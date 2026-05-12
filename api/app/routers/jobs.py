# pyright: reportMissingImports=false

"""Job API endpoints."""

import asyncio
import io
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import quote

import pymupdf
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from rq import Queue
from rq.job import Job as RqJob

try:
    from rq.command import send_stop_job_command
except Exception:  # pragma: no cover - compatibility with older RQ builds
    send_stop_job_command = None

from ..config import get_settings
from ..dependencies import get_current_user_optional
from ..job_options import validate_and_normalize_job_options
from ..schemas.job_config import JobConfig
from ..job_paths import (
    ensure_job_dir as ensure_job_dir_via_paths,
    get_job_dir as get_job_dir_via_paths,
    resolve_artifact_file,
)
from ..logging_config import get_logger
from ..models.error import AppException, ErrorCode
from ..models.job import (
    AiOcrCheckRequest,
    AiOcrCheckResponse,
    AiOcrCheckResult,
    AiOcrCheckSampleItem,
    JobCreateResponse,
    JobEvent,
    JobArtifactImage,
    JobArtifactsResponse,
    LocalOcrCheckRequest,
    LocalOcrCheckResult,
    LocalOcrCheckResponse,
    JobListItem,
    JobListResponse,
    JobStage,
    JobStatus,
    JobStatusResponse,
)
from ._upload_utils import (
    classify_upload_kind as _classify_upload_kind,
    normalize_upload_content_type as _normalize_upload_content_type,
    write_upload_as_input_pdf as _write_upload_as_input_pdf,
)
from ._ocr_check import (
    run_ai_ocr_capability_check as _run_ai_ocr_capability_check,
    truncate_error as _truncate_error,
)
from ..convert.ocr import (
    _coerce_bbox_xyxy,
    create_remote_ocr_client,
    probe_local_paddle_models,
    probe_local_paddleocr,
    probe_local_tesseract_models,
    probe_local_tesseract,
)
from ..services.redis_service import get_redis_service
from ..worker import get_redis_connection, process_pdf_job
from ..worker_helpers._job_options import JobOptions

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

def _submit_job(job_id: str, kwargs: dict[str, Any]) -> None:
    """Submit a job for processing via Thread (memory) or RQ (Redis)."""
    job_options = JobOptions(**kwargs)
    redis_service = get_redis_service()
    if redis_service.is_memory_backend():
        threading.Thread(
            target=process_pdf_job,
            kwargs={"job_id": job_id, "options": job_options},
            daemon=True,
        ).start()
    else:
        redis_conn = get_redis_connection()
        queue = Queue(connection=redis_conn)
        queue.enqueue(
            "app.worker.process_pdf_job",
            job_id,
            options=job_options,
            job_id=job_id,
            description=f"process_pdf_job(job_id={job_id})",
        )


def _sync_rq_cancel_state(*, job_id: str, status: JobStatus) -> None:
    """Mirror API-level cancellation into RQ so queued/running jobs unblock quickly."""
    redis_service = get_redis_service()
    if redis_service.is_memory_backend():
        return

    try:
        redis_conn = get_redis_connection()
    except Exception as e:
        logger.warning(
            "Failed to acquire Redis connection for job %s cancel: %s", job_id, e
        )
        return

    normalized_status = str(
        status.value if isinstance(status, JobStatus) else status
    ).strip().lower()
    try:
        if normalized_status == JobStatus.pending.value:
            rq_job = RqJob.fetch(job_id, connection=redis_conn)
            rq_job.cancel()
            logger.info("Cancelled queued RQ job %s", job_id)
            return

        if (
            normalized_status == JobStatus.processing.value
            and send_stop_job_command is not None
        ):
            send_stop_job_command(redis_conn, job_id)
            logger.info("Sent stop command to running RQ job %s", job_id)
            return

        if normalized_status == JobStatus.processing.value:
            logger.warning(
                "RQ stop command unavailable while cancelling running job %s",
                job_id,
            )
    except Exception as e:
        logger.warning("Failed to sync RQ cancel state for job %s: %s", job_id, e)


@router.post("/ocr/local/check", response_model=LocalOcrCheckResponse)
async def check_local_ocr(payload: LocalOcrCheckRequest):
    """Check whether local OCR runtime is available."""
    provider_id = (payload.provider or "tesseract").strip().lower()

    try:
        if provider_id in {"tesseract", "local", "local_tesseract"}:
            probe = probe_local_tesseract(language=payload.language)
        elif provider_id in {"paddle", "paddleocr", "paddle_ocr"}:
            probe = probe_local_paddleocr(language=payload.language)
        elif provider_id in {"tesseract_models", "tesseract-models", "tess_models"}:
            probe = probe_local_tesseract_models(language=payload.language)
        elif provider_id in {"paddle_models", "paddle-models", "paddleocr_models"}:
            probe = probe_local_paddle_models(language=payload.language)
        else:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Unsupported local OCR provider",
                details={"provider": payload.provider},
                status_code=400,
            )

        ready = bool(probe.get("ready"))
        return LocalOcrCheckResponse(
            ok=ready,
            check=LocalOcrCheckResult.model_validate(probe),
        )
    except AppException:
        raise
    except Exception as e:
        logger.exception("Local OCR check failed (provider=%s): %s", provider_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to check local OCR runtime",
            details={"error": str(e), "provider": provider_id},
            status_code=500,
        )


