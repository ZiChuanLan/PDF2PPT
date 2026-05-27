from .debug import (
    _build_ocr_effective_runtime_debug,
)
from .geometry_utils import (
    _bbox_center_distance_ratio,
    _bbox_overlap_ratio,
    _bbox_pt_to_px,
    _coerce_bbox_pt,
    _normalize_match_text,
)
from .guarded import run_blocking_with_guards
from .layout import (
    _apply_ai_tables,
    _extract_warning_suffix,
    _layout_page_signature,
    _to_page_map,
)
from .ocr_runtime import build_ocr_debug_payload, setup_ocr_runtime
from .ocr_stage import run_ocr_stage
from .ppt_stage import run_ppt_stage

__all__ = [
    "_apply_ai_tables",
    "_bbox_center_distance_ratio",
    "_bbox_overlap_ratio",
    "_bbox_pt_to_px",
    "_build_ocr_effective_runtime_debug",
    "_coerce_bbox_pt",
    "_extract_warning_suffix",
    "_layout_page_signature",
    "_normalize_match_text",
    "build_ocr_debug_payload",
    "run_blocking_with_guards",
    "run_ocr_stage",
    "run_ppt_stage",
    "setup_ocr_runtime",
    "_to_page_map",
]
