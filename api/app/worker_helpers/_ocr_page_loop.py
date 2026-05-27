"""Sequential OCR page-processing loop (split from ocr_stage.py)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import pymupdf

from ..convert.rendered_page import RenderedPage
from ..convert.ocr import ocr_image_to_elements
from ..logging_config import get_logger
from ..models.error import AppException, ErrorCode
from ..models.job import JobStage
from ..utils.concurrency import run_in_daemon_thread_with_timeout

from ._ocr_parallel import _detect_page_image_regions, _maybe_export_ocr_overlay_image
from ._ocr_progress import _format_ocr_progress_message, _progress_in_span

logger = get_logger(__name__)


def _run_sequential_ocr_page_loop(
    *,
    ir: dict[str, Any],
    ocr_debug: dict[str, Any],
    doc: pymupdf.Document,
    ocr_dir: Path,
    ocr_manager: Any,
    text_refiner: Any | None,
    linebreak_refiner: Any | None,
    linebreak_assist_effective: bool | None,
    strict_no_fallback: bool,
    effective_ocr_provider: str,
    ocr_render_dpi: int,
    ocr_page_timeout: int,
    ocr_image_region_timeout: int,
    ocr_timeout_break_after: int,
    skip_image_region_detection: bool,
    export_overlay_images: bool,
    image_region_detection_skip_reason: str | None,
    ocr_stage_deadline: float,
    ocr_total_timeout: int,
    source_page_count: int,
    set_processing_progress: Callable[[Any, int, str], None],
    abort_if_cancelled: Callable[..., None],
) -> None:
    ocr_page_targets = sum(
        1
        for page in (ir.get("pages") or [])
        if isinstance(page, dict) and not page.get("has_text_layer")
    )
    ocr_page_processed = 0
    ocr_consecutive_timeouts = 0
    ocr_timeout_break_after = max(1, ocr_timeout_break_after)

    for page in ir.get("pages") or []:
        abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
        # --- overall OCR stage timeout ---
        if time.monotonic() >= ocr_stage_deadline:
            logger.warning(
                "OCR stage timeout (%ss) exceeded – skipping remaining pages",
                ocr_total_timeout,
            )
            break
        if not isinstance(page, dict):
            continue
        if page.get("has_text_layer"):
            ocr_debug["pages"].append(
                {
                    "page_index": page.get("page_index"),
                    "skipped": "has_text_layer",
                }
            )
            continue

        ocr_page_processed += 1
        page_index = int(page.get("page_index") or 0)
        progress_value = _progress_in_span(
            ocr_page_processed - 1,
            max(1, ocr_page_targets),
            start=36,
            end=68,
        )
        set_processing_progress(
            JobStage.ocr,
            progress_value,
            _format_ocr_progress_message(
                ocr_page_processed=ocr_page_processed,
                ocr_page_targets=ocr_page_targets,
                pdf_page_index=page_index,
                source_page_count=source_page_count,
                overall_progress=progress_value,
            ),
        )
        abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")

        page_w_pt = float(page.get("page_width_pt") or 0)
        page_h_pt = float(page.get("page_height_pt") or 0)
        if page_w_pt <= 0 or page_h_pt <= 0:
            ocr_debug["pages"].append(
                {
                    "page_index": page_index,
                    "skipped": "invalid_dimensions",
                    "page_width_pt": page_w_pt,
                    "page_height_pt": page_h_pt,
                }
            )
            continue

        try:
            pdf_page = doc.load_page(page_index)
            pix = pdf_page.get_pixmap(dpi=int(ocr_render_dpi), alpha=False)
        except Exception as e:
            logger.warning("Failed to render OCR page %s: %s", page_index, e)
            ocr_debug["pages"].append(
                {
                    "page_index": page_index,
                    "error": f"render_failed: {e!s}",
                }
            )
            continue

        rendered = RenderedPage(pix, page_index)
        image_path = rendered.as_tempfile_path(ocr_dir)

        fallback_reason: str | None = None
        ocr_call_started = time.perf_counter()
        route_kind = getattr(ocr_manager, "route_kind", None)
        logger.info(
            "Starting OCR page (ocr_page=%s/%s, pdf_page=%s/%s, provider=%s, route=%s, timeout_s=%s, image=%s)",
            ocr_page_processed,
            max(1, ocr_page_targets),
            page_index + 1,
            max(1, source_page_count),
            effective_ocr_provider,
            route_kind,
            ocr_page_timeout,
            image_path.name,
        )

        try:
            abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            ocr_elements = run_in_daemon_thread_with_timeout(
                lambda: ocr_image_to_elements(
                    str(image_path),
                    page_width_pt=page_w_pt,
                    page_height_pt=page_h_pt,
                    ocr_manager=ocr_manager,
                    text_refiner=text_refiner,
                    linebreak_refiner=linebreak_refiner,
                    linebreak_assist=linebreak_assist_effective,
                    strict_no_fallback=bool(strict_no_fallback),
                    rendered_page=rendered,
                ),
                timeout_s=float(ocr_page_timeout),
                label=f"worker:ocr_page:{page_index}",
            )
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            details = f"{e!s}"
            if cause is not None:
                details = f"{details}; cause={cause!s}"
            provider_choice = effective_ocr_provider
            logger.warning(
                "OCR failed for page %s (provider=%s): %s",
                page_index,
                provider_choice,
                details,
            )

            details_lower = details.lower()
            strict_now = bool(strict_no_fallback)
            is_timeout_error = isinstance(e, TimeoutError) or (
                "timeout" in details_lower or "timed out" in details_lower
            )
            if is_timeout_error and not strict_now:
                ocr_consecutive_timeouts += 1
                page.setdefault("warnings", []).append(
                    "ocr_timeout_best_effort: "
                    f"provider={provider_choice}, page={page_index + 1}, "
                    f"consecutive={ocr_consecutive_timeouts}"
                )
                ocr_debug["pages"].append(
                    {
                        "page_index": page_index,
                        "warning": "ocr_timeout",
                        "provider": provider_choice,
                        "consecutive_timeouts": ocr_consecutive_timeouts,
                        "error": details,
                    }
                )
                if ocr_consecutive_timeouts >= ocr_timeout_break_after:
                    timeout_warning = (
                        "ocr_timeout_circuit_open: "
                        f"consecutive={ocr_consecutive_timeouts}, "
                        f"page_timeout_s={ocr_page_timeout}"
                    )
                    ir.setdefault("warnings", []).append(timeout_warning)
                    logger.warning(
                        "OCR timeout circuit open after %s consecutive timeout(s); "
                        "skipping remaining OCR pages",
                        ocr_consecutive_timeouts,
                    )
                    break
                continue
            ocr_consecutive_timeouts = 0

            nonfatal_empty_ocr = any(
                marker in details_lower
                for marker in (
                    "ai ocr returned no items",
                    "ai ocr returned empty elements",
                    "ai ocr returned no parseable items",
                )
            )

            if nonfatal_empty_ocr:
                if strict_now:
                    raise AppException(
                        code=ErrorCode.OCR_FAILED,
                        message=(
                            f"{provider_choice.upper()} returned empty OCR result on page {page_index + 1}"
                        ),
                        details={
                            "page_index": page_index,
                            "provider": provider_choice,
                            "reason": details,
                        },
                    )
                logger.warning(
                    "OCR returned empty result on page %s (provider=%s); keep background-only page",
                    page_index,
                    provider_choice,
                )
                page.setdefault("warnings", []).append(
                    f"ocr_empty_result: provider={provider_choice}, page={page_index + 1}"
                )
                ocr_debug["pages"].append(
                    {
                        "page_index": page_index,
                        "warning": "ocr_empty_result",
                        "provider": provider_choice,
                        "error": details,
                    }
                )
                continue

            if strict_now:
                provider_label = provider_choice.upper()
                raise AppException(
                    code=ErrorCode.OCR_FAILED,
                    message=f"{provider_label} failed on page {page_index + 1}: {details}",
                    details={
                        "page_index": page_index,
                        "provider": provider_choice,
                        "reason": details,
                    },
                )

            ocr_debug["pages"].append(
                {
                    "page_index": page_index,
                    "error": f"ocr_failed: {details}",
                }
            )
            page.setdefault("warnings", []).append(
                f"ocr_failed_best_effort: provider={provider_choice}, page={page_index + 1}"
            )
            continue
        elapsed_ms = int(
            round(max(0.0, time.perf_counter() - ocr_call_started) * 1000.0)
        )
        logger.info(
            "Finished OCR page (ocr_page=%s/%s, pdf_page=%s/%s, provider=%s, route=%s, elapsed_ms=%s, elements=%s)",
            ocr_page_processed,
            max(1, ocr_page_targets),
            page_index + 1,
            max(1, source_page_count),
            effective_ocr_provider,
            route_kind,
            elapsed_ms,
            len(ocr_elements or []),
        )

        ocr_consecutive_timeouts = 0
        used_provider = getattr(ocr_manager, "last_provider_name", None)
        fallback_reason = getattr(
            ocr_manager,
            "last_fallback_reason",
            fallback_reason,
        )
        layout_blocks = getattr(ocr_manager, "last_layout_blocks", [])
        layout_analysis_debug = getattr(
            ocr_manager, "last_layout_analysis_debug", None
        )
        quality_notes_raw = getattr(ocr_manager, "last_quality_notes", [])
        quality_notes = [
            str(note).strip()
            for note in (
                quality_notes_raw if isinstance(quality_notes_raw, list) else []
            )
            if str(note).strip()
        ]
        for note in quality_notes:
            page.setdefault("warnings", []).append(note)
            ir.setdefault("warnings", []).append(f"{note}:page={page_index + 1}")

        detected_image_regions_pt, image_region_error, image_region_skip_reason = (
            _detect_page_image_regions(
                enabled=not bool(skip_image_region_detection),
                image_path=image_path,
                ocr_manager=ocr_manager,
                page_index=page_index,
                ocr_image_region_timeout=int(ocr_image_region_timeout),
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
                skip_reason=image_region_detection_skip_reason,
                rendered_page=rendered,
            )
        )

        if detected_image_regions_pt:
            page["image_regions"] = detected_image_regions_pt

        overlay_path, bbox_stats = _maybe_export_ocr_overlay_image(
            enabled=export_overlay_images,
            image_path=image_path,
            ocr_dir=ocr_dir,
            page_index=page_index,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            ocr_elements=ocr_elements if isinstance(ocr_elements, list) else None,
            rendered_page=rendered,
        )
        if ocr_elements:
            page.setdefault("elements", []).extend(ocr_elements)
            page["ocr_used"] = True
        ocr_debug["pages"].append(
            {
                "page_index": page_index,
                "elements": len(ocr_elements or []),
                "image_regions": len(detected_image_regions_pt),
                "image_region_detection_error": image_region_error,
                "image_region_detection_skipped": bool(image_region_skip_reason),
                "image_region_detection_skip_reason": image_region_skip_reason,
                "used_provider": used_provider,
                "fallback_reason": fallback_reason,
                "quality_notes": quality_notes,
                "layout_block_count": len(layout_blocks or []),
                "layout_analysis": layout_analysis_debug,
                "overlay_image": str(overlay_path) if overlay_path else None,
                "bbox_stats": bbox_stats,
            }
        )

    set_processing_progress(
        JobStage.ocr,
        68,
        f"OCR 阶段完成（已处理 {ocr_page_processed}/{max(1, ocr_page_targets)} 页）",
    )
    abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