@router.post("/ocr/ai/check", response_model=AiOcrCheckResponse)
async def check_ai_ocr(payload: AiOcrCheckRequest):
    """Check whether the selected AI OCR model can return usable bbox items."""
    api_key = (payload.api_key or "").strip()
    model = (payload.model or "").strip()
    if not api_key:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="api_key is required",
            status_code=400,
        )
    if not model:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="model is required",
            status_code=400,
        )

    try:
        return await asyncio.to_thread(
            _run_ai_ocr_capability_check,
            provider=payload.provider,
            api_key=api_key,
            base_url=payload.base_url,
            model=model,
            ocr_ai_chain_mode=payload.ocr_ai_chain_mode,
            ocr_ai_layout_model=payload.ocr_ai_layout_model,
            ocr_ai_prompt_preset=payload.ocr_ai_prompt_preset,
            ocr_ai_direct_prompt_override=payload.ocr_ai_direct_prompt_override,
            ocr_ai_layout_block_prompt_override=payload.ocr_ai_layout_block_prompt_override,
            ocr_ai_image_region_prompt_override=payload.ocr_ai_image_region_prompt_override,
            ocr_paddle_vl_docparser_max_side_px=payload.ocr_paddle_vl_docparser_max_side_px,
            ocr_ai_block_concurrency=payload.ocr_ai_block_concurrency,
            ocr_ai_requests_per_minute=payload.ocr_ai_requests_per_minute,
            ocr_ai_tokens_per_minute=payload.ocr_ai_tokens_per_minute,
            ocr_ai_max_retries=payload.ocr_ai_max_retries,
        )
    except AppException:
        raise
    except Exception as e:
        logger.exception("AI OCR capability check failed: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to check AI OCR capability",
            details={"error": _truncate_error(e)},
            status_code=500,
        )


def get_job_dir(job_id: str) -> Path:
    """Get job directory path."""
    return get_job_dir_via_paths(job_id)


def ensure_job_dir(job_id: str) -> Path:
    """Create and return job directory."""
    return ensure_job_dir_via_paths(job_id)


def _safe_artifact_path(job_id: str, rel_path: str) -> Path:
    """Resolve an artifact path safely under the job directory."""
    return resolve_artifact_file(job_id, rel_path)


def _collect_page_images(
    *,
    job_dir: Path,
    subdir: str,
    regex: str,
    url_prefix: str,
) -> list[JobArtifactImage]:
    base_dir = job_dir / subdir
    if not base_dir.exists():
        return []
    matcher = re.compile(regex)
    images: list[JobArtifactImage] = []
    for path in sorted(base_dir.glob("*.png")):
        m = matcher.match(path.name)
        if not m:
            continue
        page_index = int(m.group(1))
        rel = str(path.relative_to(job_dir))
        images.append(
            JobArtifactImage(
                page_index=page_index,
                path=rel,
                url=f"{url_prefix}/file?path={quote(rel)}",
            )
        )
    return images


@router.get("", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(50, ge=1, le=200, description="Max jobs to return"),
    current_user=Depends(get_current_user_optional),
):
    """List recent jobs with queue metadata for frontend history/queue panels.

    If authenticated, only returns jobs belonging to the current user.
    """
    redis_service = get_redis_service()
    user_id = current_user.id if current_user else None
    jobs = redis_service.list_jobs(limit=limit, user_id=user_id)

    queue_job_ids: list[str] = []
    started_job_ids: set[str] = set()

    if not redis_service.is_memory_backend():
        try:
            redis_conn = get_redis_connection()
            raw_queue_ids = redis_conn.lrange("rq:queue:default", 0, -1) or []
            raw_started_ids = (
                redis_conn.zrange("rq:registry:started:default", 0, -1) or []
            )

            def _to_str(value: object) -> str:
                if isinstance(value, (bytes, bytearray)):
                    return value.decode("utf-8", errors="ignore")
                return str(value)

            queue_job_ids_raw = [_to_str(v) for v in raw_queue_ids if v is not None]
            queue_job_ids = []
            for queued_id in queue_job_ids_raw:
                queued_job = redis_service.get_job(queued_id)
                if queued_job is None:
                    queue_job_ids.append(queued_id)
                    continue
                if queued_job.status in {JobStatus.pending, JobStatus.processing}:
                    queue_job_ids.append(queued_id)
            started_job_ids = {_to_str(v) for v in raw_started_ids if v is not None}
        except Exception as e:
            logger.warning("Failed to load RQ queue metadata: %s", e)

    queue_pos_map = {job_id: idx + 1 for idx, job_id in enumerate(queue_job_ids)}

    items: list[JobListItem] = []
    for job in jobs:
        queue_position = queue_pos_map.get(job.job_id)
        if queue_position is not None:
            queue_state = "queued"
        elif job.status == JobStatus.processing:
            # If backend already marks the job as processing, treat it as running
            # even when RQ registry polling temporarily misses it.
            queue_state = "running"
        elif job.job_id in started_job_ids:
            queue_state = "running"
        elif job.status == JobStatus.pending:
            queue_state = "waiting"
        else:
            queue_state = "done"

        items.append(
            JobListItem(
                job_id=job.job_id,
                user_id=job.user_id,
                status=job.status,
                stage=job.stage,
                progress=job.progress,
                created_at=job.created_at,
                expires_at=job.expires_at,
                message=job.message,
                error=job.error,
                queue_position=queue_position,
                queue_state=queue_state,
            )
        )

    return JobListResponse(
        jobs=items,
        queue_size=len(queue_job_ids),
        returned=len(items),
    )


