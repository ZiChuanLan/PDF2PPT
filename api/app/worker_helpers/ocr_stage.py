"""OCR stage orchestration — entry point and stage management.

Split from a monolithic file into:
- _ocr_progress.py   – progress tracking helpers
- _ocr_parallel.py   – parallel AI OCR page processing
- _ocr_page_loop.py  – sequential OCR page-processing loop
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import pymupdf

from ..logging_config import get_logger
from ..models.job import JobStage
from ._ocr_page_loop import _run_sequential_ocr_page_loop
from ._ocr_parallel import (  # noqa: F401
    _convert_geometry_points_px_to_pt,  # noqa: F401
    _convert_image_region_px_to_pt,  # noqa: F401
    _detect_page_image_regions,  # noqa: F401
    _maybe_export_ocr_overlay_image,  # noqa: F401
    _process_parallel_ai_ocr_page,  # noqa: F401
    _run_parallel_ocr_executor,
)
from ._ocr_progress import (  # noqa: F401
    _format_ocr_progress_message,  # noqa: F401
    _format_parallel_ocr_progress_message,
    _progress_in_span,  # noqa: F401
    _summarize_ocr_page_runtime,
)
from .debug import _build_ocr_effective_runtime_debug

logger = get_logger(__name__)


def run_ocr_stage(
    *,
    ir: dict[str, Any],
    input_pdf: Path,
    job_path: Path,
    artifacts_dir: Path,
    settings: Any,
    ocr_manager: Any,
    text_refiner: Any | None,
    linebreak_refiner: Any | None,
    linebreak_assist_effective: bool | None,
    strict_no_fallback: bool,
    effective_ocr_provider: str,
    ocr_render_dpi: int,
    ocr_debug: dict[str, Any],
    export_overlay_images: bool,
    skip_image_region_detection: bool = False,
    set_processing_progress: Callable[[JobStage, int, str], None],
    abort_if_cancelled: Callable[..., None],
    ocr_setup: Any | None = None,
    ocr_runtime_factory: Callable[[], Any] | None = None,
) -> None:
    ocr_dir = artifacts_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    ocr_debug.setdefault("pages", [])
    ocr_debug["runtime"] = _build_ocr_effective_runtime_debug(
        ocr_manager=ocr_manager,
        fallback_provider=ocr_debug.get("provider_effective"),
    )
    image_region_detection_skip_reason = (
        "fast_ppt_generation_mode" if bool(skip_image_region_detection) else None
    )
    ocr_debug["runtime"]["image_region_detection_enabled"] = bool(
        not skip_image_region_detection
    )
    ocr_debug["runtime"]["image_region_detection_skip_reason"] = (
        image_region_detection_skip_reason
    )
    try:
        import shutil

        ocr_debug["which_tesseract"] = shutil.which("tesseract")
    except Exception as e:
        ocr_debug["which_tesseract"] = f"error: {e!s}"
    try:
        import pytesseract

        ocr_debug["pytesseract_cmd"] = getattr(
            getattr(pytesseract, "pytesseract", None),
            "tesseract_cmd",
            None,
        )
    except Exception as e:
        ocr_debug["pytesseract_cmd"] = f"error: {e!s}"

    doc = pymupdf.open(str(input_pdf))
    ocr_page_timeout = int(getattr(settings, "ocr_page_timeout_s", 300) or 300)
    ocr_total_timeout = int(getattr(settings, "ocr_total_timeout_s", 3600) or 3600)
    ocr_image_region_timeout = int(
        getattr(settings, "ocr_image_region_timeout_s", 12) or 12
    )
    ocr_timeout_break_after = int(
        getattr(settings, "ocr_max_consecutive_timeouts", 2) or 2
    )
    ocr_stage_deadline = time.monotonic() + ocr_total_timeout
    source_page_count = int(
        ir.get("source_page_count")
        or ir.get("page_count")
        or len(ir.get("pages") or [])
        or 0
    )
    route_kind = str(getattr(ocr_manager, "route_kind", "") or "")
    page_concurrency = max(
        1,
        int(
            getattr(ocr_setup, "effective_ocr_ai_page_concurrency", 1)
            if ocr_setup is not None
            else 1
        ),
    )
    use_parallel_ai_ocr = (
        page_concurrency > 1
        and str(effective_ocr_provider or "").strip().lower() == "aiocr"
        and route_kind in {"remote_prompt_ocr", "local_layout_block_ocr"}
        and callable(ocr_runtime_factory)
    )
    try:
        if use_parallel_ai_ocr:
            ocr_pages = [
                page
                for page in (ir.get("pages") or [])
                if isinstance(page, dict) and not page.get("has_text_layer")
            ]
            _run_parallel_ocr_executor(
                ocr_pages=ocr_pages,
                ir=ir,
                ocr_debug=ocr_debug,
                input_pdf=input_pdf,
                ocr_dir=ocr_dir,
                ocr_runtime_factory=ocr_runtime_factory,
                linebreak_assist_effective=linebreak_assist_effective,
                ocr_render_dpi=int(ocr_render_dpi),
                ocr_page_timeout=int(ocr_page_timeout),
                ocr_image_region_timeout=int(ocr_image_region_timeout),
                skip_image_region_detection=bool(skip_image_region_detection),
                export_overlay_images=bool(export_overlay_images),
                ocr_stage_deadline=ocr_stage_deadline,
                ocr_total_timeout=ocr_total_timeout,
                page_concurrency=page_concurrency,
                source_page_count=source_page_count,
                set_processing_progress=set_processing_progress,
                abort_if_cancelled=abort_if_cancelled,
            )

            set_processing_progress(
                JobStage.ocr,
                68,
                "OCR 阶段完成（并发模式）",
            )
            abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            return

        _run_sequential_ocr_page_loop(
            ir=ir,
            ocr_debug=ocr_debug,
            doc=doc,
            ocr_dir=ocr_dir,
            ocr_manager=ocr_manager,
            text_refiner=text_refiner,
            linebreak_refiner=linebreak_refiner,
            linebreak_assist_effective=linebreak_assist_effective,
            strict_no_fallback=bool(strict_no_fallback),
            effective_ocr_provider=effective_ocr_provider,
            ocr_render_dpi=int(ocr_render_dpi),
            ocr_page_timeout=int(ocr_page_timeout),
            ocr_image_region_timeout=int(ocr_image_region_timeout),
            ocr_timeout_break_after=max(1, ocr_timeout_break_after),
            skip_image_region_detection=bool(skip_image_region_detection),
            export_overlay_images=bool(export_overlay_images),
            image_region_detection_skip_reason=image_region_detection_skip_reason,
            ocr_stage_deadline=ocr_stage_deadline,
            ocr_total_timeout=ocr_total_timeout,
            source_page_count=source_page_count,
            set_processing_progress=set_processing_progress,
            abort_if_cancelled=abort_if_cancelled,
        )
    finally:
        doc.close()
        page_runtime_summary = _summarize_ocr_page_runtime(
            page_entries=ocr_debug.get("pages")
            if isinstance(ocr_debug.get("pages"), list)
            else [],
            ocr_manager=ocr_manager,
        )
        ocr_debug["page_runtime_summary"] = page_runtime_summary
        runtime_debug = _build_ocr_effective_runtime_debug(
            ocr_manager=ocr_manager,
            fallback_provider=ocr_debug.get("provider_effective"),
        )
        runtime_debug["page_summary"] = page_runtime_summary
        ocr_debug["runtime"] = runtime_debug

        if page_runtime_summary["distinct_provider_count"] > 1:
            providers = ",".join(sorted(page_runtime_summary["provider_counts"]))
            ir.setdefault("warnings", []).append(
                f"ocr_page_provider_switches: providers={providers}"
            )
        if page_runtime_summary["fallback_pages"] > 0:
            ir.setdefault("warnings", []).append(
                "ocr_page_fallbacks:"
                f" pages={page_runtime_summary['fallback_pages']}"
                f" reasons={json.dumps(page_runtime_summary['fallback_reason_counts'], ensure_ascii=True, sort_keys=True)}"
            )
        if page_runtime_summary["ai_provider_disabled"]:
            ir.setdefault("warnings", []).append(
                "ocr_ai_provider_disabled:"
                f" reason={page_runtime_summary['ai_provider_disabled_reason'] or 'unknown'}"
            )

        (ocr_dir / "ocr_debug.json").write_text(
            json.dumps(ocr_debug, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        # Persist IR after OCR for debugging.
        (job_path / "ir.ocr.json").write_text(
            json.dumps(ir, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
