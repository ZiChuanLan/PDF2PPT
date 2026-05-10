"""Visual probing and color sampling utilities for OCR text elements."""

from pathlib import Path
from typing import Any

from ..bbox_utils import _coerce_bbox_pt
from ..color_utils import _hex_to_rgb
from ..font_utils import (
    _compact_text_length,
    _normalize_ocr_text_for_render,
    _prefer_wrap_for_ocr_text,
    _resolve_visual_wrap_override_for_ocr_text,
)
from ..preview import _export_final_preview_page_image
from .markdown_utils import _sanitize_markdown_text


def _maybe_export_final_preview_page_image(
    *,
    enabled: bool,
    page: dict[str, Any],
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    source_pdf: Path,
    artifacts_dir: Path,
    dpi: int,
    scanned_image_region_crops: list[tuple[list[float], Path]] | None = None,
) -> None:
    if not enabled:
        return
    _export_final_preview_page_image(
        page=page,
        page_index=page_index,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        source_pdf=source_pdf,
        artifacts_dir=artifacts_dir,
        dpi=int(dpi),
        scanned_image_region_crops=scanned_image_region_crops,
    )


def _should_probe_visual_wrap_for_ocr_text(
    *,
    text: str,
    bbox_w_pt: float,
    bbox_h_pt: float,
    baseline_ocr_h_pt: float,
    is_heading: bool,
    wrap_hint: bool,
    ocr_linebreak_assisted: bool,
) -> bool:
    """Return whether a text box is worth the expensive pixel line-count probe."""

    if ocr_linebreak_assisted:
        return False

    normalized = _normalize_ocr_text_for_render(text)
    if not normalized or "\n" in normalized:
        return False

    compact_len = _compact_text_length(normalized)
    if compact_len <= 10:
        return False

    baseline = max(4.0, float(baseline_ocr_h_pt))
    h_ratio = max(1.0, float(bbox_h_pt)) / baseline
    w = max(1.0, float(bbox_w_pt))

    if is_heading:
        return bool(compact_len >= 12 and w >= 120.0)

    if (not wrap_hint) and compact_len <= 28 and h_ratio <= 1.14:
        return False

    if wrap_hint and (h_ratio >= 1.55 or (compact_len >= 48 and h_ratio >= 1.35)):
        return False

    return True


def _should_sample_local_text_colors(
    *,
    source_id: Any,
    element_color: Any,
) -> bool:
    """Return whether local bg/text color resampling is worth the cost."""

    if _hex_to_rgb(element_color) is not None:
        return False

    normalized_source = str(source_id or "").strip().lower()
    return normalized_source in {"ocr", "mineru", "baidu_doc"}


def _page_needs_ocr_sampling_render(
    *,
    page_elements: list[dict[str, Any]],
    page_h_pt: float,
    baseline_ocr_h_pt: float,
) -> bool:
    """Return whether this page needs an OCR sampling render for visual probes."""

    for el in page_elements:
        if str(el.get("source") or "").strip().lower() != "ocr":
            continue

        raw_text = str(el.get("text") or "")
        text = _normalize_ocr_text_for_render(_sanitize_markdown_text(raw_text))
        if not text:
            continue

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(el.get("bbox_pt"))
        except Exception:
            continue

        bbox_w_pt = max(1.0, float(x1 - x0))
        bbox_h_pt = max(1.0, float(y1 - y0))
        compact_len = _compact_text_length(text)
        is_heading = bool(
            y0 <= 0.20 * float(page_h_pt)
            and bbox_h_pt >= 1.45 * float(baseline_ocr_h_pt)
            and compact_len <= 56
        )
        wrap_hint = _prefer_wrap_for_ocr_text(
            text=text,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
        )
        if _should_probe_visual_wrap_for_ocr_text(
            text=text,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            is_heading=is_heading,
            wrap_hint=wrap_hint,
            ocr_linebreak_assisted=bool(el.get("ocr_linebreak_assisted")),
        ):
            return True

        if _should_sample_local_text_colors(
            source_id="ocr",
            element_color=el.get("color"),
        ):
            return True

    return False


def _should_center_scanned_heading(
    *,
    x0_pt: float,
    x1_pt: float,
    page_w_pt: float,
) -> bool:
    """Return whether a scanned-page heading bbox looks visually centered."""

    page_w = max(1.0, float(page_w_pt))
    x0 = max(0.0, min(float(x0_pt), page_w))
    x1 = max(0.0, min(float(x1_pt), page_w))
    if x1 <= x0:
        return False

    page_center_x = 0.5 * page_w
    bbox_center_x = 0.5 * (x0 + x1)
    left_margin = x0
    right_margin = page_w - x1

    center_tolerance_pt = max(20.0, min(54.0, 0.055 * page_w))
    margin_tolerance_pt = max(24.0, min(72.0, 0.07 * page_w))

    return bool(
        abs(bbox_center_x - page_center_x) <= center_tolerance_pt
        and abs(left_margin - right_margin) <= margin_tolerance_pt
    )
