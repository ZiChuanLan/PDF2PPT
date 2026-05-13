# pyright: reportMissingImports=false

"""Background job processing.

Production mode uses RQ + Redis.
Local QA mode supports an in-memory job store (REDIS_URL=memory://) and runs
the conversion inline via threads (see jobs router).
"""

from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
from rq import Connection, Queue, Worker

from .config import get_settings
from .job_options import (
    LAYOUT_PROVIDER_ALIASES,
    normalize_baidu_doc_parse_type,
    normalize_ai_ocr_provider,
    normalize_layout_provider,
    normalize_parse_provider,
    normalize_ppt_generation_mode,
    normalize_requested_ocr_provider,
    normalize_scanned_page_mode,
    normalize_text_erase_mode,
)
from .job_paths import get_job_dir
from .convert.baidu_doc_adapter import parse_pdf_to_ir_with_baidu_doc
from .convert.mineru_adapter import parse_pdf_to_ir_with_mineru
from .convert.pdf_parser import parse_pdf_to_ir
from .convert.llm_adapter import AnthropicProvider, OpenAiProvider
from .logging_config import get_logger
from .logging_config import set_job_id, set_job_stage, setup_logging
from .models.error import AppException, ErrorCode
from .models.job import JobStage, JobStatus
from .perf_policies import RuntimePerformanceSettings
from .services.redis_service import get_redis_service
from .services.job_cleanup import cleanup_job_process_artifacts
from .utils.text import clean_str
from .worker_helpers import (
    build_ocr_debug_payload,
    run_layout_assist_stage,
    run_ocr_stage,
    run_ppt_stage,
    setup_ocr_runtime,
)
from .worker_helpers._job_options import JobOptions
from .worker_helpers._param_normalizer import (
    OCR_RENDER_DPI_TURBO_CAP,
    OCR_RENDER_DPI_FAST_CAP,
    normalize_job_options,
)


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants: Progress reporting
# ---------------------------------------------------------------------------
_PROGRESS_MAX_PROCESSING = 99       # progress clamped to 0..99 during processing; 100 = done


def _retrieve_job_secrets(job_id: str) -> dict[str, str]:
    """Retrieve sensitive keys stored separately for this job.

    Returns a dict with keys like 'api_key', 'ocr_ai_api_key', etc.
    Falls back to empty dict if secrets not found (e.g., legacy jobs).
    """
    try:
        redis_service = get_redis_service()
        return redis_service.get_job_secrets(job_id)
    except Exception:
        logger.debug("Could not retrieve secrets for job %s", job_id, exc_info=True)
        return {}


class JobCancelledError(Exception):
    """Internal control-flow exception used to abort cancelled jobs."""


def _select_layout_assist_provider(
    *,
    provider: str | None,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    ocr_ai_api_key: str | None,
    ocr_ai_base_url: str | None,
    ocr_ai_model: str | None,
) -> OpenAiProvider | AnthropicProvider | None:
    raw_provider = (clean_str(provider) or "").lower()
    if raw_provider and raw_provider not in LAYOUT_PROVIDER_ALIASES:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Unsupported layout assist provider",
            details={"provider": provider},
            status_code=400,
        )
    provider_id = normalize_layout_provider(provider)

    # Primary: main AI credentials.
    key = clean_str(api_key)
    if key:
        if provider_id == "claude":
            return AnthropicProvider(key)
        return OpenAiProvider(
            key,
            base_url=clean_str(base_url),
            model=clean_str(model),
        )

    # Fallback: reuse OCR AI credentials for optional layout assist.
    ocr_key = clean_str(ocr_ai_api_key)
    if not ocr_key:
        return None

    return OpenAiProvider(
        ocr_key,
        base_url=clean_str(ocr_ai_base_url),
        model=clean_str(ocr_ai_model),
    )


def get_redis_connection() -> Any:
    """Create a Redis connection for RQ.

    NOTE: In local QA mode (REDIS_URL=memory://) this should not be used.
    """

    settings = get_settings()
    return redis.from_url(settings.redis_url)


def _job_dir(job_id: str) -> Path:
    return get_job_dir(job_id)


