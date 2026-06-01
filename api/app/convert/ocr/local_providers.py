"""Local OCR providers, manager orchestration, and conversion helpers.

This module is now a thin re-export hub.  Implementation classes and helpers
have been moved to sub-modules prefixed with ``_`` to keep the public API
stable while reducing individual file sizes.
"""

# Shared constants retained on this facade for backward-compatible imports.
from .base import (
    _DEFAULT_PADDLE_OCR_VL_MODEL,
    _PADDLE_OCR_VL_MODEL_V1,
    _PADDLE_OCR_VL_MODEL_V15,
)
from .ai_client import AiOcrClient, AiOcrTextRefiner

# Remote OCR client spec and factory functions
from ._ocr_remote import (
    RemoteOcrClientSpec,
    _build_remote_ocr_client,
    _build_remote_ocr_client_from_spec,
    _resolve_remote_ocr_client_spec,
    create_remote_ocr_client,
    resolve_remote_ocr_client_spec,
)

# Individual OCR provider implementations
from ._baidu_ocr import BaiduOcrClient
from ._tesseract_ocr import TesseractOcrClient
from ._paddle_ocr import LazyPaddleOcrClient, PaddleOcrClient

# OcrManager orchestrator and factory
from ._ocr_manager import OcrManager, create_ocr_manager

# Post-processing chain functions
from ._ocr_postprocess import (
    _bbox_iou,
    _bbox_overlap_smaller,
    _build_primary_ocr_quality_notes,
    _convert_geometry_points_px_to_pdf_coords,
    _dedupe_overlapping_ocr_items,
    _filter_contextual_noise_items,
    _is_probably_noise_line,
    _merge_line_items_prefer_primary,
    _merge_ocr_items_to_lines,
    _normalize_bbox_px,
    _normalize_ocr_items_as_lines,
    _normalize_text_for_dedupe,
    _sample_text_color,
    _texts_are_similar_for_dedupe,
    ocr_image_to_elements,
)

# Runtime probes (re-exported from runtime_probe for backward compat)
from .runtime_probe import (
    probe_local_paddle_models,
    probe_local_paddleocr,
    probe_local_tesseract,
    probe_local_tesseract_models,
)

__all__ = [
    "BaiduOcrClient",
    "AiOcrClient",
    "AiOcrTextRefiner",
    "LazyPaddleOcrClient",
    "OcrManager",
    "PaddleOcrClient",
    "RemoteOcrClientSpec",
    "TesseractOcrClient",
    "_DEFAULT_PADDLE_OCR_VL_MODEL",
    "_PADDLE_OCR_VL_MODEL_V1",
    "_PADDLE_OCR_VL_MODEL_V15",
    "_bbox_iou",
    "_bbox_overlap_smaller",
    "_build_primary_ocr_quality_notes",
    "_build_remote_ocr_client",
    "_build_remote_ocr_client_from_spec",
    "_convert_geometry_points_px_to_pdf_coords",
    "_dedupe_overlapping_ocr_items",
    "_filter_contextual_noise_items",
    "_is_probably_noise_line",
    "_merge_line_items_prefer_primary",
    "_merge_ocr_items_to_lines",
    "_normalize_bbox_px",
    "_normalize_ocr_items_as_lines",
    "_normalize_text_for_dedupe",
    "_resolve_remote_ocr_client_spec",
    "_sample_text_color",
    "_texts_are_similar_for_dedupe",
    "create_ocr_manager",
    "create_remote_ocr_client",
    "ocr_image_to_elements",
    "probe_local_paddle_models",
    "probe_local_paddleocr",
    "probe_local_tesseract",
    "probe_local_tesseract_models",
    "resolve_remote_ocr_client_spec",
]
