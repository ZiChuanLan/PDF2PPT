"""Parallel AI OCR page processing (split from ocr_stage.py)."""

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

from ._ocr_progress import _format_parallel_ocr_progress_message, _progress_in_span

logger = get_logger(__name__)


def _convert_geometry_points_px_to_pt(
    geometry_points: Any,
    *,
    image_width_px: int,
    image_height_px: int,
    page_w_pt: float,
    page_h_pt: float,
) -> list[list[float]] | None:
    if not isinstance(geometry_points, (list, tuple)):
        return None
    if image_width_px <= 0 or image_height_px <= 0:
        return None

    scale_x = float(page_w_pt) / float(image_width_px)
    scale_y = float(page_h_pt) / float(image_height_px)
    converted: list[list[float]] = []
    for point in geometry_points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            x = float(point[0])
            y = float(point[1])
        except Exception:
            return None
        converted.append([x * scale_x, y * scale_y])
    if len(converted) < 3:
        return None
    return converted


def _convert_image_region_px_to_pt(
    *,
    raw_region: Any,
    ocr_manager: Any,
    image_width_px: int,
    image_height_px: int,
    page_w_pt: float,
    page_h_pt: float,
) -> Any | None:
    raw_bbox = raw_region.get("bbox") if isinstance(raw_region, dict) else raw_region
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None

    try:
        bbox_pt = ocr_manager.convert_bbox_to_pdf_coords(
            bbox=list(raw_bbox),
            image_width=int(image_width_px),
            image_height=int(image_height_px),
            page_width_pt=page_w_pt,
            page_height_pt=page_h_pt,
        )
    except Exception:
        return None

    if not isinstance(raw_region, dict):
        return list(bbox_pt)

    converted: dict[str, Any] = {"bbox_pt": list(bbox_pt)}
    for key in ("label", "score", "order", "geometry_source"):
        if raw_region.get(key) is not None:
            converted[key] = raw_region.get(key)

    geometry_kind = str(raw_region.get("geometry_kind") or "").strip().lower()
    geometry_points_pt = _convert_geometry_points_px_to_pt(
        raw_region.get("geometry_points"),
        image_width_px=int(image_width_px),
        image_height_px=int(image_height_px),
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
    )
    if geometry_points_pt is not None:
        converted["geometry_kind"] = "polygon"
        converted["geometry_points_pt"] = geometry_points_pt
    elif geometry_kind:
        converted["geometry_kind"] = geometry_kind

    return converted


def _detect_page_image_regions(
    *,
    enabled: bool,
    image_path: Path,
    ocr_manager: Any,
    page_index: int,
    ocr_image_region_timeout: int,
    page_w_pt: float,
    page_h_pt: float,
    skip_reason: str | None = None,
    rendered_page: RenderedPage | None = None,
) -> tuple[list[Any], str | None, str | None]:
    if not enabled:
        return [], None, (skip_reason or "disabled")

    detected_image_regions_pt: list[Any] = []
    image_region_error: str | None = None
    try:
        if rendered_page is not None:
            image_width_px = rendered_page.width
            image_height_px = rendered_page.height
        else:
            from PIL import Image

            with Image.open(image_path) as img_probe:
                image_width_px, image_height_px = img_probe.size

        detected_image_regions_px = run_in_daemon_thread_with_timeout(
            lambda: ocr_manager.detect_image_regions(str(image_path)),
            timeout_s=float(max(1, ocr_image_region_timeout)),
            label=f"worker:ocr_image_regions:{page_index}",
        )
        for raw_region in detected_image_regions_px or []:
            converted = _convert_image_region_px_to_pt(
                raw_region=raw_region,
                ocr_manager=ocr_manager,
                image_width_px=int(image_width_px),
                image_height_px=int(image_height_px),
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
            )
            if converted is not None:
                detected_image_regions_pt.append(converted)
    except TimeoutError:
        image_region_error = (
            f"image_region_detection_timeout:{int(max(1, ocr_image_region_timeout))}s"
        )
    except Exception as e:
        image_region_error = str(e)

    return detected_image_regions_pt, image_region_error, None