def _resolve_ocr_ai_concurrency_defaults():
    """Return effective OCR AI concurrency / rate-limit defaults from Settings.

    Module-level constants are used as fallbacks; Settings values take
    precedence when configured via environment variables.
    """
    settings = get_settings()
    return {
        "page_concurrency_default": settings.ocr_ai_page_concurrency_default,
        "page_concurrency_max": settings.ocr_ai_page_concurrency_max,
        "block_concurrency_default": settings.ocr_ai_block_concurrency_default,
        "block_concurrency_max": settings.ocr_ai_block_concurrency_max,
        "rpm_default": settings.ocr_ai_rpm_default,
        "rpm_max": settings.ocr_ai_rpm_max,
        "tpm_default": settings.ocr_ai_tpm_default,
        "tpm_max": settings.ocr_ai_tpm_max,
        "max_retries_default": settings.ocr_ai_max_retries_default,
        "max_retries_max": settings.ocr_ai_max_retries_max,
    }


def process_pdf_job(job_id: str, *, options: JobOptions) -> None:
    """RQ job handler: process a single PDF-to-PPT conversion job."""

    # Retrieve sensitive keys stored separately in Redis (not in RQ kwargs).
    # This prevents API keys from being exposed in RQ job descriptions or logs.
    _secrets = _retrieve_job_secrets(job_id)
    options.api_key = _secrets.get("api_key") or options.api_key
    options.mineru_api_token = _secrets.get("mineru_api_token") or options.mineru_api_token
    options.ocr_baidu_api_key = _secrets.get("ocr_baidu_api_key") or options.ocr_baidu_api_key
    options.ocr_baidu_secret_key = _secrets.get("ocr_baidu_secret_key") or options.ocr_baidu_secret_key
    options.ocr_ai_api_key = _secrets.get("ocr_ai_api_key") or options.ocr_ai_api_key

    # Layout assist requires both server-side enablement (ENABLE_LAYOUT_ASSIST env var)
    # and user opt-in via settings (enableLayoutAssist checkbox).
    settings = get_settings()
    enable_layout_assist = settings.enable_layout_assist and options.enable_layout_assist
    layout_assist_apply_image_regions = settings.enable_layout_assist and options.layout_assist_apply_image_regions
    redis_service = get_redis_service()
    set_job_id(job_id)
    set_job_stage(None)
    perf_settings = RuntimePerformanceSettings.from_settings(settings)
    ocr_concurrency = _resolve_ocr_ai_concurrency_defaults()
    default_ocr_render_dpi = int(perf_settings.ocr_render_dpi)
    scanned_render_dpi = int(perf_settings.scanned_render_dpi)
    keepalive_interval_s = float(perf_settings.keepalive_interval_s)

    job_path = _job_dir(job_id)
    input_pdf = job_path / "input.pdf"
    output_pptx = job_path / "output.pptx"
    ir_path = job_path / "ir.json"
    artifacts_dir = job_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Create processing marker to prevent cleanup daemon from deleting
    # active job directory if worker hangs or Redis metadata is lost.
    processing_marker = job_path / ".processing"
    processing_marker.write_text(
        json.dumps({"started_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )

    if redis_service.is_cancelled(job_id):
        set_job_stage(JobStage.cleanup.value)
        redis_service.update_job(
            job_id,
            status=JobStatus.cancelled,
            stage=JobStage.cleanup,
            progress=100,
            message="Job cancelled",
        )
        set_job_stage(None)
        set_job_id(None)
        return

    def _select_provider() -> OpenAiProvider | AnthropicProvider | None:
        selected = _select_layout_assist_provider(
            provider=options.provider,
            api_key=options.api_key,
            base_url=options.base_url,
            model=options.model,
            ocr_ai_api_key=options.ocr_ai_api_key,
            ocr_ai_base_url=options.ocr_ai_base_url,
            ocr_ai_model=options.ocr_ai_model,
        )
        if (
            selected is not None
            and (not clean_str(options.api_key))
            and clean_str(options.ocr_ai_api_key)
        ):
            logger.info(
                "Using OCR AI credentials for layout assist (main API key missing)"
            )
        return selected

    # --- Normalize string enum fields ---
    normalized_text_erase_mode = normalize_text_erase_mode(options.text_erase_mode)
    normalized_scanned_page_mode = normalize_scanned_page_mode(options.scanned_page_mode)
    normalized_ppt_generation_mode = normalize_ppt_generation_mode(options.ppt_generation_mode)
    fast_ppt_generation = normalized_ppt_generation_mode == "fast"
    turbo_ppt_generation = normalized_ppt_generation_mode == "turbo"
    speed_ppt_generation = fast_ppt_generation or turbo_ppt_generation

    # --- Normalize all numeric parameters via extracted module ---
    normalize_job_options(options, default_ocr_render_dpi, ocr_concurrency)

    # --- Derived values after normalization ---
    effective_ocr_render_dpi = int(options.ocr_render_dpi)
    if turbo_ppt_generation:
        effective_ocr_render_dpi = min(effective_ocr_render_dpi, OCR_RENDER_DPI_TURBO_CAP)
    elif fast_ppt_generation:
        effective_ocr_render_dpi = min(effective_ocr_render_dpi, OCR_RENDER_DPI_FAST_CAP)

    fast_skip_image_region_detection = (
        speed_ppt_generation and normalized_scanned_page_mode == "fullpage"
    )

    try:
        if not input_pdf.exists():
            raise AppException(
                code=ErrorCode.INVALID_PDF,
                message="Input PDF not found",
                details={"path": str(input_pdf)},
                status_code=400,
            )

        parse_provider_id = normalize_parse_provider(options.parse_provider)
        baidu_doc_parse_type_id = normalize_baidu_doc_parse_type(options.baidu_doc_parse_type)
        if parse_provider_id not in {"local", "mineru", "baidu_doc", "v2"}:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Unsupported parse provider",
                details={"parse_provider": options.parse_provider},
            )

        reported_progress = 0

        def _set_processing_progress(
            stage: JobStage, progress: int, message: str
        ) -> None:
            nonlocal reported_progress
            set_job_stage(stage.value)
            if redis_service.is_cancelled(job_id):
                redis_service.update_job(
                    job_id,
                    status=JobStatus.cancelled,
                    stage=stage,
                    progress=100,
                    message="Job cancelled",
                )
                raise JobCancelledError()
            clamped = max(0, min(_PROGRESS_MAX_PROCESSING, int(progress)))
            if clamped < reported_progress:
                clamped = reported_progress
            reported_progress = clamped
            redis_service.update_job(
                job_id,
                status=JobStatus.processing,
                stage=stage,
                progress=clamped,
                message=message,
            )

        def _abort_if_cancelled(
            *, stage: JobStage | None = None, message: str | None = None
        ) -> None:
            if not redis_service.is_cancelled(job_id):
                return
            set_job_stage((stage or JobStage.cleanup).value)
            redis_service.update_job(
                job_id,
                status=JobStatus.cancelled,
                stage=stage or JobStage.cleanup,
                progress=100,
                message=message or "Job cancelled",
            )
            raise JobCancelledError()

        def _refresh_job_ttl() -> None:
            redis_service.refresh_job_ttl(job_id)

        def _write_ocr_debug_artifact(payload: dict[str, Any]) -> None:
            ocr_dir = artifacts_dir / "ocr"
            ocr_dir.mkdir(parents=True, exist_ok=True)
            (ocr_dir / "ocr_debug.json").write_text(
                json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )

        _set_processing_progress(
            JobStage.parsing,
            5,
            (
                "正在调用 MinerU 解析文档…"
                if parse_provider_id == "mineru"
                else (
                    "正在调用百度解析（PaddleOCR-VL）…"
                    if baidu_doc_parse_type_id == "paddle_vl"
                    else "正在调用百度解析（普通）…"
                )
                if parse_provider_id == "baidu_doc"
                else "正在解析文档结构…"
            ),
        )
        _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")

        legacy_v2_mode = parse_provider_id == "v2"
        if legacy_v2_mode:
            # Legacy compatibility: `parse_provider=v2` used to call a separate
            # "full-page OCR overlay" pipeline. That path duplicated logic and
            # produced unstable output quality. We now route it through the main
            # pipeline while keeping behavior similar:
            # - force OCR on
            # - prefer full-page scanned rendering mode (no image crops)
            # - force AI OCR credentials via SiliconFlow/OpenAI-compatible config
            parse_provider_id = "local"
            normalized_scanned_page_mode = "fullpage"
            options.enable_ocr = True

            resolved_api_key = (
                clean_str(options.ocr_ai_api_key)
                or clean_str(options.api_key)
            )
            resolved_base_url = (
                clean_str(options.ocr_ai_base_url)
                or clean_str(options.base_url)
                or "https://api.siliconflow.cn/v1"
            )
            resolved_model = (
                clean_str(options.ocr_ai_model)
                or clean_str(options.model)
                or "Pro/deepseek-ai/deepseek-ocr"
            )

            if not resolved_api_key:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Missing API key for parse_provider=v2",
                    details={
                        "hint": "Use api_key or ocr_ai_api_key",
                    },
                    status_code=400,
                )

            options.ocr_provider = "aiocr"
            options.ocr_ai_api_key = resolved_api_key
            options.ocr_ai_base_url = resolved_base_url
            options.ocr_ai_model = resolved_model
            if not clean_str(options.ocr_ai_provider):
                options.ocr_ai_provider = "auto"

        if parse_provider_id == "mineru":
            # mineru_hybrid_ocr is deprecated and ignored.
            # Log a one-time warning if someone still passes it.
            if options.mineru_hybrid_ocr is not None:
                logger.warning(
                    "mineru_hybrid_ocr is deprecated and ignored (job %s); "
                    "MinerU no longer layers local hybrid OCR alignment.",
                    job_id,
                )

            def _mineru_poll_check() -> None:
                _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")
                _refresh_job_ttl()

            ir = parse_pdf_to_ir_with_mineru(
                input_pdf,
                artifacts_dir / "mineru",
                token=clean_str(options.mineru_api_token),
                base_url=clean_str(options.mineru_base_url),
                model_version=clean_str(options.mineru_model_version) or "vlm",
                enable_formula=options.mineru_enable_formula,
                enable_table=options.mineru_enable_table,
                language=clean_str(options.mineru_language),
                is_ocr=options.mineru_is_ocr,
                page_start=options.page_start,
                page_end=options.page_end,
                data_id=job_id,
                cancel_check=_mineru_poll_check,
            )
        elif parse_provider_id == "baidu_doc":

            def _baidu_poll_check() -> None:
                _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")
                _refresh_job_ttl()

            options.enable_ocr = False
            enable_layout_assist = False
            ir = parse_pdf_to_ir_with_baidu_doc(
                input_pdf,
                artifacts_dir / "baidu_doc",
                api_key=clean_str(options.ocr_baidu_api_key),
                secret_key=clean_str(options.ocr_baidu_secret_key),
                parse_type=baidu_doc_parse_type_id,
                page_start=options.page_start,
                page_end=options.page_end,
                cancel_check=_baidu_poll_check,
            )
        else:
            ir = parse_pdf_to_ir(
                input_pdf,
                artifacts_dir,
                page_start=options.page_start,
                page_end=options.page_end,
            )
        # Persist parsed IR for debugging. We'll overwrite with the final IR at end.
        (job_path / "ir.parsed.json").write_text(
            json.dumps(ir, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        parsed_pages = sum(
            1 for page in (ir.get("pages") or []) if isinstance(page, dict)
        )
        artifact_export_policy = (
            perf_settings.artifact_exports.resolve_for_parsed_document(
                parsed_pages=parsed_pages
            )
        )
        _set_processing_progress(
            JobStage.parsing,
            22,
            f"文档解析完成，共 {parsed_pages} 页",
        )
        _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")

        # For pages without text layer, run the OCR stage only for the local
        # pipeline. MinerU now stays on its own OCR/parse path and no longer
        # layers an extra OCR pass on top.
        scanned_pages_exist = any(
            isinstance(page, dict)
            and not page.get("has_text_layer")
            and not page.get("ocr_used")
            for page in (ir.get("pages") or [])
        )
        should_attempt_ocr = (
            parse_provider_id == "local" and scanned_pages_exist and bool(options.enable_ocr)
        )
        ocr_setup = None
        ocr_manager = None
        text_refiner = None
        linebreak_refiner = None
        linebreak_enabled = False
        auto_linebreak_enabled = False
        ocr_debug_payload: dict[str, Any] | None = None
        effective_ocr_provider = normalize_requested_ocr_provider(options.ocr_provider)
        effective_ocr_ai_provider = normalize_ai_ocr_provider(options.ocr_ai_provider)
        effective_ocr_ai_base_url = clean_str(options.ocr_ai_base_url)
        effective_ocr_ai_model = clean_str(options.ocr_ai_model)
        effective_tesseract_language = (
            clean_str(options.ocr_tesseract_language) or "chi_sim+eng"
        )
        effective_tesseract_min_conf: float | None = None
        strict_ocr_mode = bool(True if options.ocr_strict_mode is None else options.ocr_strict_mode)

        if not scanned_pages_exist:
            _set_processing_progress(
                JobStage.parsing,
                30,
                "文档已有文本层，跳过 OCR 阶段",
            )
        elif not should_attempt_ocr:
            _set_processing_progress(
                JobStage.ocr,
                34,
                "检测到扫描页，但未启用 OCR，将按图片方式生成",
            )

        if should_attempt_ocr and scanned_pages_exist:
            ocr_target_pages = sum(
                1
                for page in (ir.get("pages") or [])
                if isinstance(page, dict) and not page.get("has_text_layer")
            )
            export_ocr_overlay_images_effective = (
                perf_settings.artifact_exports.resolve_ocr_overlay_images(
                    ocr_target_pages=ocr_target_pages
                )
            )
            _set_processing_progress(
                JobStage.ocr,
                35,
                f"正在准备 OCR（目标 {ocr_target_pages} 页）",
            )

            ocr_setup = setup_ocr_runtime(
                provider=options.provider,
                api_key=options.api_key,
                base_url=options.base_url,
                model=options.model,
                ocr_provider=options.ocr_provider,
                ocr_baidu_app_id=options.ocr_baidu_app_id,
                ocr_baidu_api_key=options.ocr_baidu_api_key,
                ocr_baidu_secret_key=options.ocr_baidu_secret_key,
                ocr_tesseract_min_confidence=options.ocr_tesseract_min_confidence,
                ocr_tesseract_language=options.ocr_tesseract_language,
                ocr_ai_api_key=options.ocr_ai_api_key,
                ocr_ai_provider=options.ocr_ai_provider,
                ocr_ai_base_url=options.ocr_ai_base_url,
                ocr_ai_model=options.ocr_ai_model,
                ocr_ai_chain_mode=options.ocr_ai_chain_mode,
                ocr_ai_layout_model=options.ocr_ai_layout_model,
                ocr_ai_prompt_preset=options.ocr_ai_prompt_preset,
                ocr_ai_direct_prompt_override=options.ocr_ai_direct_prompt_override,
                ocr_ai_layout_block_prompt_override=options.ocr_ai_layout_block_prompt_override,
                ocr_ai_image_region_prompt_override=options.ocr_ai_image_region_prompt_override,
                ocr_paddle_vl_docparser_max_side_px=options.ocr_paddle_vl_docparser_max_side_px,
                ocr_ai_page_concurrency=options.ocr_ai_page_concurrency,
                ocr_ai_block_concurrency=options.ocr_ai_block_concurrency,
                ocr_ai_requests_per_minute=options.ocr_ai_requests_per_minute,
                ocr_ai_tokens_per_minute=options.ocr_ai_tokens_per_minute,
                ocr_ai_max_retries=options.ocr_ai_max_retries,
                ocr_geometry_mode=options.ocr_geometry_mode,
                ocr_ai_linebreak_assist=options.ocr_ai_linebreak_assist,
                ocr_strict_mode=options.ocr_strict_mode,
            )
            ocr_manager = ocr_setup.ocr_manager
            text_refiner = ocr_setup.text_refiner
            linebreak_refiner = ocr_setup.linebreak_refiner
            effective_ocr_provider = ocr_setup.effective_ocr_provider
            effective_ocr_ai_provider = ocr_setup.effective_ocr_ai_provider
            effective_ocr_ai_base_url = ocr_setup.effective_ocr_ai_base_url
            effective_ocr_ai_model = ocr_setup.effective_ocr_ai_model
            effective_tesseract_language = ocr_setup.effective_tesseract_language
            effective_tesseract_min_conf = ocr_setup.effective_tesseract_min_conf
            strict_ocr_mode = ocr_setup.strict_ocr_mode
            linebreak_enabled = ocr_setup.linebreak_enabled
            auto_linebreak_enabled = ocr_setup.auto_linebreak_enabled
            ocr_debug_payload = build_ocr_debug_payload(
                provider_requested=(options.ocr_provider or "auto"),
                ocr_render_dpi=int(effective_ocr_render_dpi),
                scanned_render_dpi=int(scanned_render_dpi),
                ocr_ai_linebreak_assist=options.ocr_ai_linebreak_assist,
                setup=ocr_setup,
            )
            ocr_debug_payload["env_PATH"] = os.environ.get("PATH")

            def _build_page_ocr_runtime():
                return setup_ocr_runtime(
                    provider=options.provider,
                    api_key=options.api_key,
                    base_url=options.base_url,
                    model=options.model,
                    ocr_provider=options.ocr_provider,
                    ocr_baidu_app_id=options.ocr_baidu_app_id,
                    ocr_baidu_api_key=options.ocr_baidu_api_key,
                    ocr_baidu_secret_key=options.ocr_baidu_secret_key,
                    ocr_tesseract_min_confidence=options.ocr_tesseract_min_confidence,
                    ocr_tesseract_language=options.ocr_tesseract_language,
                    ocr_ai_api_key=options.ocr_ai_api_key,
                    ocr_ai_provider=options.ocr_ai_provider,
                    ocr_ai_base_url=options.ocr_ai_base_url,
                    ocr_ai_model=options.ocr_ai_model,
                    ocr_ai_chain_mode=options.ocr_ai_chain_mode,
                    ocr_ai_layout_model=options.ocr_ai_layout_model,
                    ocr_ai_prompt_preset=options.ocr_ai_prompt_preset,
                    ocr_ai_direct_prompt_override=options.ocr_ai_direct_prompt_override,
                    ocr_ai_layout_block_prompt_override=options.ocr_ai_layout_block_prompt_override,
                    ocr_ai_image_region_prompt_override=options.ocr_ai_image_region_prompt_override,
                    ocr_paddle_vl_docparser_max_side_px=options.ocr_paddle_vl_docparser_max_side_px,
                    ocr_ai_page_concurrency=options.ocr_ai_page_concurrency,
                    ocr_ai_block_concurrency=options.ocr_ai_block_concurrency,
                    ocr_ai_requests_per_minute=options.ocr_ai_requests_per_minute,
                    ocr_ai_tokens_per_minute=options.ocr_ai_tokens_per_minute,
                    ocr_ai_max_retries=options.ocr_ai_max_retries,
                    ocr_geometry_mode=options.ocr_geometry_mode,
                    ocr_ai_linebreak_assist=options.ocr_ai_linebreak_assist,
                    ocr_strict_mode=options.ocr_strict_mode,
                )

            if ocr_setup.setup_warning:
                logger.warning(
                    "OCR setup failed (best-effort): %s", ocr_setup.setup_warning
                )
                ir.setdefault("warnings", []).append(
                    f"ocr_setup_failed_best_effort: error={ocr_setup.setup_warning}"
                )
            if (
                options.ocr_ai_linebreak_assist is True
                and ocr_setup.linebreak_enabled
                and ocr_setup.linebreak_mode != "ai_refiner"
            ):
                ir.setdefault("warnings", []).append(
                    "ocr_linebreak_assist_heuristic_only:"
                    f" mode={ocr_setup.linebreak_mode}"
                    f" reason={ocr_setup.linebreak_unavailable_reason or 'ai_refiner_unavailable'}"
                )

            if ocr_manager is None:
                if ocr_debug_payload is not None:
                    ocr_debug_payload["runtime"] = {
                        "configured_provider": ocr_setup.effective_ocr_provider,
                        "runtime_provider": "unavailable",
                        "provider_chain": [],
                        "setup_warning": ocr_setup.setup_warning,
                    }
                    ocr_debug_payload["pages"] = []
                    ocr_debug_payload["page_runtime_summary"] = {
                        "provider_counts": {},
                        "distinct_provider_count": 0,
                        "pages_with_elements": 0,
                        "pages_with_errors": 0,
                        "fallback_pages": 0,
                        "fallback_reason_counts": {},
                        "ai_provider_disabled": False,
                        "ai_provider_disabled_reason": None,
                    }
                    _write_ocr_debug_artifact(ocr_debug_payload)
                # No OCR possible; continue conversion as image-only.
                scanned_pages_exist = False

        if scanned_pages_exist and should_attempt_ocr and ocr_manager:
            if ocr_setup is None:
                raise RuntimeError("internal error: OCR runtime setup missing")
            if ocr_debug_payload is None:
                raise RuntimeError("internal error: OCR debug payload missing")
            linebreak_assist_effective = (
                False
                if options.ocr_ai_linebreak_assist is False
                else (True if linebreak_enabled else None)
            )
            run_ocr_stage(
                ir=ir,
                input_pdf=input_pdf,
                job_path=job_path,
                artifacts_dir=artifacts_dir,
                settings=settings,
                ocr_manager=ocr_manager,
                text_refiner=text_refiner,
                linebreak_refiner=linebreak_refiner,
                linebreak_assist_effective=linebreak_assist_effective,
                strict_no_fallback=bool(strict_ocr_mode),
                effective_ocr_provider=effective_ocr_provider,
                ocr_render_dpi=int(effective_ocr_render_dpi),
                ocr_debug=ocr_debug_payload,
                export_overlay_images=export_ocr_overlay_images_effective,
                skip_image_region_detection=bool(fast_skip_image_region_detection),
                ocr_setup=ocr_setup,
                ocr_runtime_factory=_build_page_ocr_runtime,
                set_processing_progress=_set_processing_progress,
                abort_if_cancelled=_abort_if_cancelled,
            )

        ir = run_layout_assist_stage(
            ir=ir,
            job_id=job_id,
            enable_layout_assist=bool(enable_layout_assist),
            layout_assist_apply_image_regions=bool(layout_assist_apply_image_regions),
            input_pdf=input_pdf,
            job_path=job_path,
            artifacts_dir=artifacts_dir,
            scanned_render_dpi=int(scanned_render_dpi),
            export_debug_images=artifact_export_policy.layout_assist_debug_images,
            select_provider=_select_provider,
            set_processing_progress=_set_processing_progress,
            abort_if_cancelled=_abort_if_cancelled,
            heartbeat=_refresh_job_ttl,
            heartbeat_interval_s=keepalive_interval_s,
        ).ir

        ppt_stage_kwargs: dict[str, Any] = {
            "ir": ir,
            "output_pptx": output_pptx,
            "artifacts_dir": artifacts_dir,
            "scanned_render_dpi": int(scanned_render_dpi),
            "remove_footer_notebooklm": bool(options.remove_footer_notebooklm),
            "normalized_text_erase_mode": normalized_text_erase_mode,
            "normalized_scanned_page_mode": normalized_scanned_page_mode,
            "normalized_ppt_generation_mode": normalized_ppt_generation_mode,
            "normalized_image_bg_clear_expand_min_pt": options.image_bg_clear_expand_min_pt,
            "normalized_image_bg_clear_expand_max_pt": options.image_bg_clear_expand_max_pt,
            "normalized_image_bg_clear_expand_ratio": options.image_bg_clear_expand_ratio,
            "normalized_scanned_image_region_min_area_ratio": options.scanned_image_region_min_area_ratio,
            "normalized_scanned_image_region_max_area_ratio": options.scanned_image_region_max_area_ratio,
            "normalized_scanned_image_region_max_aspect_ratio": options.scanned_image_region_max_aspect_ratio,
            "export_final_preview_images": artifact_export_policy.final_preview_images,
            "set_processing_progress": _set_processing_progress,
            "abort_if_cancelled": _abort_if_cancelled,
            "heartbeat": _refresh_job_ttl,
            "heartbeat_interval_s": keepalive_interval_s,
        }
        ppt_stage_params = inspect.signature(run_ppt_stage).parameters
        if "remove_footer_notebooklm" not in ppt_stage_params:
            ppt_stage_kwargs.pop("remove_footer_notebooklm", None)
            ir.setdefault("warnings", []).append(
                "worker_helper_compat_mode_missing_remove_footer_notebooklm"
            )
        ppt_stage_result = run_ppt_stage(**ppt_stage_kwargs)
        worker_compat_mode = bool(
            getattr(ppt_stage_result, "worker_compat_mode", ppt_stage_result)
        )
        # Persist final IR so users can inspect what the generator saw.
        ir_path.write_text(
            json.dumps(ir, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )

        # Collect user-facing warnings from IR
        warnings_obj = ir.get("warnings")
        ir_warnings: list[Any] = warnings_obj if isinstance(warnings_obj, list) else []
        user_warnings: list[str] = []
        for w in ir_warnings:
            w_str = str(w)
            if "ocr_setup_failed_best_effort" in w_str:
                user_warnings.append("OCR 初始化失败，已降级为图片模式")
            elif "ocr_failed_best_effort" in w_str:
                user_warnings.append("部分页面 OCR 失败，已降级为图片模式")
            elif "ocr_empty_result" in w_str:
                user_warnings.append("部分页面 OCR 未识别到文字")
            elif "ocr_linebreak_assist_heuristic_only" in w_str:
                user_warnings.append("OCR 行拆分未使用 AI 模型，已改为启发式模式")
            elif "ocr_page_provider_switches" in w_str:
                user_warnings.append("OCR 在任务内发生了 provider 切换，请检查调试产物")
            elif "ocr_page_fallbacks" in w_str:
                user_warnings.append("部分页面 OCR 发生了回退，请检查调试产物")
            elif "ocr_ai_provider_disabled" in w_str:
                user_warnings.append("AI OCR 在任务中途被停用，后续页面改走本地链路")
            elif "paddle_vl_sparse_slide_layout" in w_str:
                user_warnings.append(
                    "PaddleOCR-VL 当前页识别结果偏粗，可能漏掉流程图小字；这类页面更建议用 DeepSeek OCR / Qwen"
                )
            elif "layout_assist_status=failed" in w_str:
                user_warnings.append("AI 版式辅助失败，使用原始布局")
            elif "layout_assist_status=skipped_missing_provider" in w_str:
                user_warnings.append("AI 版式辅助未执行：缺少可用 AI 配置")
        # Deduplicate
        user_warnings = list(dict.fromkeys(user_warnings))

        completion_message = (
            "转换完成，可下载 PPTX（兼容模式，建议升级 worker）"
            if worker_compat_mode
            else "转换完成，可下载 PPTX"
        )
        if user_warnings:
            completion_message += "（⚠️ " + "；".join(user_warnings) + "）"

        redis_service.update_job(
            job_id,
            status=JobStatus.completed,
            stage=JobStage.done,
            progress=100,
            message=completion_message,
        )

    except JobCancelledError:
        set_job_stage(JobStage.cleanup.value)
        logger.info("Job %s cancelled", job_id)
        return
    except AppException as e:
        set_job_stage(JobStage.cleanup.value)
        logger.warning(f"Job {job_id} failed: {e.code} {e.message}")
        redis_service.update_job(
            job_id,
            status=JobStatus.failed,
            stage=JobStage.cleanup,
            progress=100,
            message=e.message,
            error={"code": e.code, "message": e.message, "details": e.details},
        )
        return
    except Exception as e:
        set_job_stage(JobStage.cleanup.value)
        logger.exception(f"Job {job_id} crashed: {e!s}")
        redis_service.update_job(
            job_id,
            status=JobStatus.failed,
            stage=JobStage.cleanup,
            progress=100,
            message="Conversion failed",
            error={"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        )
        return
    finally:
        # Remove processing marker
        try:
            processing_marker.unlink(missing_ok=True)
        except Exception:
            pass
        # Clean up secrets from Redis immediately (no longer needed)
        try:
            redis_service.delete_job_secrets(job_id)
        except Exception:
            pass
        if not bool(options.retain_process_artifacts):
            try:
                removed = cleanup_job_process_artifacts(job_path)
                if removed:
                    logger.info("Removed process artifacts for job %s", job_id)
            except Exception:
                logger.warning(
                    "Failed to remove process artifacts for job %s",
                    job_id,
                    exc_info=True,
                )
            # Clean up intermediate IR file
            ir_parsed = job_path / "ir.parsed.json"
            try:
                ir_parsed.unlink(missing_ok=True)
            except Exception:
                pass
        set_job_stage(None)
        set_job_id(None)


def run_worker() -> None:
    """Run the RQ worker."""

    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    settings = get_settings()
    if str(settings.redis_url).startswith("memory://"):
        raise RuntimeError("RQ worker is not supported with REDIS_URL=memory://")

    conn = redis.from_url(settings.redis_url)
    with Connection(conn):
        # Do not log full job kwargs; requests carry user API keys (OpenAI/Baidu/etc).
        worker = Worker(Queue("default"), log_job_description=False)
        worker.work()


if __name__ == "__main__":
    run_worker()