@router.post("", response_model=JobCreateResponse)
async def create_job(
    file: UploadFile = File(..., description="PDF or image file to convert"),
    enable_ocr: bool = Form(False, description="Enable OCR for scanned PDFs or images"),
    retain_process_artifacts: bool = Form(
        False,
        description=(
            "Keep process/debug artifacts under the job directory for tracking "
            "and visual comparison"
        ),
    ),
    remove_footer_notebooklm: bool = Form(
        False,
        description="Remove detected NotebookLM footer branding text from the output",
    ),
    text_erase_mode: str | None = Form(
        "fill", description="Text erase mode for scanned/mineru pages (smart, fill)"
    ),
    parse_provider: str = Form(
        "local",
        description=(
            "Parser provider (local, baidu_doc, mineru). Legacy `v2` is accepted for backward compatibility "
            "and maps to local+fullpage+AI OCR."
        ),
    ),
    provider: str = Form(
        "openai",
        description="LLM provider identifier (openai, claude, siliconflow, domestic)",
    ),
    api_key: str | None = Form(None, description="Optional API key for AI services"),
    baidu_doc_parse_type: str | None = Form(
        "paddle_vl",
        description="Optional Baidu parser variant when parse_provider=baidu_doc (general, paddle_vl)",
    ),
    base_url: str | None = Form(
        None, description="Optional OpenAI-compatible base URL"
    ),
    model: str | None = Form(
        None, description="Optional OpenAI-compatible model identifier"
    ),
    page_start: int | None = Form(
        None, description="Optional 1-based start page for conversion"
    ),
    page_end: int | None = Form(
        None, description="Optional 1-based end page for conversion"
    ),
    mineru_api_token: str | None = Form(
        None,
        description="Optional MinerU API token (required when parse_provider=mineru)",
    ),
    mineru_base_url: str | None = Form(
        None, description="Optional MinerU API base URL"
    ),
    mineru_model_version: str | None = Form(
        "vlm", description="MinerU model version (pipeline, vlm, MinerU-HTML)"
    ),
    mineru_enable_formula: bool | None = Form(
        True, description="Enable formula recognition in MinerU"
    ),
    mineru_enable_table: bool | None = Form(
        True, description="Enable table recognition in MinerU"
    ),
    mineru_language: str | None = Form(
        None, description="Optional MinerU language hint (e.g. ch, en)"
    ),
    mineru_is_ocr: bool | None = Form(
        None, description="Optional MinerU per-file OCR switch"
    ),
    ocr_provider: str | None = Form(
        "auto",
        description="OCR provider (auto, aiocr, baidu, tesseract, paddle, paddle_local); legacy ai/remote are accepted",
    ),
    ocr_baidu_app_id: str | None = Form(None, description="Optional Baidu OCR App ID"),
    ocr_baidu_api_key: str | None = Form(
        None, description="Optional Baidu OCR API key"
    ),
    ocr_baidu_secret_key: str | None = Form(
        None, description="Optional Baidu OCR secret key"
    ),
    ocr_tesseract_min_confidence: float | None = Form(
        None, description="Optional Tesseract min confidence (0-100)"
    ),
    ocr_tesseract_language: str | None = Form(
        None, description="Optional Tesseract language code (e.g. eng, chi_sim)"
    ),
    ocr_ai_api_key: str | None = Form(
        None, description="Optional AI OCR API key (OpenAI-compatible)"
    ),
    ocr_ai_provider: str | None = Form(
        "auto",
        description="Optional AI OCR vendor adapter (auto, openai, siliconflow, deepseek, ppio, novita)",
    ),
    ocr_ai_base_url: str | None = Form(
        None, description="Optional AI OCR base URL (OpenAI-compatible)"
    ),
    ocr_ai_model: str | None = Form(None, description="Optional AI OCR model name"),
    ocr_ai_chain_mode: str | None = Form(
        "direct",
        description="AI OCR chain mode (direct, doc_parser, layout_block)",
    ),
    ocr_ai_layout_model: str | None = Form(
        "pp_doclayout_v3",
        description="Local layout model for AI OCR layout_block chain",
    ),
    ocr_ai_prompt_preset: str | None = Form(
        "auto",
        description=(
            "Optional OCR prompt preset "
            "(auto, generic_vision, openai_vision, qwen_vl, glm_v, deepseek_ocr)"
        ),
    ),
    ocr_ai_direct_prompt_override: str | None = Form(
        None,
        description="Optional direct OCR prompt override",
    ),
    ocr_ai_layout_block_prompt_override: str | None = Form(
        None,
        description="Optional local layout block OCR prompt override",
    ),
    ocr_ai_image_region_prompt_override: str | None = Form(
        None,
        description="Optional image region detection prompt override",
    ),
    ocr_paddle_vl_docparser_max_side_px: int | None = Form(
        None,
        ge=0,
        le=6000,
        description=(
            "Optional max long-edge in pixels for PaddleOCR-VL doc_parser input images; "
            "0 disables downscale"
        ),
    ),
    ocr_ai_page_concurrency: int | None = Form(
        1,
        ge=1,
        le=8,
        description=(
            "Experimental multi-page AI OCR concurrency for direct/layout_block chains. "
            "1 keeps OCR page processing serial."
        ),
    ),
    ocr_ai_block_concurrency: int | None = Form(
        None,
        ge=1,
        le=8,
        description="Experimental per-page block concurrency override for layout_block OCR",
    ),
    ocr_ai_requests_per_minute: int | None = Form(
        None,
        ge=1,
        le=2000,
        description="Experimental shared requests-per-minute cap for AI OCR requests",
    ),
    ocr_ai_tokens_per_minute: int | None = Form(
        None,
        ge=1,
        le=2_000_000,
        description="Experimental shared tokens-per-minute cap for AI OCR requests",
    ),
    ocr_ai_max_retries: int | None = Form(
        0,
        ge=0,
        le=8,
        description="Experimental retry count for retryable AI OCR chat/completions failures",
    ),
    ocr_render_dpi: int | None = Form(
        None,
        ge=72,
        le=400,
        description="Optional OCR render DPI for scanned-page rasterization before OCR",
    ),
    scanned_page_mode: str | None = Form(
        "segmented",
        description=(
            "Image placement mode in PPT generation (segmented, fullpage). "
            "Controls whether scanned pages and MinerU text pages keep images as "
            "editable blocks or leave them in the full-page background."
        ),
    ),
    ppt_generation_mode: str | None = Form(
        "standard",
        description=(
            "PPT generation mode (standard, fast, turbo). "
            "Fast and turbo prioritize speed over fidelity, with turbo being the most aggressive."
        ),
    ),
    image_bg_clear_expand_min_pt: float | None = Form(
        None,
        description="Optional min expansion (pt) when clearing background under image overlays",
    ),
    image_bg_clear_expand_max_pt: float | None = Form(
        None,
        description="Optional max expansion (pt) when clearing background under image overlays",
    ),
    image_bg_clear_expand_ratio: float | None = Form(
        None,
        description="Optional expansion ratio for image-overlay background clearing",
    ),
    scanned_image_region_min_area_ratio: float | None = Form(
        None,
        description="Optional min page-area ratio for scanned image region candidates",
    ),
    scanned_image_region_max_area_ratio: float | None = Form(
        None,
        description="Optional max page-area ratio for scanned image region candidates",
    ),
    scanned_image_region_max_aspect_ratio: float | None = Form(
        None,
        description="Optional max aspect ratio threshold for scanned image region candidates",
    ),
    ocr_ai_linebreak_assist: bool | None = Form(
        None,
        description=(
            "Optional AI OCR line-break post-process for OCR blocks (split coarse boxes into line-level boxes). "
            "When omitted (null), the backend may auto-enable this for some OCR providers/models."
        ),
    ),
    ocr_strict_mode: bool | None = Form(
        True,
        description=(
            "Strict OCR quality mode (default on): when enabled, disable implicit OCR fallbacks/downgrades and fail fast on OCR errors"
        ),
    ),
    current_user=Depends(get_current_user_optional),
):
    """
    Create a new PDF/image to PPT conversion job.

    Uploads the file, normalizes image inputs into a single-page PDF, and queues it
    for processing.
    Returns immediately with a job_id for tracking progress.
    """
    settings = get_settings()
    redis_service = get_redis_service()
    normalized_options = validate_and_normalize_job_options(
        parse_provider=parse_provider,
        mineru_api_token=mineru_api_token,
        provider=provider,
        api_key=api_key,
        baidu_doc_parse_type=baidu_doc_parse_type,
        ocr_provider=ocr_provider,
        ocr_ai_provider=ocr_ai_provider,
        ocr_ai_api_key=ocr_ai_api_key,
        ocr_ai_model=ocr_ai_model,
        ocr_ai_chain_mode=ocr_ai_chain_mode,
        ocr_ai_layout_model=ocr_ai_layout_model,
        ocr_baidu_app_id=ocr_baidu_app_id,
        ocr_baidu_api_key=ocr_baidu_api_key,
        ocr_baidu_secret_key=ocr_baidu_secret_key,
        text_erase_mode=text_erase_mode,
        scanned_page_mode=scanned_page_mode,
        ppt_generation_mode=ppt_generation_mode,
        page_start=page_start,
        page_end=page_end,
    )
    parse_provider_id = normalized_options.parse_provider

    if parse_provider_id == "v2":
        has_v2_key = (
            bool((api_key or "").strip())
            or bool((ocr_ai_api_key or "").strip())
        )
        if not has_v2_key:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message=(
                    "api_key or ocr_ai_api_key is required when parse_provider=v2"
                ),
            )

    filename = file.filename or ""
    normalized_content_type = _normalize_upload_content_type(file.content_type)
    upload_kind = _classify_upload_kind(
        filename=filename,
        content_type=normalized_content_type,
    )
    if upload_kind is None:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Only PDF, PNG, JPG, JPEG, and WEBP files are supported",
            details={
                "filename": file.filename,
                "content_type": normalized_content_type,
            },
        )

    # Check disk space before accepting upload
    import shutil as _shutil
    _job_root = Path(settings.job_root_dir)
    _job_root.mkdir(parents=True, exist_ok=True)
    _disk = _shutil.disk_usage(_job_root)
    _min_bytes = settings.min_disk_space_mb * 1024 * 1024
    if _disk.free < _min_bytes:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"磁盘空间不足，剩余 {_disk.free // (1024*1024)}MB，需要至少 {settings.min_disk_space_mb}MB",
            details={
                "free_mb": _disk.free // (1024 * 1024),
                "required_mb": settings.min_disk_space_mb,
            },
        )

    # Generate job ID
    job_id = str(uuid.uuid4())
    job_dir: Path | None = None
    job_created = False

    try:
        # Stream file to disk instead of loading entirely into memory.
        # This prevents memory pressure for large files (up to 100MB).
        job_dir = ensure_job_dir(job_id)
        input_path = job_dir / "input.pdf"
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(input_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > settings.max_file_mb * 1024 * 1024:
                    f.close()
                    input_path.unlink(missing_ok=True)
                    raise AppException(
                        code=ErrorCode.FILE_TOO_LARGE,
                        message=f"File size exceeds {settings.max_file_mb}MB limit",
                        details={"limit_mb": settings.max_file_mb},
                    )
                f.write(chunk)
        file_size_mb = file_size / (1024 * 1024)

        upload_kind = _write_upload_as_input_pdf(
            filename=filename,
            content_type=normalized_content_type,
            content=None,  # Already written via streaming
            output_path=input_path,
        )

        # Create job in Redis
        user_id = current_user.id if current_user else None

        # Check user quotas before creating job
        if current_user:
            # Check concurrent task limit
            if current_user.concurrent_task_limit > 0:
                active_jobs = redis_service.count_active_jobs_for_user(user_id)
                if active_jobs >= current_user.concurrent_task_limit:
                    raise AppException(
                        code=ErrorCode.QUOTA_EXCEEDED,
                        message=f"Concurrent task limit reached ({current_user.concurrent_task_limit})",
                        details={
                            "limit": current_user.concurrent_task_limit,
                            "active": active_jobs,
                        },
                    )

            # Check daily task limit
            if current_user.daily_task_limit > 0:
                daily_jobs = redis_service.count_daily_jobs_for_user(user_id)
                if daily_jobs >= current_user.daily_task_limit:
                    raise AppException(
                        code=ErrorCode.QUOTA_EXCEEDED,
                        message=f"Daily task limit reached ({current_user.daily_task_limit})",
                        details={
                            "limit": current_user.daily_task_limit,
                            "used": daily_jobs,
                        },
                    )

        job = redis_service.create_job(job_id, user_id=user_id)
        job_created = True

        # Persist queued state before starting worker execution so debug events
        # remain ordered even when a local in-process worker begins immediately.
        redis_service.update_job(
            job_id,
            status=JobStatus.pending,
            stage=JobStage.queued,
            message="Job queued for processing",
        )

        # Store sensitive keys separately in Redis (not in RQ job kwargs)
        # so they don't appear in RQ job descriptions or admin views.
        secrets: dict[str, str] = {}
        if api_key:
            secrets["api_key"] = api_key
        if mineru_api_token:
            secrets["mineru_api_token"] = mineru_api_token
        if ocr_baidu_api_key:
            secrets["ocr_baidu_api_key"] = ocr_baidu_api_key
        if ocr_baidu_secret_key:
            secrets["ocr_baidu_secret_key"] = ocr_baidu_secret_key
        if ocr_ai_api_key:
            secrets["ocr_ai_api_key"] = ocr_ai_api_key
        if secrets:
            redis_service.store_job_secrets(job_id, secrets)

        # Queue job for processing
        _submit_job(
            job_id,
            dict(
                enable_ocr=enable_ocr,
                retain_process_artifacts=retain_process_artifacts,
                remove_footer_notebooklm=remove_footer_notebooklm,
                enable_layout_assist=False,
                layout_assist_apply_image_regions=False,
                provider=normalized_options.provider,
                api_key=None,
                baidu_doc_parse_type=normalized_options.baidu_doc_parse_type,
                base_url=base_url,
                model=model,
                page_start=page_start,
                page_end=page_end,
                parse_provider=normalized_options.parse_provider,
                mineru_api_token=None,
                mineru_base_url=mineru_base_url,
                mineru_model_version=mineru_model_version,
                mineru_enable_formula=mineru_enable_formula,
                mineru_enable_table=mineru_enable_table,
                mineru_language=mineru_language,
                mineru_is_ocr=mineru_is_ocr,
                mineru_hybrid_ocr=False,
                ocr_provider=normalized_options.ocr_provider,
                ocr_baidu_app_id=ocr_baidu_app_id,
                ocr_baidu_api_key=None,
                ocr_baidu_secret_key=None,
                ocr_tesseract_min_confidence=ocr_tesseract_min_confidence,
                ocr_tesseract_language=ocr_tesseract_language,
                ocr_ai_api_key=None,
                ocr_ai_provider=normalized_options.ocr_ai_provider,
                ocr_ai_base_url=ocr_ai_base_url,
                ocr_ai_model=ocr_ai_model,
                ocr_ai_chain_mode=normalized_options.ocr_ai_chain_mode,
                ocr_ai_layout_model=normalized_options.ocr_ai_layout_model,
                ocr_ai_prompt_preset=ocr_ai_prompt_preset,
                ocr_ai_direct_prompt_override=ocr_ai_direct_prompt_override,
                ocr_ai_layout_block_prompt_override=ocr_ai_layout_block_prompt_override,
                ocr_ai_image_region_prompt_override=ocr_ai_image_region_prompt_override,
                ocr_paddle_vl_docparser_max_side_px=ocr_paddle_vl_docparser_max_side_px,
                ocr_ai_page_concurrency=ocr_ai_page_concurrency,
                ocr_ai_block_concurrency=ocr_ai_block_concurrency,
                ocr_ai_requests_per_minute=ocr_ai_requests_per_minute,
                ocr_ai_tokens_per_minute=ocr_ai_tokens_per_minute,
                ocr_ai_max_retries=ocr_ai_max_retries,
                ocr_render_dpi=ocr_render_dpi,
                ocr_geometry_mode="auto",
                text_erase_mode=normalized_options.text_erase_mode,
                scanned_page_mode=normalized_options.scanned_page_mode,
                ppt_generation_mode=normalized_options.ppt_generation_mode,
                image_bg_clear_expand_min_pt=image_bg_clear_expand_min_pt,
                image_bg_clear_expand_max_pt=image_bg_clear_expand_max_pt,
                image_bg_clear_expand_ratio=image_bg_clear_expand_ratio,
                scanned_image_region_min_area_ratio=scanned_image_region_min_area_ratio,
                scanned_image_region_max_area_ratio=scanned_image_region_max_area_ratio,
                scanned_image_region_max_aspect_ratio=scanned_image_region_max_aspect_ratio,
                ocr_ai_linebreak_assist=ocr_ai_linebreak_assist,
                ocr_strict_mode=ocr_strict_mode,
                job_timeout=f"{settings.job_timeout_seconds}s",
            ),
        )

        logger.info("Job %s created and queued from %s upload", job_id, upload_kind)

        return JobCreateResponse(
            job_id=job.job_id,
            status=job.status,
            created_at=job.created_at,
            expires_at=job.expires_at,
        )

    except AppException:
        if not job_created and job_dir is not None and job_dir.exists():
            shutil.rmtree(job_dir)
        raise
    except Exception as e:
        logger.exception(f"Failed to create job: {e}")
        if job_created:
            try:
                redis_service.delete_job(job_id)
            except Exception as cleanup_error:
                logger.exception(
                    "Failed to rollback job metadata for %s: %s",
                    job_id,
                    cleanup_error,
                )
        if job_dir is not None and job_dir.exists():
            shutil.rmtree(job_dir)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to create job",
            details={"error": str(e)},
            status_code=500,
        )


