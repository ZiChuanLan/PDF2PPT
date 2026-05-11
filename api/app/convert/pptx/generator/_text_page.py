"""Text-page slide builder extracted from main.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..bbox_utils import (
    _as_path,
    _bbox_pt_to_slide_emu,
    _coerce_bbox_pt,
    _compute_text_erase_padding_pt,
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
    _fit_mineru_text_style,
    _fit_ocr_text_style,
    _map_font_name,
    _normalize_ocr_text_for_render,
)
from ..scanned_page import (
    _clear_regions_for_transparent_crops,
    _erase_regions_in_render_image,
    _render_pdf_page_png,
    _sample_bbox_background_rgb,
    _sample_bbox_text_rgb,
)
from ..slide_builder import _infer_font_size_pt, _iter_page_elements

from .footer import (
    _build_notebooklm_footer_fill_overlays,
    _is_notebooklm_footer_text_element,
)
from .markdown_utils import _sanitize_markdown_text
from .probing import (
    _maybe_export_final_preview_page_image,
    _page_needs_ocr_sampling_render,
    _should_sample_local_text_colors,
)


def _is_layout_parse_source(source_id: Any) -> bool:
    normalized = str(source_id or "").strip().lower()
    return normalized in {"mineru", "baidu_doc"}


def _build_text_page_slide(
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
    remove_footer_notebooklm: bool,
    should_export_final_previews: bool,
    slide_w_emu: int,
    slide_h_emu: int,
    page_text_elements_all: list[dict[str, Any]],
    page_text_elements_render: list[dict[str, Any]],
    page_text_elements_footer_removed: list[dict[str, Any]],
    baseline_ocr_h_pt: float,
    has_mineru_elements: bool,
    Emu: Any,
    Pt: Any,
    RGBColor: Any,
    MSO_AUTO_SIZE: Any,
    MSO_ANCHOR: Any,
    PP_ALIGN: Any,
    MSO_AUTO_SHAPE_TYPE: Any,
) -> None:
    """Build a slide for a text-layer PDF page."""

    mineru_background_placed = False
    mineru_render_pix: Any | None = None
    ocr_sampling_pix: Any | None = None
    should_overlay_layout_images = scanned_page_mode_id != "fullpage"

    if has_mineru_elements and source_pdf.exists():
        try:
            mineru_text_erase_mode = "fill"
            render_path = (
                artifacts / "page_renders" / f"page-{page_index:04d}.mineru.png"
            )
            mineru_render_pix = _render_pdf_page_png(
                source_pdf,
                page_index=page_index,
                dpi=int(scanned_render_dpi),
                out_path=render_path,
            )
            ocr_sampling_pix = mineru_render_pix

            text_erase_bboxes_pt: list[list[float]] = []
            protect_bboxes_pt: list[list[float]] = []
            mineru_image_regions_pt: list[list[float]] = []

            for el in page_text_elements_all:
                if not _is_layout_parse_source(el.get("source")):
                    continue
                try:
                    x0, y0, x1, y1 = _coerce_bbox_pt(el.get("bbox_pt"))
                except Exception:
                    continue
                bbox_h_pt = max(1.0, y1 - y0)
                pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
                    bbox_h_pt=bbox_h_pt,
                    text_erase_mode=mineru_text_erase_mode,
                )
                text_erase_bboxes_pt.append(
                    [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
                )

            if should_overlay_layout_images:
                for el in _iter_page_elements(page, type_name="image"):
                    if not _is_layout_parse_source(el.get("source")):
                        continue
                    if not str(el.get("image_path") or "").strip():
                        continue
                    try:
                        ix0, iy0, ix1, iy1 = _coerce_bbox_pt(el.get("bbox_pt"))
                    except Exception:
                        continue
                    if ix1 <= ix0 or iy1 <= iy0:
                        continue
                    mineru_image_regions_pt.append([ix0, iy0, ix1, iy1])

            cleaned_render_path = _erase_regions_in_render_image(
                render_path,
                out_path=artifacts
                / "page_renders"
                / f"page-{page_index:04d}.mineru.clean.png",
                erase_bboxes_pt=text_erase_bboxes_pt,
                protect_bboxes_pt=protect_bboxes_pt,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
                text_erase_mode=mineru_text_erase_mode,
            )
            if mineru_image_regions_pt and mineru_render_pix is not None:
                cleaned_render_path = _clear_regions_for_transparent_crops(
                    cleaned_render_path=cleaned_render_path,
                    out_path=artifacts
                    / "page_renders"
                    / f"page-{page_index:04d}.mineru.clean.images-bg-cleared.png",
                    regions_pt=mineru_image_regions_pt,
                    pix=mineru_render_pix,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                    clear_expand_min_pt=image_bg_clear_expand_min_pt,
                    clear_expand_max_pt=image_bg_clear_expand_max_pt,
                    clear_expand_ratio=image_bg_clear_expand_ratio,
                )

            bg_left = int(round(transform.offset_x_emu))
            bg_top = int(round(transform.offset_y_emu))
            bg_w = int(round(page_w_pt * _EMU_PER_PT * transform.scale))
            bg_h = int(round(page_h_pt * _EMU_PER_PT * transform.scale))
            slide.shapes.add_picture(
                str(cleaned_render_path),
                Emu(bg_left),
                Emu(bg_top),
                Emu(bg_w),
                Emu(bg_h),
            )
            mineru_background_placed = True
        except Exception:
            mineru_background_placed = False

    if (
        (not is_speed_ppt_generation)
        and ocr_sampling_pix is None
        and source_pdf.exists()
    ):
        if _page_needs_ocr_sampling_render(
            page_elements=page_text_elements_render,
            page_h_pt=float(page_h_pt),
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
        ):
            try:
                ocr_render_path = (
                    artifacts / "page_renders" / f"page-{page_index:04d}.ocr.png"
                )
                ocr_sampling_pix = _render_pdf_page_png(
                    source_pdf,
                    page_index=page_index,
                    dpi=int(scanned_render_dpi),
                    out_path=ocr_render_path,
                )
            except Exception:
                ocr_sampling_pix = None
            mineru_render_pix = None

    footer_fill_overlays: list[tuple[list[float], tuple[int, int, int]]] = []
    if page_text_elements_footer_removed and not mineru_background_placed:
        if ocr_sampling_pix is None and source_pdf.exists():
            try:
                footer_render_path = (
                    artifacts / "page_renders" / f"page-{page_index:04d}.footer.png"
                )
                ocr_sampling_pix = _render_pdf_page_png(
                    source_pdf,
                    page_index=page_index,
                    dpi=int(scanned_render_dpi),
                    out_path=footer_render_path,
                )
            except Exception:
                ocr_sampling_pix = None
        footer_fill_overlays = _build_notebooklm_footer_fill_overlays(
            footer_elements=page_text_elements_footer_removed,
            render_pix=ocr_sampling_pix,
            page_h_pt=float(page_h_pt),
            scanned_render_dpi=int(scanned_render_dpi),
            text_erase_mode=text_erase_mode_id,
        )

    for el in _iter_page_elements(page, type_name="image"):
        if (
            has_mineru_elements
            and not should_overlay_layout_images
            and _is_layout_parse_source(el.get("source"))
        ):
            continue
        bbox_pt = el.get("bbox_pt")
        image_path = el.get("image_path")
        if not image_path:
            continue
        img_path = _as_path(str(image_path))
        if not img_path.is_absolute():
            candidate = artifacts / img_path
            if candidate.exists():
                img_path = candidate
        if not img_path.exists():
            continue
        try:
            left, top, width, height = _bbox_pt_to_slide_emu(
                bbox_pt, transform=transform
            )
        except Exception:
            continue
        slide.shapes.add_picture(
            str(img_path), Emu(left), Emu(top), Emu(width), Emu(height)
        )

    for el in _iter_page_elements(page, type_name="table"):
        bbox_pt = el.get("bbox_pt")
        try:
            rows = int(el.get("rows") or 0)
            cols = int(el.get("cols") or 0)
        except Exception:
            rows, cols = 0, 0
        if rows <= 0 or cols <= 0:
            continue
        try:
            left, top, width, height = _bbox_pt_to_slide_emu(
                bbox_pt, transform=transform
            )
        except Exception:
            continue

        table_shape = slide.shapes.add_table(
            rows, cols, Emu(left), Emu(top), Emu(width), Emu(height)
        )
        table = table_shape.table

        cells = el.get("cells") or []
        if isinstance(cells, list) and cells:
            col_widths_pt = [0.0 for _ in range(cols)]
            row_heights_pt = [0.0 for _ in range(rows)]
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                r = int(cell.get("r") or 0)
                c = int(cell.get("c") or 0)
                if r < 0 or r >= rows or c < 0 or c >= cols:
                    continue
                try:
                    x0, y0, x1, y1 = _coerce_bbox_pt(cell.get("bbox_pt"))
                except Exception:
                    continue
                col_widths_pt[c] = max(col_widths_pt[c], x1 - x0)
                row_heights_pt[r] = max(row_heights_pt[r], y1 - y0)

            if sum(col_widths_pt) <= 0:
                col_widths_pt = [page_w_pt / cols for _ in range(cols)]
            if sum(row_heights_pt) <= 0:
                row_heights_pt = [page_h_pt / rows for _ in range(rows)]

            col_widths_emu = [
                int(round(w * _EMU_PER_PT * transform.scale)) for w in col_widths_pt
            ]
            row_heights_emu = [
                int(round(h * _EMU_PER_PT * transform.scale))
                for h in row_heights_pt
            ]

            if col_widths_emu:
                col_widths_emu[-1] += int(width - sum(col_widths_emu))
            if row_heights_emu:
                row_heights_emu[-1] += int(height - sum(row_heights_emu))

            for c, w in enumerate(col_widths_emu):
                table.columns[c].width = Emu(max(0, w))
            for r, h in enumerate(row_heights_emu):
                table.rows[r].height = Emu(max(0, h))

            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                r = int(cell.get("r") or 0)
                c = int(cell.get("c") or 0)
                if r < 0 or r >= rows or c < 0 or c >= cols:
                    continue
                text = _sanitize_markdown_text(str(cell.get("text") or ""))
                table.cell(r, c).text = text

    for bbox_pt, fill_rgb in footer_fill_overlays:
        try:
            left, top, width, height = _bbox_pt_to_slide_emu(
                bbox_pt, transform=transform
            )
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue
        cover_shape = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            Emu(left),
            Emu(top),
            Emu(width),
            Emu(height),
        )
        cover_shape.fill.solid()
        cover_shape.fill.fore_color.rgb = RGBColor(*fill_rgb)
        try:
            cover_shape.line.fill.background()
        except Exception:
            pass

    for el in page_text_elements_render:
        bbox_pt = el.get("bbox_pt")
        try:
            left, top, width, height = _bbox_pt_to_slide_emu(
                bbox_pt, transform=transform
            )
        except Exception:
            continue

        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        source_id = str(el.get("source") or "").strip().lower()
        is_mineru_text = _is_layout_parse_source(source_id)
        is_ocr_text = source_id == "ocr"
        ocr_linebreak_assisted = bool(el.get("ocr_linebreak_assisted"))
        raw_text = str(el.get("text") or "")
        text = _sanitize_markdown_text(raw_text)
        if is_mineru_text:
            text = "\n".join(
                [line.strip() for line in text.split("\n") if line.strip()]
            ).strip()
        elif is_ocr_text:
            text = _normalize_ocr_text_for_render(text)
        else:
            text = text.replace("\n", " ").strip()
        if not text:
            continue

        tx = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
        tf = tx.text_frame
        bbox_w_pt = max(1.0, x1 - x0)
        bbox_h_pt = max(1.0, y1 - y0)
        text_to_render = text
        sampled_bg_rgb: tuple[int, int, int] | None = None
        sampled_text_rgb: tuple[int, int, int] | None = None
        is_primary_heading = False
        if is_mineru_text:
            text_to_render, font_size_pt, wrap, is_heading, is_primary_heading = (
                _fit_mineru_text_style(
                    text=text,
                    bbox_w_pt=bbox_w_pt,
                    bbox_h_pt=bbox_h_pt,
                    page_w_pt=float(page_w_pt),
                    page_h_pt=float(page_h_pt),
                    y0_pt=float(y0),
                    mineru_block_type=el.get("mineru_block_type"),
                    mineru_text_level=el.get("mineru_text_level"),
                )
            )
            if not text_to_render.strip():
                continue
        elif is_ocr_text:
            compact_len = _compact_text_length(text)
            is_heading = bool(
                y0 <= 0.20 * float(page_h_pt)
                and bbox_h_pt >= 1.45 * float(baseline_ocr_h_pt)
                and compact_len <= 56
            )
            text_to_render, font_size_pt, wrap = _fit_ocr_text_style(
                text=text,
                bbox_w_pt=bbox_w_pt,
                bbox_h_pt=bbox_h_pt,
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                is_heading=is_heading,
            )

            if (
                has_mineru_elements
                and source_pdf.exists()
                and (mineru_render_pix is not None)
                and _should_sample_local_text_colors(
                    source_id="ocr",
                    element_color=el.get("color"),
                )
            ):
                try:
                    sampled_bg_rgb = _sample_bbox_background_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                    )
                    sampled_text_rgb = _sample_bbox_text_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                        bg_rgb=sampled_bg_rgb,
                    )
                except Exception:
                    sampled_bg_rgb = None
                    sampled_text_rgb = None
        else:
            wrap = False
            font_size_pt = _infer_font_size_pt(el, bbox_h_pt=bbox_h_pt)
            is_heading = False

        if is_mineru_text:
            if is_heading and not wrap:
                nudge_right_pt = min(
                    14.0,
                    max(
                        4.0,
                        0.22 * float(bbox_h_pt),
                        0.72 * float(font_size_pt),
                    ),
                )
            elif wrap:
                nudge_right_pt = min(
                    10.0,
                    max(
                        3.0,
                        0.16 * float(bbox_h_pt),
                        0.50 * float(font_size_pt),
                    ),
                )
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
            max_box_w = max(1, int(slide_w_emu) - int(left))
            textbox_width = max(1, min(int(width) + nudge_right_emu, max_box_w))
            try:
                tx.width = Emu(textbox_width)
            except Exception:
                pass
        elif is_ocr_text and ocr_linebreak_assisted and not wrap:
            nudge_right_pt = min(
                6.0,
                max(
                    1.6,
                    0.10 * float(bbox_h_pt),
                    0.26 * float(font_size_pt),
                ),
            )
            nudge_right_emu = int(
                round(float(nudge_right_pt) * _EMU_PER_PT * transform.scale)
            )
            max_box_w = max(1, int(slide_w_emu) - int(left))
            textbox_width = max(1, min(int(width) + nudge_right_emu, max_box_w))
            try:
                tx.width = Emu(textbox_width)
            except Exception:
                pass

        tf.word_wrap = False if is_mineru_text else bool(wrap)
        tf.auto_size = MSO_AUTO_SIZE.NONE
        try:
            tf.vertical_anchor = MSO_ANCHOR.TOP
        except Exception:
            pass
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        tf.text = text_to_render

        if is_mineru_text or is_ocr_text:
            for p in tf.paragraphs:
                try:
                    if is_primary_heading:
                        p.alignment = PP_ALIGN.CENTER
                except Exception:
                    pass
                try:
                    p.line_spacing = 1.0
                    p.space_before = Pt(0)
                    p.space_after = Pt(0)
                except Exception:
                    pass

        mapped_font = _map_font_name(el.get("font_name"))
        rgb = _hex_to_rgb(el.get("color"))
        if is_mineru_text and mineru_render_pix is not None:
            if _should_sample_local_text_colors(
                source_id=source_id,
                element_color=el.get("color"),
            ):
                try:
                    sampled_bg_rgb = _sample_bbox_background_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                    )
                    sampled_text_rgb = _sample_bbox_text_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                        bg_rgb=sampled_bg_rgb,
                    )
                except Exception:
                    sampled_bg_rgb = None
                    sampled_text_rgb = None
        elif (
            is_ocr_text
            and sampled_bg_rgb is None
            and ocr_sampling_pix is not None
            and _should_sample_local_text_colors(
                source_id=source_id,
                element_color=el.get("color"),
            )
        ):
            try:
                sampled_bg_rgb = _sample_bbox_background_rgb(
                    ocr_sampling_pix,
                    bbox_pt=bbox_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                )
                sampled_text_rgb = _sample_bbox_text_rgb(
                    ocr_sampling_pix,
                    bbox_pt=bbox_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                    bg_rgb=sampled_bg_rgb,
                )
            except Exception:
                sampled_bg_rgb = None
                sampled_text_rgb = None
        if rgb is None and sampled_bg_rgb is not None:
            if sampled_text_rgb is not None:
                rgb = sampled_text_rgb
            else:
                rgb = _pick_contrasting_text_rgb(sampled_bg_rgb)
        elif rgb is not None and sampled_bg_rgb is not None:
            if _rgb_sq_distance(rgb, sampled_bg_rgb) < (32 * 32):
                if sampled_text_rgb is not None:
                    rgb = sampled_text_rgb
                else:
                    rgb = _pick_contrasting_text_rgb(sampled_bg_rgb)
        applied = False
        for p in tf.paragraphs:
            for run in p.runs:
                font = run.font
                font.size = Pt(float(font_size_pt))
                if mapped_font:
                    font.name = mapped_font
                elif is_mineru_text:
                    font.name = (
                        "Microsoft YaHei"
                        if _contains_cjk(text_to_render)
                        else "Arial"
                    )
                elif is_ocr_text:
                    font.name = (
                        "Microsoft YaHei"
                        if _contains_cjk(text_to_render)
                        else "Arial"
                    )
                font.bold = bool(el.get("bold")) if "bold" in el else None
                font.italic = bool(el.get("italic")) if "italic" in el else None
                if rgb:
                    font.color.rgb = RGBColor(*rgb)
                applied = True

        if not applied:
            continue

    _maybe_export_final_preview_page_image(
        enabled=should_export_final_previews,
        page=page,
        page_index=page_index,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        source_pdf=source_pdf,
        artifacts_dir=artifacts,
        dpi=int(scanned_render_dpi),
    )
