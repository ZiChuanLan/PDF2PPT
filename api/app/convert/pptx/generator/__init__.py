"""PPTX generator sub-package."""

from .main import generate_pptx_from_ir
from .probing import (
    _maybe_export_final_preview_page_image,
    _should_probe_visual_wrap_for_ocr_text,
    _should_sample_local_text_colors,
    _page_needs_ocr_sampling_render,
    _should_center_scanned_heading,
)
from .text_erase import _merge_text_erase_bboxes
from .markdown_utils import _sanitize_markdown_text, _normalize_footer_brand_text
from .footer import (
    _is_notebooklm_footer_brand_normalized,
    _is_notebooklm_footer_text_element,
    _detect_notebooklm_footer_bbox_from_render,
    _build_notebooklm_footer_fill_overlays,
)

__all__ = ["generate_pptx_from_ir"]