def _maybe_export_ocr_overlay_image(
    *,
    enabled: bool,
    image_path: Path,
    ocr_dir: Path,
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    ocr_elements: list[dict[str, Any]] | None,
    rendered_page: RenderedPage | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    if not enabled:
        return None, {}

    try:
        from PIL import ImageDraw

        if rendered_page is not None:
            img = rendered_page.as_pil_image().convert("RGB")
        else:
            from PIL import Image

            img = Image.open(image_path).convert("RGB")
        gray = img.convert("L")
        W, H = img.size
        draw = ImageDraw.Draw(img)

        stds: list[float] = []
        out_of_bounds = 0
        low_variance = 0
        low_std_threshold = 5.0

        sx = float(W) / float(page_w_pt) if page_w_pt else 1.0
        sy = float(H) / float(page_h_pt) if page_h_pt else 1.0

        for el in ocr_elements or []:
            bbox_pt = el.get("bbox_pt")
            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                continue
            try:
                x0, y0, x1, y1 = (
                    float(bbox_pt[0]),
                    float(bbox_pt[1]),
                    float(bbox_pt[2]),
                    float(bbox_pt[3]),
                )
            except Exception:
                continue

            x0p = int(round(x0 * sx))
            y0p = int(round(y0 * sy))
            x1p = int(round(x1 * sx))
            y1p = int(round(y1 * sy))

            if x0p < 0 or y0p < 0 or x1p > W or y1p > H:
                out_of_bounds += 1

            # Clamp for drawing/stat sampling.
            x0c = max(0, min(W - 1, x0p))
            y0c = max(0, min(H - 1, y0p))
            x1c = max(0, min(W, x1p))
            y1c = max(0, min(H, y1p))
            if x1c <= x0c or y1c <= y0c:
                continue

            draw.rectangle([x0c, y0c, x1c, y1c], outline=(255, 0, 0), width=2)

            crop = gray.crop((x0c, y0c, x1c, y1c))
            target_w = max(8, min(64, crop.width // 8))
            target_h = max(8, min(64, crop.height // 8))
            small = crop.resize((target_w, target_h))
            pixels = list(small.getdata())
            if not pixels:
                continue
            mean = sum(pixels) / len(pixels)
            var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            std = float(var**0.5)
            stds.append(std)
            if std <= low_std_threshold:
                low_variance += 1

        overlay_path = ocr_dir / f"page-{page_index:04d}.overlay.png"
        img.save(overlay_path)

        return overlay_path, {
            "out_of_bounds": out_of_bounds,
            "low_variance": low_variance,
            "low_std_threshold": low_std_threshold,
            "median_std": (sorted(stds)[len(stds) // 2] if stds else None),
        }
    except Exception as e:
        return None, {"overlay_error": str(e)}


def _process_parallel_ai_ocr_page(
    *,
    page: dict[str, Any],
    input_pdf: Path,
    ocr_dir: Path,
    ocr_runtime_factory: Callable[[], Any],
    linebreak_assist_effective: bool | None,
    ocr_render_dpi: int,
    ocr_page_timeout: int,
    ocr_image_region_timeout: int,
    skip_image_region_detection: bool,
    export_overlay_images: bool,
    abort_if_cancelled: Callable[..., None],
) -> dict[str, Any]:
    abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
    page_index = int(page.get("page_index") or 0)
    page_w_pt = float(page.get("page_width_pt") or 0)
    page_h_pt = float(page.get("page_height_pt") or 0)
    if page_w_pt <= 0 or page_h_pt <= 0:
        return {
            "page_index": page_index,
            "page_warnings": [],
            "ir_warnings": [],
            "elements": [],
            "image_regions": [],
            "debug_entry": {
                "page_index": page_index,
                "skipped": "invalid_dimensions",
                "page_width_pt": page_w_pt,
                "page_height_pt": page_h_pt,
            },
        }

    runtime = ocr_runtime_factory()
    ocr_manager = getattr(runtime, "ocr_manager", None)
    if ocr_manager is None:
        raise RuntimeError("parallel OCR runtime has no ocr_manager")
    text_refiner = getattr(runtime, "text_refiner", None)
    linebreak_refiner = getattr(runtime, "linebreak_refiner", None)
    strict_no_fallback = bool(getattr(runtime, "strict_ocr_mode", True))
    effective_ocr_provider = str(
        getattr(runtime, "effective_ocr_provider", None) or "aiocr"
    )
    route_kind = getattr(ocr_manager, "route_kind", None)

    try:
        pdf_doc = pymupdf.open(str(input_pdf))
        try:
            abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            pdf_page = pdf_doc.load_page(page_index)
            pix = pdf_page.get_pixmap(dpi=int(ocr_render_dpi), alpha=False)
        finally:
            pdf_doc.close()
    except Exception as e:
        logger.warning("Failed to render parallel OCR page %s: %s", page_index, e)
        return {
            "page_index": page_index,
            "page_warnings": [],
            "ir_warnings": [],
            "elements": [],
            "image_regions": [],
            "debug_entry": {
                "page_index": page_index,
                "error": f"render_failed: {e!s}",
            },
        }

    rendered = RenderedPage(pix, page_index)
    image_path = rendered.as_tempfile_path(ocr_dir)

    ocr_call_started = time.perf_counter()
    logger.info(
        "Starting parallel OCR page (pdf_page=%s, provider=%s, route=%s, timeout_s=%s, image=%s)",
        page_index + 1,
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
        logger.warning(
            "Parallel OCR failed for page %s (provider=%s): %s",
            page_index,
            effective_ocr_provider,
            details,
        )
        details_lower = details.lower()
        is_timeout_error = isinstance(e, TimeoutError) or (
            "timeout" in details_lower or "timed out" in details_lower
        )
        if is_timeout_error and not strict_no_fallback:
            return {
                "page_index": page_index,
                "page_warnings": [
                    f"ocr_timeout_best_effort: provider={effective_ocr_provider}, page={page_index + 1}, parallel=1"
                ],
                "ir_warnings": [],
                "elements": [],
                "image_regions": [],
                "debug_entry": {
                    "page_index": page_index,
                    "warning": "ocr_timeout",
                    "provider": effective_ocr_provider,
                    "error": details,
                },
            }

        nonfatal_empty_ocr = any(
            marker in details_lower
            for marker in (
                "ai ocr returned no items",
                "ai ocr returned empty elements",
                "ai ocr returned no parseable items",
            )
        )
        if nonfatal_empty_ocr:
            if strict_no_fallback:
                raise AppException(
                    code=ErrorCode.OCR_FAILED,
                    message=(
                        f"{effective_ocr_provider.upper()} returned empty OCR result on page {page_index + 1}"
                    ),
                    details={
                        "page_index": page_index,
                        "provider": effective_ocr_provider,
                        "reason": details,
                    },
                ) from e
            return {
                "page_index": page_index,
                "page_warnings": [
                    f"ocr_empty_result: provider={effective_ocr_provider}, page={page_index + 1}"
                ],
                "ir_warnings": [],
                "elements": [],
                "image_regions": [],
                "debug_entry": {
                    "page_index": page_index,
                    "warning": "ocr_empty_result",
                    "provider": effective_ocr_provider,
                    "error": details,
                },
            }

        if strict_no_fallback:
            raise AppException(
                code=ErrorCode.OCR_FAILED,
                message=(
                    f"{effective_ocr_provider.upper()} failed on page {page_index + 1}: {details}"
                ),
                details={
                    "page_index": page_index,
                    "provider": effective_ocr_provider,
                    "reason": details,
                },
            ) from e

        return {
            "page_index": page_index,
            "page_warnings": [
                f"ocr_failed_best_effort: provider={effective_ocr_provider}, page={page_index + 1}"
            ],
            "ir_warnings": [],
            "elements": [],
            "image_regions": [],
            "debug_entry": {
                "page_index": page_index,
                "error": f"ocr_failed: {details}",
            },
        }

    elapsed_ms = int(round(max(0.0, time.perf_counter() - ocr_call_started) * 1000.0))
    logger.info(
        "Finished parallel OCR page (pdf_page=%s, provider=%s, route=%s, elapsed_ms=%s, elements=%s)",
        page_index + 1,
        effective_ocr_provider,
        route_kind,
        elapsed_ms,
        len(ocr_elements or []),
    )

    used_provider = getattr(ocr_manager, "last_provider_name", None)
    fallback_reason = getattr(ocr_manager, "last_fallback_reason", None)
    layout_blocks = getattr(ocr_manager, "last_layout_blocks", [])
    layout_analysis_debug = getattr(ocr_manager, "last_layout_analysis_debug", None)
    quality_notes_raw = getattr(ocr_manager, "last_quality_notes", [])
    quality_notes = [
        str(note).strip()
        for note in (quality_notes_raw if isinstance(quality_notes_raw, list) else [])
        if str(note).strip()
    ]
    page_warnings = list(quality_notes)
    ir_warnings = [f"{note}:page={page_index + 1}" for note in quality_notes]

    detected_image_regions_pt, image_region_error, image_region_skip_reason = (
        _detect_page_image_regions(
            enabled=not bool(skip_image_region_detection),
            image_path=image_path,
            ocr_manager=ocr_manager,
            page_index=page_index,
            ocr_image_region_timeout=int(ocr_image_region_timeout),
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            skip_reason="fast_ppt_generation_mode",
            rendered_page=rendered,
        )
    )

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

    return {
        "page_index": page_index,
        "page_warnings": page_warnings,
        "ir_warnings": ir_warnings,
        "elements": ocr_elements or [],
        "image_regions": detected_image_regions_pt,
        "debug_entry": {
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
        },
    }


# ── parallel executor ────────────────────────────────────────────────────────


def _run_parallel_ocr_executor(
    *,
    ocr_pages: list[dict[str, Any]],
    ir: dict[str, Any],
    ocr_debug: dict[str, Any],
    input_pdf: Path,
    ocr_dir: Path,
    ocr_runtime_factory: Callable[[], Any],
    linebreak_assist_effective: bool | None,
    ocr_render_dpi: int,
    ocr_page_timeout: int,
    ocr_image_region_timeout: int,
    skip_image_region_detection: bool,
    export_overlay_images: bool,
    ocr_stage_deadline: float,
    ocr_total_timeout: int,
    page_concurrency: int,
    source_page_count: int,
    set_processing_progress: Callable[[Any, int, str], None],
    abort_if_cancelled: Callable[..., None],
) -> None:
    """Run parallel AI OCR over OCR pages using ThreadPoolExecutor."""
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    completed_pages = 0
    latest_pdf_page_index: int | None = None
    running_initial = min(page_concurrency, len(ocr_pages))
    set_processing_progress(
        JobStage.ocr,
        36,
        _format_parallel_ocr_progress_message(
            completed_pages=0,
            total_pages=len(ocr_pages),
            running_pages=running_initial,
            page_concurrency=page_concurrency,
            latest_pdf_page_index=None,
            source_page_count=source_page_count,
            overall_progress=36,
        ),
    )
    abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")

    page_iter = iter(ocr_pages)
    future_map: dict[Any, dict[str, Any]] = {}
    stop_submitting_new_pages = False
    with ThreadPoolExecutor(max_workers=page_concurrency) as executor:
        for _ in range(running_initial):
            page = next(page_iter, None)
            if page is None:
                break
            future = executor.submit(
                _process_parallel_ai_ocr_page,
                page=page,
                input_pdf=input_pdf,
                ocr_dir=ocr_dir,
                ocr_runtime_factory=ocr_runtime_factory,
                linebreak_assist_effective=linebreak_assist_effective,
                ocr_render_dpi=int(ocr_render_dpi),
                ocr_page_timeout=int(ocr_page_timeout),
                ocr_image_region_timeout=int(ocr_image_region_timeout),
                skip_image_region_detection=bool(skip_image_region_detection),
                export_overlay_images=bool(export_overlay_images),
                abort_if_cancelled=abort_if_cancelled,
            )
            future_map[future] = page

        while future_map:
            done_futures, _ = wait(
                set(future_map),
                timeout=1.0,
                return_when=FIRST_COMPLETED,
            )
            if not done_futures:
                if (
                    not stop_submitting_new_pages
                    and time.monotonic() >= ocr_stage_deadline
                ):
                    stop_submitting_new_pages = True
                    logger.warning(
                        "Parallel OCR stage timeout (%ss) exceeded – stop scheduling new pages",
                        ocr_total_timeout,
                    )
                    ir.setdefault("warnings", []).append(
                        "ocr_parallel_total_timeout:"
                        f" total_timeout_s={ocr_total_timeout}"
                    )
                abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
                continue
            for future in done_futures:
                page = future_map.pop(future)
                result = future.result()
                latest_pdf_page_index = int(result.get("page_index") or 0)
                for note in result.get("page_warnings") or []:
                    if str(note).strip():
                        page.setdefault("warnings", []).append(str(note).strip())
                for note in result.get("ir_warnings") or []:
                    if str(note).strip():
                        ir.setdefault("warnings", []).append(str(note).strip())
                image_regions = result.get("image_regions") or []
                if image_regions:
                    page["image_regions"] = image_regions
                ocr_elements = result.get("elements") or []
                if ocr_elements:
                    page.setdefault("elements", []).extend(ocr_elements)
                    page["ocr_used"] = True
                debug_entry = result.get("debug_entry")
                if isinstance(debug_entry, dict):
                    ocr_debug["pages"].append(debug_entry)

                completed_pages += 1
                if (
                    not stop_submitting_new_pages
                    and time.monotonic() >= ocr_stage_deadline
                ):
                    stop_submitting_new_pages = True
                    logger.warning(
                        "Parallel OCR stage timeout (%ss) exceeded – stop scheduling new pages",
                        ocr_total_timeout,
                    )
                    ir.setdefault("warnings", []).append(
                        "ocr_parallel_total_timeout:"
                        f" total_timeout_s={ocr_total_timeout}"
                    )
                next_page = (
                    None if stop_submitting_new_pages else next(page_iter, None)
                )
                if next_page is not None:
                    next_future = executor.submit(
                        _process_parallel_ai_ocr_page,
                        page=next_page,
                        input_pdf=input_pdf,
                        ocr_dir=ocr_dir,
                        ocr_runtime_factory=ocr_runtime_factory,
                        linebreak_assist_effective=linebreak_assist_effective,
                        ocr_render_dpi=int(ocr_render_dpi),
                        ocr_page_timeout=int(ocr_page_timeout),
                        ocr_image_region_timeout=int(ocr_image_region_timeout),
                        skip_image_region_detection=bool(skip_image_region_detection),
                        export_overlay_images=bool(export_overlay_images),
                        abort_if_cancelled=abort_if_cancelled,
                    )
                    future_map[next_future] = next_page

                progress_value = _progress_in_span(
                    completed_pages,
                    max(1, len(ocr_pages)),
                    start=36,
                    end=68,
                )
                set_processing_progress(
                    JobStage.ocr,
                    progress_value,
                    _format_parallel_ocr_progress_message(
                        completed_pages=completed_pages,
                        total_pages=len(ocr_pages),
                        running_pages=len(future_map),
                        page_concurrency=page_concurrency,
                        latest_pdf_page_index=latest_pdf_page_index,
                        source_page_count=source_page_count,
                        overall_progress=progress_value,
                    ),
                )
                abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
