"""Scanned-page slide builder extracted from main.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..bbox_utils import (
    _bbox_pt_to_slide_emu,
    _coerce_bbox_pt,
    _compute_text_erase_padding_pt,
    _is_near_full_page_bbox_pt,
)
from ..color_utils import (
    _hex_to_rgb,
    _pick_contrasting_text_rgb,
    _rgb_sq_distance,
)
from ..constants import _EMU_PER_PT
from ..font_utils import (
    _compact_text_length,
    _contains_cjk,
    _fit_ocr_text_style,
    _is_inline_short_token,
    _map_font_name,
    _prefer_wrap_for_ocr_text,
    _resolve_visual_wrap_override_for_ocr_text,
)
from ..scanned_page import (
    _apply_text_cutouts_to_scanned_image_region_crops,
    _build_scanned_image_region_infos,
    _clear_regions_for_transparent_crops,
    _dedupe_scanned_ocr_text_elements,
    _erase_regions_in_render_image,
    _estimate_bbox_ink_line_count,
    _estimate_baseline_ocr_line_height_pt,
    _filter_scanned_ocr_text_elements,
    _render_pdf_page_png,
    _sample_bbox_background_rgb,
    _sample_bbox_text_rgb,
)
from ..slide_builder import _iter_page_elements

from ._parameter_parser import normalise_parameters
from .footer import _detect_notebooklm_footer_bbox_from_render
from .markdown_utils import _sanitize_markdown_text
from .probing import (
    _maybe_export_final_preview_page_image,
    _should_center_scanned_heading,
    _should_probe_visual_wrap_for_ocr_text,
    _should_sample_local_text_colors,
)
from .text_erase import _merge_text_erase_bboxes


def _is_layout_parse_source(source_id: Any) -> bool:
    normalized = str(source_id or "").strip().lower()
    return normalized in {"mineru", "baidu_doc"}


def _text_coverage_ratio(
    bb: list[float],
    *,
    ocr_text_elements: list[dict[str, Any]],
    baseline_ocr_h_pt: float,
) -> tuple[float, int]:
    """Return (overlap_area_ratio, ocr_items_inside_count) for a bbox.

    Used to reject image-region candidates that are actually paragraph
    text blocks or card backgrounds. Coverage is computed against OCR
    text boxes in PDF point coordinates.
    """

    if not ocr_text_elements:
        return (0.0, 0)
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bb)
    except Exception:
        return (0.0, 0)
    area = float(max(1.0, (x1 - x0) * (y1 - y0)))
    # Expand OCR bboxes a bit to account for line spacing gaps,
    # which otherwise underestimates text coverage.
    pad = max(1.0, min(6.0, 0.18 * float(baseline_ocr_h_pt)))
    overlap = 0.0
    count = 0
    for tel in ocr_text_elements:
        bbox_pt = tel.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        text_value = str(tel.get("text") or "")
        if _is_inline_short_token(text_value):
            continue

        text_area = max(1.0, float((tx1 - tx0) * (ty1 - ty0)))
        cx = (tx0 + tx1) / 2.0
        cy = (ty0 + ty1) / 2.0

        tx0 -= pad
        ty0 -= pad
        tx1 += pad
        ty1 += pad
        ix0 = max(x0, tx0)
        iy0 = max(y0, ty0)
        ix1 = min(x1, tx1)
        iy1 = min(y1, ty1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        inter = float((ix1 - ix0) * (iy1 - iy0))
        overlap += inter

        center_inside = cx >= x0 and cx <= x1 and cy >= y0 and cy <= y1
        if center_inside or (inter / text_area) >= 0.18:
            count += 1
    overlap = min(overlap, area)
    return (float(overlap) / area, int(count))


def _text_inside_counts(
    bb: list[float],
    *,
    ocr_text_elements: list[dict[str, Any]],
) -> tuple[int, int]:
    """Return (items_inside_count, cjk_items_inside_count) for a bbox.

    This complements area-based coverage with linguistic hints so we can
    reject large mixed regions that accidentally swallow CJK body text.
    """

    if not ocr_text_elements:
        return (0, 0)
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bb)
    except Exception:
        return (0, 0)
    inside = 0
    cjk_inside = 0
    for tel in ocr_text_elements:
        bbox_pt = tel.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        cx = (tx0 + tx1) / 2.0
        cy = (ty0 + ty1) / 2.0
        if cx < x0 or cx > x1 or cy < y0 or cy > y1:
            continue

        text_value = str(tel.get("text") or "")
        if _is_inline_short_token(text_value):
            continue

        inside += 1
        if _contains_cjk(text_value):
            cjk_inside += 1
    return (int(inside), int(cjk_inside))


def _build_scanned_page_slide(
    *,
    slide: Any,
    page: dict[str, Any],
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    transform: Any,
    source_pdf: Path,
    artifacts: Path,
    scanned_render_dpi: int,
    text_erase_mode_id: str,
    scanned_page_mode_id: str,
    is_speed_ppt_generation: bool,
    image_bg_clear_expand_min_pt: float,
    image_bg_clear_expand_max_pt: float,
    image_bg_clear_expand_ratio: float,
    scanned_image_region_min_area_ratio: float,
    scanned_image_region_max_area_ratio: float,
    scanned_image_region_max_aspect_ratio: float,
    remove_footer_notebooklm: bool,
    should_export_final_previews: bool,
    slide_w_emu: int,
    slide_h_emu: int,
    page_text_elements_all: list[dict[str, Any]],
    page_text_elements_render: list[dict[str, Any]],
    page_text_elements_footer_removed: list[dict[str, Any]],
    baseline_ocr_h_pt: float,
    Emu: Any,
    Pt: Any,
    RGBColor: Any,
    MSO_AUTO_SIZE: Any,
    MSO_ANCHOR: Any,
    PP_ALIGN: Any,
) -> None:
    """Build a slide for a scanned PDF page (no text layer)."""

    should_split_scanned_image_regions = scanned_page_mode_id != "fullpage"
    skip_scanned_image_region_analysis = bool(is_speed_ppt_generation)
    overlay_scanned_image_crops = bool(should_split_scanned_image_regions)

    render_path = artifacts / "page_renders" / f"page-{page_index:04d}.png"
    pix = _render_pdf_page_png(
        source_pdf,
        page_index=page_index,
        dpi=int(scanned_render_dpi),
        out_path=render_path,
    )

    bg_left = int(round(transform.offset_x_emu))
    bg_top = int(round(transform.offset_y_emu))
    bg_w = int(round(page_w_pt * _EMU_PER_PT * transform.scale))
    bg_h = int(round(page_h_pt * _EMU_PER_PT * transform.scale))

    removed_footer_ocr_text_elements = [
        el
        for el in page_text_elements_footer_removed
        if str(el.get("source") or "").strip().lower() == "ocr"
    ]
    fallback_footer_erase_bboxes_pt: list[list[float]] = []
    if bool(remove_footer_notebooklm) and not removed_footer_ocr_text_elements:
        detected_footer_bbox_pt = _detect_notebooklm_footer_bbox_from_render(
            render_path=render_path,
            page_w_pt=float(page_w_pt),
            page_h_pt=float(page_h_pt),
        )
        if detected_footer_bbox_pt is not None:
            fallback_footer_erase_bboxes_pt.append(detected_footer_bbox_pt)

    ocr_text_elements = [
        el
        for el in page_text_elements_render
        if str(el.get("source") or "") == "ocr"
    ]
    baseline_ocr_h_pt = _estimate_baseline_ocr_line_height_pt(
        ocr_text_elements=ocr_text_elements,
        page_w_pt=float(page_w_pt),
    )

    has_full_page_bg_image = any(
        _is_near_full_page_bbox_pt(
            el.get("bbox_pt"), page_w_pt=page_w_pt, page_h_pt=page_h_pt
        )
        for el in _iter_page_elements(page, type_name="image")
    )

    image_region_infos = (
        []
        if skip_scanned_image_region_analysis
        else _build_scanned_image_region_infos(
            page=page,
            render_path=render_path,
            artifacts_dir=artifacts,
            page_index=page_index,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            scanned_render_dpi=int(scanned_render_dpi),
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            ocr_text_elements=ocr_text_elements,
            has_full_page_bg_image=has_full_page_bg_image,
            text_coverage_ratio_fn=lambda bb: _text_coverage_ratio(
                bb,
                ocr_text_elements=ocr_text_elements,
                baseline_ocr_h_pt=baseline_ocr_h_pt,
            ),
            text_inside_counts_fn=lambda bb: _text_inside_counts(
                bb, ocr_text_elements=ocr_text_elements
            ),
            min_area_ratio=scanned_image_region_min_area_ratio,
            max_area_ratio=scanned_image_region_max_area_ratio,
            max_aspect_ratio=scanned_image_region_max_aspect_ratio,
        )
    )
    overlay_image_region_infos = list(image_region_infos)
    overlay_scanned_image_crops = bool(overlay_image_region_infos) and (
        scanned_page_mode_id != "fullpage"
    )
    ocr_text_elements = _filter_scanned_ocr_text_elements(
        ocr_text_elements=ocr_text_elements,
        image_region_infos=image_region_infos,
        baseline_ocr_h_pt=float(baseline_ocr_h_pt),
    )
    ocr_text_elements = _dedupe_scanned_ocr_text_elements(
        ocr_text_elements=ocr_text_elements,
        baseline_ocr_h_pt=float(baseline_ocr_h_pt),
    )
    overlay_image_region_infos = _apply_text_cutouts_to_scanned_image_region_crops(
        infos=overlay_image_region_infos,
        render_path=render_path,
        page_h_pt=page_h_pt,
        scanned_render_dpi=int(scanned_render_dpi),
        ocr_text_elements=ocr_text_elements,
    )

    text_erase_bboxes_pt: list[list[float]] = []
    text_erase_polygons_pt: list[list[list[float]] | None] = []
    kept_text_erase_bboxes_pt: list[list[float]] = []
    kept_text_erase_polygons_pt: list[list[list[float]] | None] = []
    text_items: list[
        tuple[dict[str, Any], list[float], str, tuple[int, int, int]]
    ] = []
    is_fill_mode = text_erase_mode_id == "fill"

    for el in removed_footer_ocr_text_elements:
        bbox_pt = el.get("bbox_pt")
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        bbox_h_pt = max(1.0, y1 - y0)
        pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
            bbox_h_pt=bbox_h_pt,
            text_erase_mode=text_erase_mode_id,
        )
        text_erase_bboxes_pt.append(
            [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
        )
        text_erase_polygons_pt.append(
            el.get("ocr_layout_geometry_points_pt")
            if str(el.get("ocr_layout_geometry_kind") or "").strip().lower()
            == "polygon"
            else None
        )

    for bbox_pt in fallback_footer_erase_bboxes_pt:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        bbox_h_pt = max(1.0, y1 - y0)
        pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
            bbox_h_pt=bbox_h_pt,
            text_erase_mode=text_erase_mode_id,
        )
        text_erase_bboxes_pt.append(
            [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
        )
        text_erase_polygons_pt.append(None)

    for el in ocr_text_elements:
        bbox_pt = el.get("bbox_pt")
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue

        raw_text = str(el.get("text") or "")
        text = _sanitize_markdown_text(raw_text)
        text = "\n".join(
            [line.strip() for line in text.split("\n") if line.strip()]
        ).strip()
        if not text:
            continue

        bbox_w_pt = max(1.0, x1 - x0)
        bbox_h_pt = max(1.0, y1 - y0)

        bg_rgb = (
            (255, 255, 255)
            if is_speed_ppt_generation
            else _sample_bbox_background_rgb(
                pix,
                bbox_pt=[x0, y0, x1, y1],
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
            )
        )

        pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
            bbox_h_pt=bbox_h_pt,
            text_erase_mode=text_erase_mode_id,
        )
        text_erase_bboxes_pt.append(
            [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
        )
        text_polygon = (
            el.get("ocr_layout_geometry_points_pt")
            if str(el.get("ocr_layout_geometry_kind") or "").strip().lower()
            == "polygon"
            else None
        )
        text_erase_polygons_pt.append(text_polygon)
        kept_text_erase_bboxes_pt.append(
            [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
        )
        kept_text_erase_polygons_pt.append(text_polygon)

        text_items.append((el, [x0, y0, x1, y1], text, bg_rgb))

    if is_fill_mode:
        erase_bboxes_for_background = list(text_erase_bboxes_pt)
        erase_polygons_for_background: list[list[list[float]] | None] | None = (
            list(text_erase_polygons_pt)
        )
        if len(text_erase_bboxes_pt) >= 60:
            merged_fill_bboxes_pt = _merge_text_erase_bboxes(
                text_erase_bboxes_pt,
                gap_pt=max(1.5, 0.42 * float(baseline_ocr_h_pt)),
            )
            for bb in merged_fill_bboxes_pt:
                try:
                    mx0, my0, mx1, my1 = _coerce_bbox_pt(bb)
                except Exception:
                    continue
                if (mx1 - mx0) >= 0.92 * float(page_w_pt):
                    continue
                if (my1 - my0) >= 3.8 * float(baseline_ocr_h_pt):
                    continue
                erase_bboxes_for_background.append([mx0, my0, mx1, my1])
                erase_polygons_for_background.append(None)
    else:
        merged_text_erase_bboxes_pt = _merge_text_erase_bboxes(
            text_erase_bboxes_pt,
            gap_pt=max(2.0, 0.75 * float(baseline_ocr_h_pt)),
        )
        erase_bboxes_for_background = list(merged_text_erase_bboxes_pt) + list(
            text_erase_bboxes_pt
        )
        erase_polygons_for_background = None

    # Protect confirmed image regions from erase.
    protect_bboxes_for_erase: list[list[float]] = []
    for info in image_region_infos:
        is_ai_hint = bool(getattr(info, "ai_hint", False))
        if (not info.shape_confirmed) and (not is_ai_hint):
            continue
        try:
            ix0, iy0, ix1, iy1 = _coerce_bbox_pt(info.bbox_pt)
        except Exception:
            continue
        iw = float(ix1 - ix0)
        ih = float(iy1 - iy0)
        area_ratio = max(0.0, iw * ih) / max(
            1.0, float(page_w_pt) * float(page_h_pt)
        )
        if area_ratio < 0.030 and not (is_ai_hint and area_ratio >= 0.018):
            continue
        if (not info.shape_confirmed) and is_ai_hint and area_ratio < 0.025:
            continue
        protect_bboxes_for_erase.append([ix0, iy0, ix1, iy1])

    cleaned_render_path = _erase_regions_in_render_image(
        render_path,
        out_path=artifacts
        / "page_renders"
        / f"page-{page_index:04d}.clean.png",
        erase_bboxes_pt=erase_bboxes_for_background,
        erase_polygons_pt=erase_polygons_for_background,
        protect_bboxes_pt=protect_bboxes_for_erase,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
        text_erase_mode=text_erase_mode_id,
    )

    if overlay_scanned_image_crops:
        if is_fill_mode:
            clear_region_infos = list(overlay_image_region_infos)
            clear_out_name = (
                f"page-{page_index:04d}.clean.images-bg-cleared.png"
            )
        else:
            clear_region_infos = [
                info
                for info in overlay_image_region_infos
                if info.background_removed or info.geometry_points_pt
            ]
            clear_out_name = f"page-{page_index:04d}.clean.icons-bg-cleared.png"

        if clear_region_infos:
            cleaned_render_path = _clear_regions_for_transparent_crops(
                cleaned_render_path=cleaned_render_path,
                out_path=artifacts / "page_renders" / clear_out_name,
                regions_pt=[info.bbox_pt for info in clear_region_infos],
                regions_polygons_pt=[
                    info.geometry_points_pt for info in clear_region_infos
                ],
                pix=pix,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
                clear_expand_min_pt=image_bg_clear_expand_min_pt,
                clear_expand_max_pt=image_bg_clear_expand_max_pt,
                clear_expand_ratio=image_bg_clear_expand_ratio,
            )

    if kept_text_erase_bboxes_pt:
        cleaned_render_path = _erase_regions_in_render_image(
            cleaned_render_path,
            out_path=artifacts
            / "page_renders"
            / f"page-{page_index:04d}.clean.text-overlay.png",
            erase_bboxes_pt=list(kept_text_erase_bboxes_pt),
            erase_polygons_pt=list(kept_text_erase_polygons_pt),
            protect_bboxes_pt=None,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
            text_erase_mode=text_erase_mode_id,
        )

    slide.shapes.add_picture(
        str(cleaned_render_path),
        Emu(bg_left),
        Emu(bg_top),
        Emu(bg_w),
        Emu(bg_h),
    )

    # Overlay cropped images
    if overlay_scanned_image_crops:
        for info in overlay_image_region_infos:
            try:
                left, top, width, height = _bbox_pt_to_slide_emu(
                    info.bbox_pt, transform=transform
                )
            except Exception:
                continue
            if width <= 0 or height <= 0:
                continue
            slide.shapes.add_picture(
                str(info.crop_path),
                Emu(left),
                Emu(top),
                Emu(width),
                Emu(height),
            )

    # Editable text boxes
    for el, bbox_pt, text, (r, g, b) in text_items:
        try:
            left, top, width, height = _bbox_pt_to_slide_emu(
                bbox_pt, transform=transform
            )
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue

        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        bbox_w_pt = max(1.0, x1 - x0)
        bbox_h_pt = max(1.0, y1 - y0)

        is_heading = (
            y0 <= 0.22 * float(page_h_pt)
            and bbox_h_pt >= 1.6 * float(baseline_ocr_h_pt)
            and len(text) <= 40
        )
        center_heading = bool(
            is_heading
            and _should_center_scanned_heading(
                x0_pt=float(x0),
                x1_pt=float(x1),
                page_w_pt=float(page_w_pt),
            )
        )

        fit_bbox_h_pt = float(bbox_h_pt) + float(
            min(1.2, 0.06 * float(bbox_h_pt))
        )

        wrap_hint = _prefer_wrap_for_ocr_text(
            text=text,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
        )
        visual_wrap_override: bool | None = None
        if (
            not is_speed_ppt_generation
        ) and _should_probe_visual_wrap_for_ocr_text(
            text=text,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            is_heading=bool(is_heading),
            wrap_hint=bool(wrap_hint),
            ocr_linebreak_assisted=bool(el.get("ocr_linebreak_assisted")),
        ):
            try:
                visual_line_count = _estimate_bbox_ink_line_count(
                    pix,
                    bbox_pt=bbox_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                    max_lines=3,
                )
                if (
                    isinstance(visual_line_count, int)
                    and visual_line_count >= 1
                ):
                    compact_len = _compact_text_length(text)
                    visual_wrap_override = (
                        _resolve_visual_wrap_override_for_ocr_text(
                            visual_line_count=visual_line_count,
                            compact_len=compact_len,
                            bbox_h_pt=bbox_h_pt,
                            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                            is_heading=bool(is_heading),
                        )
                    )
            except Exception:
                visual_wrap_override = None

        sampled_bg_rgb: tuple[int, int, int] | None = None
        sampled_text_rgb: tuple[int, int, int] | None = None
        if (not is_speed_ppt_generation) and _should_sample_local_text_colors(
            source_id="ocr",
            element_color=el.get("color"),
        ):
            try:
                sampled_bg_rgb = _sample_bbox_background_rgb(
                    pix,
                    bbox_pt=bbox_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                )
                sampled_text_rgb = _sample_bbox_text_rgb(
                    pix,
                    bbox_pt=bbox_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                    bg_rgb=sampled_bg_rgb,
                )
            except Exception:
                sampled_bg_rgb = None
                sampled_text_rgb = None

        text_to_render, font_size_pt, wrap = _fit_ocr_text_style(
            text=text,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=fit_bbox_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            is_heading=bool(is_heading),
            wrap_override=(
                visual_wrap_override
                if visual_wrap_override is not None
                else wrap_hint
            ),
        )
        if not text_to_render.strip():
            continue

        nudge_up_pt = min(
            2.2,
            max(
                0.6,
                0.08 * float(bbox_h_pt),
                0.10 * float(font_size_pt),
            ),
        )
        nudge_emu = int(
            round(float(nudge_up_pt) * _EMU_PER_PT * transform.scale)
        )
        textbox_top = max(0, int(top) - nudge_emu)
        textbox_height = int(height) + nudge_emu

        if wrap:
            nudge_right_pt = min(3.2, max(1.2, 0.07 * float(bbox_h_pt)))
        else:
            nudge_right_pt = min(
                8.0,
                max(
                    3.0,
                    0.16 * float(bbox_h_pt),
                    0.50 * float(font_size_pt),
                ),
            )
        nudge_right_emu = int(
            round(float(nudge_right_pt) * _EMU_PER_PT * transform.scale)
        )
        textbox_left = int(left)
        textbox_width = int(width) + nudge_right_emu
        max_box_w = max(1, int(slide_w_emu) - textbox_left)
        textbox_width = max(1, min(textbox_width, max_box_w))

        tx = slide.shapes.add_textbox(
            Emu(textbox_left),
            Emu(textbox_top),
            Emu(textbox_width),
            Emu(textbox_height),
        )
        tx.fill.background()
        tx.line.fill.background()
        tf = tx.text_frame
        try:
            tf.vertical_anchor = MSO_ANCHOR.TOP
        except Exception:
            pass
        tf.word_wrap = False
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        tf.text = text_to_render

        for p in tf.paragraphs:
            try:
                if center_heading:
                    p.alignment = PP_ALIGN.CENTER
            except Exception:
                pass
            try:
                p.space_before = Pt(0)
                p.space_after = Pt(0)
            except Exception:
                pass
            try:
                p.line_spacing = 1.0
            except Exception:
                pass

            for run in p.runs:
                font = run.font
                font.size = Pt(float(font_size_pt))
                if _contains_cjk(text):
                    font.name = "Microsoft YaHei"
                else:
                    font.name = _map_font_name(el.get("font_name")) or "Arial"
                font.bold = bool(el.get("bold")) if "bold" in el else None
                font.italic = bool(el.get("italic")) if "italic" in el else None

                rgb = _hex_to_rgb(el.get("color"))
                if rgb is None and sampled_bg_rgb is not None:
                    if sampled_text_rgb is not None:
                        rgb = sampled_text_rgb
                    else:
                        rgb = _pick_contrasting_text_rgb(sampled_bg_rgb)
                elif rgb is not None and sampled_bg_rgb is not None:
                    if _rgb_sq_distance(rgb, sampled_bg_rgb) < (32 * 32):
                        rgb = (
                            sampled_text_rgb
                            if sampled_text_rgb is not None
                            else _pick_contrasting_text_rgb(sampled_bg_rgb)
                        )

                if rgb is None:
                    rgb = (
                        (0, 0, 0)
                        if (0.2126 * r + 0.7152 * g + 0.0722 * b) >= 128
                        else (255, 255, 255)
                    )
                font.color.rgb = RGBColor(*rgb)

    _maybe_export_final_preview_page_image(
        enabled=should_export_final_previews,
        page=page,
        page_index=page_index,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        source_pdf=source_pdf,
        artifacts_dir=artifacts,
        dpi=int(scanned_render_dpi),
        scanned_image_region_crops=[
            (list(info.bbox_pt), info.crop_path)
            for info in overlay_image_region_infos
        ]
        if overlay_scanned_image_crops
        else [],
    )