@router.post("/v2", response_model=JobCreateResponse)
async def create_job_v2(
    file: UploadFile = File(..., description="PDF or image file to convert"),
    config: str = Form(..., description="JSON-encoded JobConfig"),
    current_user=Depends(get_current_user_optional),
):
    """
    Create a new PDF/image to PPT conversion job using structured JSON config.

    This is the v2 endpoint that accepts a structured JobConfig body instead
    of 60+ Form() parameters. The structured config is converted to the flat
    kwargs format expected by the worker internally.

    The old POST /api/v1/jobs endpoint with Form() params continues to work
    for backward compatibility.
    """
    import json

    settings = get_settings()
    redis_service = get_redis_service()

    # Parse JSON config string into JobConfig
    try:
        config_data = json.loads(config)
        job_config = JobConfig.model_validate(config_data)
    except json.JSONDecodeError as e:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid JSON in config: {e}",
            status_code=400,
        )
    except Exception as e:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid JobConfig: {e}",
            status_code=400,
        )

    # Convert structured config to flat kwargs for validation and worker
    kwargs = job_config.to_worker_kwargs()

    # Validate using existing validation logic
    normalized_options = validate_and_normalize_job_options(
        parse_provider=kwargs["parse_provider"],
        mineru_api_token=kwargs["mineru_api_token"],
        provider=kwargs["provider"],
        api_key=kwargs["api_key"],
        baidu_doc_parse_type=kwargs["baidu_doc_parse_type"],
        ocr_provider=kwargs["ocr_provider"],
        ocr_ai_provider=kwargs["ocr_ai_provider"],
        ocr_ai_api_key=kwargs["ocr_ai_api_key"],
        ocr_ai_model=kwargs["ocr_ai_model"],
        ocr_ai_chain_mode=kwargs["ocr_ai_chain_mode"],
        ocr_ai_layout_model=kwargs["ocr_ai_layout_model"],
        ocr_baidu_app_id=kwargs["ocr_baidu_app_id"],
        ocr_baidu_api_key=kwargs["ocr_baidu_api_key"],
        ocr_baidu_secret_key=kwargs["ocr_baidu_secret_key"],
        ocr_geometry_mode=kwargs["ocr_geometry_mode"],
        text_erase_mode=kwargs["text_erase_mode"],
        scanned_page_mode=kwargs["scanned_page_mode"],
        ppt_generation_mode=kwargs["ppt_generation_mode"],
        page_start=kwargs["page_start"],
        page_end=kwargs["page_end"],
    )

    # Apply normalized values back to kwargs
    kwargs["parse_provider"] = normalized_options.parse_provider
    kwargs["provider"] = normalized_options.provider
    kwargs["baidu_doc_parse_type"] = normalized_options.baidu_doc_parse_type
    kwargs["ocr_provider"] = normalized_options.ocr_provider
    kwargs["ocr_ai_provider"] = normalized_options.ocr_ai_provider
    kwargs["ocr_ai_chain_mode"] = normalized_options.ocr_ai_chain_mode
    kwargs["ocr_ai_layout_model"] = normalized_options.ocr_ai_layout_model
    kwargs["ocr_geometry_mode"] = normalized_options.ocr_geometry_mode
    kwargs["text_erase_mode"] = normalized_options.text_erase_mode
    kwargs["scanned_page_mode"] = normalized_options.scanned_page_mode
    kwargs["ppt_generation_mode"] = normalized_options.ppt_generation_mode

    # v2 legacy compatibility check
    parse_provider_id = normalized_options.parse_provider
    if parse_provider_id == "v2":
        has_v2_key = (
            bool((kwargs.get("api_key") or "").strip())
            or bool((kwargs.get("ocr_ai_api_key") or "").strip())
        )
        if not has_v2_key:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message=(
                    "api_key or ocr_ai_api_key is required when parse_provider=v2"
                ),
            )

    # Check disk space before accepting upload
    import shutil as _shutil
    _job_root = Path(settings.job_root_dir)
    _job_root.mkdir(parents=True, exist_ok=True)
    _disk = _shutil.disk_usage(_job_root)
    _min_bytes = settings.min_disk_space_mb * 1024 * 1024
    if _disk.free < _min_bytes:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"磁盘空间不足，剩余 {_disk.free // (1024*1024)}MB，需要至少 {settings.min_disk_space_mb}MB",
            details={
                "free_mb": _disk.free // (1024 * 1024),
                "required_mb": settings.min_disk_space_mb,
            },
        )

    # Generate job ID
    job_id = str(uuid.uuid4())
    job_dir: Path | None = None
    job_created = False

    try:
        # Handle file upload
        filename = file.filename or ""
        normalized_content_type = _normalize_upload_content_type(file.content_type)
        upload_kind = _classify_upload_kind(
            filename=filename,
            content_type=normalized_content_type,
        )
        if upload_kind is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Only PDF, PNG, JPG, JPEG, and WEBP files are supported",
                details={
                    "filename": file.filename,
                    "content_type": normalized_content_type,
                },
            )

        # Stream file to disk instead of loading entirely into memory.
        # This prevents memory pressure for large files (up to 100MB).
        job_dir = ensure_job_dir(job_id)
        input_path = job_dir / "input.pdf"
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(input_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > settings.max_file_mb * 1024 * 1024:
                    f.close()
                    input_path.unlink(missing_ok=True)
                    raise AppException(
                        code=ErrorCode.FILE_TOO_LARGE,
                        message=f"File size exceeds {settings.max_file_mb}MB limit",
                        details={"limit_mb": settings.max_file_mb},
                    )
                f.write(chunk)
        file_size_mb = file_size / (1024 * 1024)

        upload_kind = _write_upload_as_input_pdf(
            filename=filename,
            content_type=normalized_content_type,
            content=None,  # Already written via streaming
            output_path=input_path,
        )

        # Create job in Redis
        user_id = current_user.id if current_user else None

        # Check user quotas before creating job
        if current_user:
            # Check concurrent task limit
            if current_user.concurrent_task_limit > 0:
                active_jobs = redis_service.count_active_jobs_for_user(user_id)
                if active_jobs >= current_user.concurrent_task_limit:
                    raise AppException(
                        code=ErrorCode.QUOTA_EXCEEDED,
                        message=f"Concurrent task limit reached ({current_user.concurrent_task_limit})",
                        details={
                            "limit": current_user.concurrent_task_limit,
                            "active": active_jobs,
                        },
                    )

            # Check daily task limit
            if current_user.daily_task_limit > 0:
                daily_jobs = redis_service.count_daily_jobs_for_user(user_id)
                if daily_jobs >= current_user.daily_task_limit:
                    raise AppException(
                        code=ErrorCode.QUOTA_EXCEEDED,
                        message=f"Daily task limit reached ({current_user.daily_task_limit})",
                        details={
                            "limit": current_user.daily_task_limit,
                            "used": daily_jobs,
                        },
                    )

        job = redis_service.create_job(job_id, user_id=user_id)
        job_created = True

        # Persist queued state
        redis_service.update_job(
            job_id,
            status=JobStatus.pending,
            stage=JobStage.queued,
            message="Job queued for processing",
        )

        # Store sensitive keys separately in Redis (not in RQ job kwargs)
        secrets: dict[str, str] = {}
        for key_name in ("api_key", "mineru_api_token", "ocr_baidu_api_key", "ocr_baidu_secret_key", "ocr_ai_api_key"):
            val = kwargs.get(key_name)
            if val:
                secrets[key_name] = str(val)
        if secrets:
            redis_service.store_job_secrets(job_id, secrets)

        # Remove sensitive keys from kwargs before passing to worker
        for key_name in ("api_key", "mineru_api_token", "ocr_baidu_api_key", "ocr_baidu_secret_key", "ocr_ai_api_key"):
            kwargs.pop(key_name, None)

        # Add job_timeout to kwargs
        kwargs["job_timeout"] = f"{settings.job_timeout_seconds}s"

        # Queue job for processing
        _submit_job(job_id, kwargs)

        logger.info("Job %s created and queued via v2 endpoint", job_id)

        return JobCreateResponse(
            job_id=job.job_id,
            status=job.status,
            created_at=job.created_at,
            expires_at=job.expires_at,
        )

    except AppException:
        if not job_created and job_dir is not None and job_dir.exists():
            shutil.rmtree(job_dir)
        raise
    except Exception as e:
        logger.exception(f"Failed to create job via v2 endpoint: {e}")
        if job_created:
            try:
                redis_service.delete_job(job_id)
            except Exception as cleanup_error:
                logger.exception(
                    "Failed to rollback job metadata for %s: %s",
                    job_id,
                    cleanup_error,
                )
        if job_dir is not None and job_dir.exists():
            shutil.rmtree(job_dir)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to create job",
            details={"error": str(e)},
            status_code=500,
        )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user=Depends(get_current_user_optional),
):
    """
    Get current status of a job.

    Returns job metadata including status, stage, and progress.
    """
    redis_service = get_redis_service()
    job = redis_service.get_job(job_id)

    if not job:
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job {job_id} not found",
            status_code=404,
        )

    # Check ownership: users can only view their own jobs
    if current_user and job.user_id and job.user_id != current_user.id:
        raise AppException(
            code=ErrorCode.FORBIDDEN,
            message="You can only view your own jobs",
            status_code=403,
        )

    return JobStatusResponse(
        job_id=job.job_id,
        user_id=job.user_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        created_at=job.created_at,
        expires_at=job.expires_at,
        message=job.message,
        error=job.error,
        debug_events=job.debug_events,
    )


