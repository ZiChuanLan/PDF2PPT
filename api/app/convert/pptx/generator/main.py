"""Main entrypoint for generating PPTX from IR.

Large branches extracted to:
- _scanned_page.py   (scanned-page slide building)
- _text_page.py      (text-layer slide building)
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ....models.error import AppException, ErrorCode

from ..bbox_utils import (
    _as_path,
    _coerce_bbox_pt,
    _ensure_parent_dir,
)
from ..constants import _EMU_PER_INCH, _EMU_PER_PT
from ..font_utils import (
    _is_inline_short_token,
)
from ..scanned_page import (
    _estimate_baseline_ocr_line_height_pt,
)
from ..slide_builder import (
    _build_transform,
    _iter_page_elements,
    _set_slide_size_type,
)

from ._parameter_parser import normalise_parameters
from ._scanned_page import (
    _build_scanned_page_slide,
    _is_layout_parse_source,
)
from ._text_page import _build_text_page_slide
from .footer import (
    _is_notebooklm_footer_text_element,
)


def generate_pptx_from_ir(
    ir: dict[str, Any],
    output_pptx_path: str | Path,
    *,
    artifacts_dir: str | Path | None = None,
    force_16x9: bool = False,
    scanned_render_dpi: int = 200,
    remove_footer_notebooklm: bool = False,
    scanned_page_mode: str = "segmented",
    text_erase_mode: str = "fill",
    ppt_generation_mode: str = "standard",
    image_bg_clear_expand_min_pt: float = 0.35,
    image_bg_clear_expand_max_pt: float = 1.5,
    image_bg_clear_expand_ratio: float = 0.012,
    scanned_image_region_min_area_ratio: float = 0.0025,
    scanned_image_region_max_area_ratio: float = 0.72,
    scanned_image_region_max_aspect_ratio: float = 4.8,
    export_final_preview_images: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Generate a PPTX from the provided IR.

    Args:
        ir: The intermediate representation dict.
        output_pptx_path: Where to write the PPTX file.
        artifacts_dir: Directory for any intermediate artifacts (e.g. scanned page renders).
        force_16x9: If True, use a 16:9 slide size and letterbox PDF content.
        scanned_render_dpi: DPI used when rendering scanned pages to images.
        remove_footer_notebooklm: Whether to drop detected bottom-right
            NotebookLM footer branding text from the exported PPT.
        text_erase_mode: Erase strategy for background cleanup (smart, fill).
        ppt_generation_mode: PPT generation mode (standard, fast, turbo). Fast
            and turbo prioritize speed over visual fidelity, with turbo being
            the most aggressive.
        image_bg_clear_expand_min_pt: Min outward expansion (pt) when clearing
            background under overlaid image crops.
        image_bg_clear_expand_max_pt: Max outward expansion (pt) when clearing
            background under overlaid image crops.
        image_bg_clear_expand_ratio: Expansion ratio against crop min dimension.
        scanned_image_region_min_area_ratio: Min page area ratio for scanned
            image-region candidate filtering.
        scanned_image_region_max_area_ratio: Max page area ratio for scanned
            image-region candidate filtering.
        scanned_image_region_max_aspect_ratio: Max aspect ratio threshold for
            suppressing long narrow scanned-image candidates.
        export_final_preview_images: Whether to export per-page final preview
            snapshots into `artifacts/final_preview`.
        progress_callback: Optional callback(done_pages, total_pages), called
            after each IR page is written.

    Returns:
        The output PPTX path.
    """

    try:
        pptx = importlib.import_module("pptx")
        Presentation = getattr(pptx, "Presentation")

        RGBColor = getattr(importlib.import_module("pptx.dml.color"), "RGBColor")
        text_enums = importlib.import_module("pptx.enum.text")
        MSO_AUTO_SIZE = getattr(text_enums, "MSO_AUTO_SIZE")
        MSO_ANCHOR = getattr(text_enums, "MSO_ANCHOR")
        PP_ALIGN = getattr(text_enums, "PP_ALIGN")
        shape_enums = importlib.import_module("pptx.enum.shapes")
        MSO_AUTO_SHAPE_TYPE = getattr(shape_enums, "MSO_AUTO_SHAPE_TYPE")
        util = importlib.import_module("pptx.util")
        Emu = getattr(util, "Emu")
        Pt = getattr(util, "Pt")
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="python-pptx is required to generate PPTX output",
            details={"error": str(e)},
        )

    pages = ir.get("pages")
    if not isinstance(pages, list) or not pages:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR is missing pages[]",
        )

    first_page = pages[0] if isinstance(pages[0], dict) else None
    if not first_page:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR pages[0] is invalid",
        )

    params = normalise_parameters(
        text_erase_mode=text_erase_mode,
        scanned_page_mode=scanned_page_mode,
        ppt_generation_mode=ppt_generation_mode,
        scanned_render_dpi=scanned_render_dpi,
        image_bg_clear_expand_min_pt=image_bg_clear_expand_min_pt,
        image_bg_clear_expand_max_pt=image_bg_clear_expand_max_pt,
        image_bg_clear_expand_ratio=image_bg_clear_expand_ratio,
        scanned_image_region_min_area_ratio=scanned_image_region_min_area_ratio,
        scanned_image_region_max_area_ratio=scanned_image_region_max_area_ratio,
        scanned_image_region_max_aspect_ratio=scanned_image_region_max_aspect_ratio,
    )
    text_erase_mode_id = params["text_erase_mode_id"]
    scanned_page_mode_id = params["scanned_page_mode_id"]
    ppt_generation_mode_id = params["ppt_generation_mode_id"]
    is_fast_ppt_generation = params["is_fast_ppt_generation"]
    is_turbo_ppt_generation = params["is_turbo_ppt_generation"]
    is_speed_ppt_generation = params["is_speed_ppt_generation"]
    scanned_render_dpi = params["scanned_render_dpi"]
    image_bg_clear_expand_min_pt_id = params["image_bg_clear_expand_min_pt"]
    image_bg_clear_expand_max_pt_id = params["image_bg_clear_expand_max_pt"]
    image_bg_clear_expand_ratio_id = params["image_bg_clear_expand_ratio"]
    scanned_image_region_min_area_ratio_id = params["scanned_image_region_min_area_ratio"]
    scanned_image_region_max_area_ratio_id = params["scanned_image_region_max_area_ratio"]
    scanned_image_region_max_aspect_ratio_id = params["scanned_image_region_max_aspect_ratio"]

    try:
        first_w_pt = float(first_page.get("page_width_pt") or 0.0)
        first_h_pt = float(first_page.get("page_height_pt") or 0.0)
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR page dimensions are invalid",
            details={"error": str(e)},
        )

    if first_w_pt <= 0 or first_h_pt <= 0:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR page dimensions are missing",
            details={"page_width_pt": first_w_pt, "page_height_pt": first_h_pt},
        )

    out_path = _as_path(output_pptx_path)
    _ensure_parent_dir(out_path)

    artifacts = (
        _as_path(artifacts_dir)
        if artifacts_dir is not None
        else (out_path.parent / "artifacts")
    )
    artifacts.mkdir(parents=True, exist_ok=True)

    prs = Presentation()

    if force_16x9:
        # 13.333" x 7.5" is the common widescreen (16:9) size.
        slide_w_emu = int(round(13.333 * _EMU_PER_INCH))
        slide_h_emu = int(round(7.5 * _EMU_PER_INCH))
    else:
        # Default: 1:1 mapping with PDF points (8.5x11 for letter, etc.).
        slide_w_emu = int(round(first_w_pt * _EMU_PER_PT))
        slide_h_emu = int(round(first_h_pt * _EMU_PER_PT))

    prs.slide_width = Emu(slide_w_emu)
    prs.slide_height = Emu(slide_h_emu)
    _set_slide_size_type(prs, slide_w_emu=slide_w_emu, slide_h_emu=slide_h_emu)

    blank_layout = prs.slide_layouts[6]
    source_pdf = _as_path(str(ir.get("source_pdf") or ""))
    total_pages = sum(1 for page in pages if isinstance(page, dict))
    should_export_final_previews = bool(export_final_preview_images) and (
        not is_speed_ppt_generation
    )
    done_pages = 0

    def _notify_page_done() -> None:
        nonlocal done_pages
        done_pages += 1
        if progress_callback:
            try:
                progress_callback(done_pages, max(1, total_pages))
            except Exception:
                pass

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("page_index") or 0)
        page_w_pt = float(page.get("page_width_pt") or first_w_pt)
        page_h_pt = float(page.get("page_height_pt") or first_h_pt)

        transform = _build_transform(
            page_width_pt=page_w_pt,
            page_height_pt=page_h_pt,
            slide_width_emu=slide_w_emu,
            slide_height_emu=slide_h_emu,
        )

        slide = prs.slides.add_slide(blank_layout)
        has_text_layer = bool(page.get("has_text_layer"))
        page_elements = [
            el for el in (page.get("elements") or []) if isinstance(el, dict)
        ]
        page_text_elements_all = [
            el
            for el in _iter_page_elements(page, type_name="text")
            if isinstance(el, dict)
        ]
        page_text_elements_render = [
            el
            for el in page_text_elements_all
            if not (
                bool(remove_footer_notebooklm)
                and _is_notebooklm_footer_text_element(
                    el,
                    page_w_pt=float(page_w_pt),
                    page_h_pt=float(page_h_pt),
                )
            )
        ]
        page_text_elements_footer_removed = [
            el
            for el in page_text_elements_all
            if bool(remove_footer_notebooklm)
            and _is_notebooklm_footer_text_element(
                el,
                page_w_pt=float(page_w_pt),
                page_h_pt=float(page_h_pt),
            )
        ]
        page_ocr_text_elements = [
            el
            for el in page_text_elements_render
            if str(el.get("source") or "").strip().lower() == "ocr"
        ]
        baseline_ocr_h_pt = (
            _estimate_baseline_ocr_line_height_pt(
                ocr_text_elements=page_ocr_text_elements,
                page_w_pt=float(page_w_pt),
            )
            if page_ocr_text_elements
            else 12.0
        )
        has_mineru_elements = any(
            _is_layout_parse_source(el.get("source")) for el in page_elements
        )

        if not has_text_layer:
            _build_scanned_page_slide(
                slide=slide,
                page=page,
                page_index=page_index,
                page_w_pt=float(page_w_pt),
                page_h_pt=float(page_h_pt),
                transform=transform,
                source_pdf=source_pdf,
                artifacts=artifacts,
                scanned_render_dpi=int(scanned_render_dpi),
                text_erase_mode_id=text_erase_mode_id,
                scanned_page_mode_id=scanned_page_mode_id,
                is_speed_ppt_generation=is_speed_ppt_generation,
                image_bg_clear_expand_min_pt=image_bg_clear_expand_min_pt_id,
                image_bg_clear_expand_max_pt=image_bg_clear_expand_max_pt_id,
                image_bg_clear_expand_ratio=image_bg_clear_expand_ratio_id,
                scanned_image_region_min_area_ratio=scanned_image_region_min_area_ratio_id,
                scanned_image_region_max_area_ratio=scanned_image_region_max_area_ratio_id,
                scanned_image_region_max_aspect_ratio=scanned_image_region_max_aspect_ratio_id,
                remove_footer_notebooklm=bool(remove_footer_notebooklm),
                should_export_final_previews=should_export_final_previews,
                slide_w_emu=int(slide_w_emu),
                slide_h_emu=int(slide_h_emu),
                page_text_elements_all=page_text_elements_all,
                page_text_elements_render=page_text_elements_render,
                page_text_elements_footer_removed=page_text_elements_footer_removed,
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                Emu=Emu,
                Pt=Pt,
                RGBColor=RGBColor,
                MSO_AUTO_SIZE=MSO_AUTO_SIZE,
                MSO_ANCHOR=MSO_ANCHOR,
                PP_ALIGN=PP_ALIGN,
            )
            _notify_page_done()
            continue

        # Text-based page: place elements directly.
        _build_text_page_slide(
            slide=slide,
            page=page,
            page_index=page_index,
            page_w_pt=float(page_w_pt),
            page_h_pt=float(page_h_pt),
            transform=transform,
            source_pdf=source_pdf,
            artifacts=artifacts,
            scanned_render_dpi=int(scanned_render_dpi),
            text_erase_mode_id=text_erase_mode_id,
            scanned_page_mode_id=scanned_page_mode_id,
            is_speed_ppt_generation=is_speed_ppt_generation,
            image_bg_clear_expand_min_pt=image_bg_clear_expand_min_pt_id,
            image_bg_clear_expand_max_pt=image_bg_clear_expand_max_pt_id,
            image_bg_clear_expand_ratio=image_bg_clear_expand_ratio_id,
            remove_footer_notebooklm=bool(remove_footer_notebooklm),
            should_export_final_previews=should_export_final_previews,
            slide_w_emu=int(slide_w_emu),
            slide_h_emu=int(slide_h_emu),
            page_text_elements_all=page_text_elements_all,
            page_text_elements_render=page_text_elements_render,
            page_text_elements_footer_removed=page_text_elements_footer_removed,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            has_mineru_elements=has_mineru_elements,
            Emu=Emu,
            Pt=Pt,
            RGBColor=RGBColor,
            MSO_AUTO_SIZE=MSO_AUTO_SIZE,
            MSO_ANCHOR=MSO_ANCHOR,
            PP_ALIGN=PP_ALIGN,
            MSO_AUTO_SHAPE_TYPE=MSO_AUTO_SHAPE_TYPE,
        )
        _notify_page_done()

    prs.save(str(out_path))
    return out_path
