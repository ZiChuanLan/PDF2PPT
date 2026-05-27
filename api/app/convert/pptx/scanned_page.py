"""Scanned-page rendering and image-region processing (re-export hub).

Implementation lives in sub-modules under this package:
- _scanned_render.py         — render, pixel helpers, OCR line-height estimation
- _scanned_region_detect.py  — heuristic region detection + shape analysis
- _scanned_color.py          — color sampling (background, text)
- _scanned_ink.py            — ink/line visual detection
- _scanned_erase.py          — image erasure, background cleanup, transparency
- _scanned_region_build.py   — region building, merging, tightening, dedupe
"""

from ._scanned_render import (
    _apply_max_filter_l,
    _estimate_baseline_ocr_line_height_pt,
    _pixel_to_int,
    _pixel_to_rgb_triplet,
    _render_pdf_page_png,
)
from ._scanned_region_detect import (
    _analyze_shape_crop,
    _coerce_polygon_points_pt,
    _element_polygon_points_px,
    _is_shape_confirmed_crop,
    _pdf_pt_to_pix_px,
    _polygon_points_pt_to_px,
)
from ._scanned_color import (
    _pix_to_rgb_array,
    _sample_bbox_background_rgb,
    _sample_bbox_text_rgb,
    _sample_pixmap_rgb,
)
from ._scanned_ink import _estimate_bbox_ink_line_count
from ._scanned_erase import (
    _clear_regions_for_transparent_crops,
    _erase_regions_in_render_image,
    _try_make_crop_background_transparent,
)
from ._scanned_region_build import (
    _apply_text_cutouts_to_scanned_image_region_crops,
    _build_scanned_image_region_infos,
    _build_scanned_image_region_suppress_bbox,
    _collect_scanned_image_region_candidates,
    _coerce_image_region_entry_pt,
    _dedupe_scanned_ocr_text_elements,
    _filter_scanned_ocr_text_elements,
    _geometry_points_signature,
    _is_card_like_region,
    _is_small_text_fragment_region,
    _merge_neighbor_boxes_pt,
    _project_bbox_pt_to_local_crop_rect,
    _project_polygon_points_pt_to_local_crop,
    _save_scanned_image_region_crop,
    _save_scanned_regions_debug_overlay,
    _ScannedImageRegionInfo,
    _tighten_scanned_image_region_bbox_by_visual_bounds,
    _tighten_scanned_image_region_infos,
    _try_merge_fragmented_scanned_image_regions,
)