async def job_event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for job progress.

    Polls Redis for job updates and yields SSE-formatted events.
    """
    redis_service = get_redis_service()

    # Check if job exists
    job = redis_service.get_job(job_id)
    if not job:
        event = JobEvent(
            job_id=job_id,
            status=JobStatus.failed,
            stage=JobStage.upload_received,
            progress=0,
            error={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Job not found"},
        )
        yield f"data: {event.model_dump_json()}\n\n"
        return

    last_status = None
    last_stage = None
    last_progress = None
    last_message = None

    while True:
        job = redis_service.get_job(job_id)

        if not job:
            # Job expired or deleted
            break

        # Send update if anything changed
        if (
            job.status != last_status
            or job.stage != last_stage
            or job.progress != last_progress
            or job.message != last_message
        ):
            event = JobEvent(
                job_id=job.job_id,
                status=job.status,
                stage=job.stage,
                progress=job.progress,
                message=job.message,
                error=job.error,
            )
            yield f"data: {event.model_dump_json()}\n\n"

            last_status = job.status
            last_stage = job.stage
            last_progress = job.progress
            last_message = job.message

        # Stop streaming if job is in terminal state
        if job.status in [JobStatus.completed, JobStatus.failed, JobStatus.cancelled]:
            break

        # Poll every 500ms
        await asyncio.sleep(0.5)


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    current_user=Depends(get_current_user_optional),
):
    """
    Stream job progress events via Server-Sent Events (SSE).

    Clients can connect to this endpoint to receive real-time updates
    about job status, stage, and progress.

    Access control:
    - Authenticated users can only stream their own jobs
    - Jobs without an owner are publicly accessible
    - Unauthenticated access to owned jobs returns 401
    """
    # Perform ownership check before starting the stream
    redis_service = get_redis_service()
    job = redis_service.get_job(job_id)
    if job:
        if current_user and job.user_id and job.user_id != current_user.id:
            raise AppException(
                code=ErrorCode.FORBIDDEN,
                message="You can only access your own jobs",
                status_code=403,
            )
        if not current_user and job.user_id:
            raise AppException(
                code=ErrorCode.AUTH_REQUIRED,
                message="Authentication required to access this job",
                status_code=401,
            )

    return StreamingResponse(
        job_event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user=Depends(get_current_user_optional),
):
    """
    Cancel a running job.

    Mirrors cancellation into Redis and RQ so queued/running jobs can release
    worker capacity promptly.
    """
    redis_service = get_redis_service()

    job = redis_service.get_job(job_id)
    if not job:
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job {job_id} not found",
            status_code=404,
        )

    # Check ownership: users can only cancel their own jobs
    if current_user and job.user_id and job.user_id != current_user.id:
        raise AppException(
            code=ErrorCode.FORBIDDEN,
            message="You can only cancel your own jobs",
            status_code=403,
        )

    # Can only cancel pending or processing jobs
    if job.status not in [JobStatus.pending, JobStatus.processing]:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Cannot cancel job in {job.status} state",
            details={"status": job.status},
        )

    _sync_rq_cancel_state(job_id=job_id, status=job.status)

    # Set cancellation flag
    redis_service.set_cancel_flag(job_id)

    # Update job status
    redis_service.update_job(
        job_id,
        status=JobStatus.cancelled,
        stage=job.stage,
        progress=100,
        message="Job cancellation requested",
    )

    logger.info(f"Job {job_id} cancellation requested")

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Cancellation requested",
    }


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    current_user=Depends(get_current_user_optional),
):
    """Delete terminal job metadata and on-disk artifacts."""
    redis_service = get_redis_service()
    job = redis_service.get_job(job_id)
    job_dir = get_job_dir(job_id)

    if not job and not job_dir.exists():
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job {job_id} not found",
            status_code=404,
        )

    # Check ownership: users can only delete their own jobs
    if current_user and job and job.user_id and job.user_id != current_user.id:
        raise AppException(
            code=ErrorCode.FORBIDDEN,
            message="You can only delete your own jobs",
            status_code=403,
        )

    if job and job.status in [JobStatus.pending, JobStatus.processing]:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Cannot delete an active job; cancel it first",
            details={"status": job.status},
            status_code=400,
        )

    artifacts_deleted = False
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
            artifacts_deleted = True
        except Exception as e:
            logger.exception("Failed to delete job artifacts for %s: %s", job_id, e)
            raise AppException(
                code=ErrorCode.INTERNAL_ERROR,
                message="Failed to delete job artifacts",
                details={"job_id": job_id, "error": str(e)},
                status_code=500,
            ) from e

    redis_service.delete_job(job_id)
    logger.info(
        "Deleted job %s (had_metadata=%s, artifacts_deleted=%s)",
        job_id,
        bool(job),
        artifacts_deleted,
    )

    return {
        "job_id": job_id,
        "status": "deleted",
        "artifacts_deleted": artifacts_deleted,
    }


@router.get("/{job_id}/download")
async def download_result(job_id: str):
    """
    Download the converted PowerPoint file.

    Only available for completed jobs.
    """
    redis_service = get_redis_service()
    job = redis_service.get_job(job_id)
    if not job:
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job {job_id} not found",
            status_code=404,
        )

    if job.status != JobStatus.completed:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Job is not completed (status: {job.status})",
            details={"status": job.status},
        )

    output_path = get_job_dir(job_id) / "output.pptx"
    if output_path.exists():
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"converted_{job_id}.pptx",
        )

    # Job metadata exists and indicates completion, but output is missing.
    raise AppException(
        code=ErrorCode.INTERNAL_ERROR,
        message="Output file not found",
        status_code=500,
    )


@router.get("/{job_id}/artifacts", response_model=JobArtifactsResponse)
async def get_job_artifacts(job_id: str):
    """Return artifact image manifest for tracking/debug UI."""
    redis_service = get_redis_service()
    job = redis_service.get_job(job_id)
    job_dir = get_job_dir(job_id)
    if not job and not job_dir.exists():
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job {job_id} not found",
            status_code=404,
        )

    prefix = f"/api/v1/jobs/{job_id}/artifacts"
    artifacts_root = job_dir / "artifacts"
    source_pdf_rel = "input.pdf"
    source_pdf_path = job_dir / source_pdf_rel
    source_pdf_url = (
        f"{prefix}/file?path={quote(source_pdf_rel)}"
        if source_pdf_path.exists()
        else None
    )

    original_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/page_renders",
        regex=r"^page-(\d{4})\.png$",
        url_prefix=prefix,
    )
    cleaned_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/page_renders",
        regex=r"^page-(\d{4})\.(?:mineru\.)?clean\.png$",
        url_prefix=prefix,
    )
    final_preview_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/final_preview",
        regex=r"^page-(\d{4})\.final\.png$",
        url_prefix=prefix,
    )
    ocr_overlay_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/ocr",
        regex=r"^page-(\d{4})\.overlay\.png$",
        url_prefix=prefix,
    )
    layout_before_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/layout_assist",
        regex=r"^page-(\d{4})\.before\.png$",
        url_prefix=prefix,
    )
    layout_after_images = _collect_page_images(
        job_dir=job_dir,
        subdir="artifacts/layout_assist",
        regex=r"^page-(\d{4})\.after\.png$",
        url_prefix=prefix,
    )

    all_pages = sorted(
        {
            *[img.page_index for img in original_images],
            *[img.page_index for img in cleaned_images],
            *[img.page_index for img in final_preview_images],
            *[img.page_index for img in ocr_overlay_images],
            *[img.page_index for img in layout_before_images],
            *[img.page_index for img in layout_after_images],
        }
    )

    return JobArtifactsResponse(
        job_id=job_id,
        status=job.status if job else None,
        artifacts_retained=artifacts_root.exists(),
        source_pdf_url=source_pdf_url,
        original_images=original_images,
        cleaned_images=cleaned_images,
        final_preview_images=final_preview_images,
        ocr_overlay_images=ocr_overlay_images,
        layout_before_images=layout_before_images,
        layout_after_images=layout_after_images,
        available_pages=all_pages,
    )


@router.get("/{job_id}/artifacts/file")
async def get_job_artifact_file(
    job_id: str, path: str = Query(..., description="Artifact path relative to job dir")
):
    """Read a single artifact file by relative path."""
    target = _safe_artifact_path(job_id, path)
    return FileResponse(path=target)
