"""Local OCR providers, manager orchestration, and conversion helpers."""

from dataclasses import dataclass
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from app.config import get_settings

# ---------------------------------------------------------------------------
# Constants: Baidu OCR thresholds
# ---------------------------------------------------------------------------
_BAIDU_AREA_RATIO_PRUNE_THRESHOLD = 0.16
"""Area ratio above which a Baidu OCR box is considered a coarse paragraph."""

_BAIDU_WIDTH_RATIO_PRUNE_THRESHOLD = 0.85
"""Width ratio threshold for wide+short paragraph detection."""

_BAIDU_HEIGHT_RATIO_PRUNE_THRESHOLD = 0.08
"""Height ratio threshold for wide+short paragraph detection."""

_BAIDU_COMPACT_TEXT_LENGTH_LIMIT = 24
"""Max compact text length for wide+short paragraph pruning."""

_BAIDU_AREA_RATIO_THRESHOLD_ALT = 0.06
"""Alternative area ratio threshold for short-text pruning."""

_BAIDU_COMPACT_TEXT_LENGTH_LIMIT_ALT = 6
"""Alternative compact text length limit for short-text pruning."""

_BAIDU_HEIGHT_RATIO_THRESHOLD_ALT = 0.06
"""Alternative height ratio threshold for short-text pruning."""

_BAIDU_DEFAULT_CONFIDENCE = 0.95
"""Default confidence for Baidu OCR results (Baidu doesn't reliably return confidences)."""

# ---------------------------------------------------------------------------
# Constants: Tesseract OCR thresholds
# ---------------------------------------------------------------------------
_TESSERACT_DEFAULT_MIN_CONFIDENCE = 50.0
"""Default minimum confidence threshold for Tesseract OCR (0-100 scale)."""

_TESSERACT_PSM_SPARSE_TEXT = 11
"""Tesseract PSM mode for sparse text (best for slides/scanned pages)."""

_TESSERACT_LOW_RECALL_LINE_THRESHOLD = 12
"""Line count below which we consider the result low recall."""

_TESSERACT_LOW_RECALL_WORD_THRESHOLD = 80
"""Word count below which we consider the result low recall."""

_TESSERACT_LOW_CONFIDENCE_RETRY_THRESHOLD = 25.0
"""Confidence threshold below which we retry with lower confidence."""

_TESSERACT_LOOKS_EMPTY_LINE_THRESHOLD = 8
"""Line count below which the result looks empty."""

_TESSERACT_LOOKS_EMPTY_WORD_THRESHOLD = 40
"""Word count below which the result looks empty."""

# ---------------------------------------------------------------------------
# Constants: PaddleOCR thresholds
# ---------------------------------------------------------------------------
_PADDLE_OCR_DEFAULT_CONFIDENCE = 0.85
"""Default confidence for PaddleOCR results when not provided."""

_PADDLE_OCR_MAX_NODES_FOR_TRAVERSAL = 20000
"""Maximum nodes to visit when traversing PaddleOCR result tree."""

# ---------------------------------------------------------------------------
# Constants: OCR merge / normalization
# ---------------------------------------------------------------------------
_MERGE_GAP_THRESHOLD_MULTIPLIER = 1.8
"""Multiplier for median line height in horizontal gap threshold calculation."""

_MERGE_GAP_THRESHOLD_RATIO = 0.025
"""Ratio of image width for horizontal gap threshold calculation."""

_MERGE_Y_THRESHOLD_MULTIPLIER = 0.70
"""Multiplier for median line height in Y-center threshold calculation."""

_MERGE_Y_THRESHOLD_RATIO = 0.006
"""Ratio of image height for Y-center threshold calculation."""

# ---------------------------------------------------------------------------
# Constants: Band clustering (line merging)
# ---------------------------------------------------------------------------
_BAND_X_GAP_THRESHOLD_RATIO = 0.04
"""Ratio of image width for horizontal gap threshold in band clustering."""

_BAND_X_GAP_THRESHOLD_HEIGHT_MULTIPLIER = 6.0
"""Multiplier for median height in horizontal gap threshold."""

_BAND_CLOSE_Y_THRESHOLD_MULTIPLIER = 0.55
"""Multiplier for median height in close-Y detection."""

_BAND_OVERLAP_THRESHOLD_MULTIPLIER = 0.35
"""Multiplier for overlap threshold relative to min box height."""

# ---------------------------------------------------------------------------
# Constants: Noise detection
# ---------------------------------------------------------------------------
_NOISE_AREA_RATIO_THRESHOLD = 0.3
"""Area ratio threshold for noise detection (box too large relative to image)."""

_NOISE_HEIGHT_RATIO_THRESHOLD = 0.08
"""Height ratio threshold for noise detection (box too tall)."""

_NOISE_MIN_TEXT_LENGTH = 3
"""Minimum text length to not be considered noise."""

_NOISE_WIDTH_RATIO_THRESHOLD_ALT = 0.08
"""Alternative width ratio threshold for noise detection."""

_NOISE_HEIGHT_RATIO_THRESHOLD_ALT = 0.08
"""Alternative height ratio threshold for noise detection."""

_NOISE_MIN_TEXT_LENGTH_ALT = 2
"""Alternative minimum text length for noise detection."""

# ---------------------------------------------------------------------------
# Constants: Coarse AI paragraph pruning
# ---------------------------------------------------------------------------
_COARSE_AI_PRUNE_WIDTH_RATIO = 0.90
"""Width ratio threshold for pruning coarse AI paragraph boxes."""

_COARSE_AI_PRUNE_HEIGHT_RATIO = 0.16
"""Height ratio threshold for pruning coarse AI paragraph boxes."""

# ---------------------------------------------------------------------------
# Constants: Overlap merge threshold
# ---------------------------------------------------------------------------
_OVERLAP_MERGE_THRESHOLD = 0.90
"""Overlap ratio threshold for merging overlapping boxes."""

# ---------------------------------------------------------------------------
# Constants: OCR item deduplication
# ---------------------------------------------------------------------------
_DEDUPE_STRONG_SAME_BBOX_OVERLAP = 0.985
"""Overlap ratio for strong same-bbox duplicate detection."""

_DEDUPE_STRONG_SAME_BBOX_IOU = 0.90
"""IoU threshold for strong same-bbox duplicate detection."""

_DEDUPE_NEAR_SAME_BBOX_OVERLAP = 0.965
"""Overlap ratio for near same-bbox duplicate detection."""

_DEDUPE_NEAR_SAME_BBOX_IOU = 0.85
"""IoU threshold for near same-bbox duplicate detection."""

_DEDUPE_EXACT_LIKE_OVERLAP = 0.93
"""Overlap ratio for exact-like duplicate detection."""

_DEDUPE_SINGLE_PROVIDER_OVERLAP = 0.85
"""Overlap ratio for single-provider duplicate detection."""

_DEDUPE_SINGLE_PROVIDER_OVERLAP_ALT = 0.70
"""Alternative overlap ratio for single-provider duplicate detection."""

_DEDUPE_SINGLE_PROVIDER_IOU = 0.55
"""IoU threshold for single-provider duplicate detection."""

_DEDUPE_MULTI_PROVIDER_OVERLAP = 0.88
"""Overlap ratio for multi-provider duplicate detection."""

_DEDUPE_MULTI_PROVIDER_IOU = 0.78
"""IoU threshold for multi-provider duplicate detection."""

_DEDUPE_MULTI_PROVIDER_IOU_ALT = 0.62
"""Alternative IoU threshold for multi-provider duplicate detection."""

_DEDUPE_TEXT_SIMILARITY_SHORT_RATIO = 0.65
"""Minimum short/long ratio for text similarity deduplication."""

_DEDUPE_SINGLE_PROVIDER_Y_THRESHOLD_MULTIPLIER = 0.55
"""Multiplier for median height in single-provider Y-center deduplication."""

# ---------------------------------------------------------------------------
# Constants: Text color sampling (BT.709 luma coefficients)
# ---------------------------------------------------------------------------
_LUMA_COEFF_RED = 0.2126
"""BT.709 luma coefficient for red channel."""

_LUMA_COEFF_GREEN = 0.7152
"""BT.709 luma coefficient for green channel."""

_LUMA_COEFF_BLUE = 0.0722
"""BT.709 luma coefficient for blue channel."""

_COLOR_SAMPLE_BG_PAD_MIN = 3
"""Minimum padding pixels for background sampling."""

_COLOR_SAMPLE_BG_PAD_MAX = 12
"""Maximum padding pixels for background sampling."""

_COLOR_SAMPLE_BG_PAD_RATIO = 0.03
"""Ratio of box size for background padding calculation."""

_COLOR_SAMPLE_STEP_DIVISOR = 2400.0
"""Divisor for calculating scan step size from area."""

_COLOR_SAMPLE_FOREGROUND_CONTRAST_THRESHOLD = 8.0
"""Minimum contrast to consider a pixel as foreground."""

_COLOR_SAMPLE_BG_LUMA_MIDPOINT = 128.0
"""Luma midpoint for determining dark/light background."""

_COLOR_SAMPLE_PREFERRED_CONTRAST_THRESHOLD = 14.0
"""Contrast threshold for preferred foreground candidates."""

_COLOR_SAMPLE_FALLBACK_CONTRAST_THRESHOLD = 18.0
"""Contrast threshold for fallback foreground candidates."""

_COLOR_SAMPLE_DISTANCE_THRESHOLD = 900.0
"""RGB distance threshold for color candidate selection."""

_COLOR_SAMPLE_TOP_CANDIDATE_COUNT = 12
"""Number of top candidates to consider for color sampling."""

_COLOR_SAMPLE_KEEP_COUNT_MIN = 6
"""Minimum number of candidates to keep."""

_COLOR_SAMPLE_KEEP_COUNT_MAX = 96
"""Maximum number of candidates to keep."""

_COLOR_SAMPLE_KEEP_COUNT_DIVISOR = 4
"""Divisor for calculating keep count from preferred list."""

_COLOR_SAMPLE_DARKER_THRESHOLD = 6.0
"""Luma difference threshold for darker-than-background detection."""

_COLOR_SAMPLE_LIGHTER_THRESHOLD = 6.0
"""Luma difference threshold for lighter-than-background detection."""

_COLOR_SAMPLE_MAX_CHOSEN_RGBS = 24
"""Maximum number of RGB values to use for median calculation."""

_COLOR_SAMPLE_MIN_LUMA_CONTRAST = 18.0
"""Minimum luma contrast for final color validation."""

_COLOR_SAMPLE_FALLBACK_DARK_TEXT = 17
"""Fallback dark text color value."""

_COLOR_SAMPLE_FALLBACK_LIGHT_TEXT = 245
"""Fallback light text color value."""

# ---------------------------------------------------------------------------
# Constants: OCR quality notes
# ---------------------------------------------------------------------------
_QUALITY_NOTES_LANDSCAPE_ASPECT_RATIO = 1.18
"""Aspect ratio threshold for landscape slide detection."""

_QUALITY_NOTES_LARGE_BOX_HEIGHT_MULTIPLIER = 1.7
"""Multiplier for median height in large box detection."""

_QUALITY_NOTES_LARGE_BOX_HEIGHT_RATIO = 0.075
"""Height ratio for large box detection."""

_QUALITY_NOTES_LARGE_BOX_WIDTH_RATIO = 0.22
"""Width ratio for large box detection."""

_QUALITY_NOTES_LARGE_BOX_TEXT_LENGTH = 20
"""Text length threshold for large box detection."""

_QUALITY_NOTES_SMALL_BOX_WIDTH_RATIO = 0.18
"""Width ratio for small box detection."""

_QUALITY_NOTES_SMALL_BOX_HEIGHT_RATIO = 0.08
"""Height ratio for small box detection."""

_QUALITY_NOTES_SMALL_BOX_TEXT_LENGTH = 24
"""Text length threshold for small box detection."""

_QUALITY_NOTES_RIGHT_BOX_CENTER_RATIO = 0.58
"""Center X ratio for right-positioned box detection."""

_QUALITY_NOTES_ITEM_COUNT_MIN = 4
"""Minimum item count for quality notes analysis."""

_QUALITY_NOTES_ITEM_COUNT_MAX = 18
"""Maximum item count for quality notes analysis."""

_QUALITY_NOTES_LARGE_BOX_COUNT_RATIO = 2
"""Subtraction from count for large box threshold."""

_QUALITY_NOTES_SMALL_BOX_MAX = 1
"""Maximum small boxes before suspicious."""

_QUALITY_NOTES_RIGHT_BOX_MAX = 1
"""Maximum right boxes before suspicious."""

# ---------------------------------------------------------------------------
# Constants: Line break assist (ink projection)
# ---------------------------------------------------------------------------
_LINEBREAK_MIN_WIDTH_PX = 6
"""Minimum width in pixels for ink projection analysis."""

_LINEBREAK_MIN_HEIGHT_PX = 10
"""Minimum height in pixels for ink projection analysis."""

_LINEBREAK_SMOOTHING_KERNEL_DIVISOR = 54.0
"""Divisor for calculating smoothing kernel size from height."""

_LINEBREAK_PERCENTILE_THRESHOLD = 70.0
"""Percentile for adaptive threshold calculation."""

_LINEBREAK_MIN_THRESHOLD = 0.055
"""Minimum threshold for ink detection."""

_LINEBREAK_MAX_THRESHOLD = 0.20
"""Maximum threshold for ink detection."""

_LINEBREAK_INK_MASK_THRESHOLD = 0.16
"""Threshold for ink mask binarization."""

_LINEBREAK_MIN_ROW_PROFILE_SUM_RATIO = 0.02
"""Minimum ratio of active rows to total height."""

_LINEBREAK_MIN_SEGMENT_HEIGHT_RATIO = 0.25
"""Minimum segment height as ratio of typical line height."""

_LINEBREAK_MERGE_GAP_RATIO = 0.22
"""Gap ratio for merging nearby segments."""

_LINEBREAK_MAX_LINES = 8
"""Maximum number of lines for heuristic splitting."""

_LINEBREAK_TYPICAL_HEIGHT_QUANTILE = 0.35
"""Quantile for typical height estimation."""

_LINEBREAK_MIN_CANDIDATES_RATIO = 0.18
"""Minimum ratio of candidates to total items for auto mode."""

_LINEBREAK_LINE_LENGTH_TOLERANCE = 1.12
"""Tolerance factor for line length when splitting."""

_LINEBREAK_BREAKPOINT_TOLERANCE_RATIO = 0.45
"""Ratio of target for breakpoint tolerance."""

_LINEBREAK_INK_PROJECTION_CONTRAST_MIN = 8.0
"""Minimum contrast for ink projection to be valid."""

# ---------------------------------------------------------------------------
# Constants: Contextual noise filtering
# ---------------------------------------------------------------------------
_CONTEXTUAL_NOISE_CJK_DOMINANT_RATIO = 0.32
"""CJK character ratio to consider page CJK-dominant."""

_CONTEXTUAL_NOISE_SHORT_LATIN_AREA_RATIO = 0.012
"""Area ratio threshold for short Latin token noise."""

_CONTEXTUAL_NOISE_LOWERCASE_AREA_RATIO = 0.015
"""Area ratio threshold for lowercase short word noise."""

_CONTEXTUAL_NOISE_LONG_LATIN_AREA_RATIO = 0.0035
"""Area ratio threshold for long Latin word noise."""

_CONTEXTUAL_NOISE_MIXED_ALPHA_DIGIT_AREA_RATIO = 0.0040
"""Area ratio threshold for mixed alpha+digit noise."""

_CONTEXTUAL_NOISE_TINY_NUMERIC_AREA_RATIO = 0.0015
"""Area ratio threshold for tiny numeric noise."""

_CONTEXTUAL_NOISE_LOW_CONFIDENCE_THRESHOLD = 0.45
"""Confidence threshold for low-confidence noise filtering."""

_CONTEXTUAL_NOISE_LOW_CONFIDENCE_AREA_RATIO = 0.02
"""Area ratio threshold for low-confidence noise."""

_CONTEXTUAL_NOISE_SINGLE_LETTER_AREA_RATIO = 0.002
"""Area ratio threshold for single-letter noise."""

_CONTEXTUAL_NOISE_SINGLE_LETTER_HEIGHT_RATIO = 0.08
"""Height ratio threshold for single-letter noise."""

_CONTEXTUAL_NOISE_ACRONYM_AREA_RATIO = 0.00035
"""Area ratio threshold for acronym tokens."""

_CONTEXTUAL_NOISE_NON_ACRONYM_AREA_RATIO = 0.00070
"""Area ratio threshold for non-acronym tokens."""

_CONTEXTUAL_NOISE_TWO_LETTER_HEIGHT_RATIO = 0.10
"""Height ratio threshold for two-letter tokens."""

_CONTEXTUAL_NOISE_TWO_LETTER_NON_UPPER_AREA_RATIO = 0.0012
"""Area ratio threshold for two-letter non-uppercase tokens."""

_CONTEXTUAL_NOISE_THREE_FOUR_UPPER_AREA_RATIO = 0.0009
"""Area ratio threshold for 3-4 character uppercase tokens."""

_CONTEXTUAL_NOISE_THREE_FOUR_UPPER_HEIGHT_RATIO = 0.11
"""Height ratio threshold for 3-4 character uppercase tokens."""

_CONTEXTUAL_NOISE_REPETITIVE_MAX_FREQ_OFFSET = 1
"""Offset from string length for repetitive character detection."""

_CONTEXTUAL_NOISE_SHORT_ALPHA_MAX_LENGTH = 4
"""Maximum length for short alpha token noise detection."""

_CONTEXTUAL_NOISE_LOWERCASE_MAX_LENGTH = 6
"""Maximum length for lowercase word noise detection."""

_CONTEXTUAL_NOISE_LONG_LATIN_MIN_LENGTH = 7
"""Minimum length for long Latin word detection."""

_CONTEXTUAL_NOISE_LONG_LATIN_ALPHA_MAX_LENGTH = 4
"""Maximum alpha length for mixed CJK+Latin noise."""

_CONTEXTUAL_NOISE_MIXED_ALPHA_DIGIT_MAX_LENGTH = 14
"""Maximum length for mixed alpha+digit noise."""

_CONTEXTUAL_NOISE_TINY_NUMERIC_MAX_LENGTH = 5
"""Maximum length for tiny numeric noise."""

_CONTEXTUAL_NOISE_LOW_CONFIDENCE_MAX_LENGTH = 8
"""Maximum length for low-confidence noise."""

# ---------------------------------------------------------------------------
# Constants: Merge line items (prefer primary)
# ---------------------------------------------------------------------------
_MERGE_LINE_ITEMS_IOU_THRESHOLD = 0.45
"""IoU threshold for matching secondary items to primary."""

_MERGE_LINE_ITEMS_PRIMARY_HEIGHT_MULTIPLIER = 2.2
"""Multiplier for primary line height reasonableness check."""

_MERGE_LINE_ITEMS_PRIMARY_WIDTH_RATIO = 0.98
"""Width ratio for primary line reasonableness check."""

_MERGE_LINE_ITEMS_SECONDARY_HEIGHT_MULTIPLIER = 2.6
"""Multiplier for secondary line height reasonableness check."""

_MERGE_LINE_ITEMS_CENTER_MATCH_TOLERANCE = 2.0
"""Pixel tolerance for center-in-box matching."""

_MERGE_LINE_ITEMS_OVERLAP_THRESHOLD = 0.85
"""Overlap ratio threshold relative to smaller box area."""

# ---------------------------------------------------------------------------
# Constants: Word-level merge detection
# ---------------------------------------------------------------------------
_WORD_MERGE_AI_OCR_MIN_ITEMS = 140
"""Minimum item count for AI OCR word-level merge detection."""

_WORD_MERGE_AI_OCR_WIDTH_RATIO = 0.18
"""Width ratio threshold for AI OCR word-level detection."""

_WORD_MERGE_AI_OCR_HEIGHT_MULTIPLIER = 2.9
"""Height multiplier for AI OCR word-level detection."""

_WORD_MERGE_PADDLE_MIN_ITEMS = 80
"""Minimum item count for PaddleOCR word-level merge detection."""

_WORD_MERGE_PADDLE_WIDTH_RATIO = 0.22
"""Width ratio threshold for PaddleOCR word-level detection."""

_WORD_MERGE_PADDLE_HEIGHT_MULTIPLIER = 3.2
"""Height multiplier for PaddleOCR word-level detection."""

# ---------------------------------------------------------------------------
# Constants: AI supplement pruning (hybrid mode)
# ---------------------------------------------------------------------------
_AI_SUPPLEMENT_HEIGHT_MULTIPLIER = 3.0
"""Multiplier for baseline height in coarse paragraph detection."""

_AI_SUPPLEMENT_HEIGHT_RATIO = 0.14
"""Height ratio of image for coarse paragraph detection."""

_AI_SUPPLEMENT_WIDTH_RATIO = 0.20
"""Width ratio of image for coarse paragraph detection."""

_AI_SUPPLEMENT_TEXT_LENGTH = 8
"""Text length threshold for coarse paragraph detection."""

_AI_SUPPLEMENT_WIDE_WIDTH_RATIO = 0.90
"""Width ratio for wide paragraph detection."""

_AI_SUPPLEMENT_WIDE_HEIGHT_MULTIPLIER = 1.8
"""Multiplier for baseline height in wide paragraph detection."""

_AI_SUPPLEMENT_WIDE_HEIGHT_RATIO = 0.08
"""Height ratio of image for wide paragraph detection."""

_AI_SUPPLEMENT_FALLBACK_HEIGHT_RATIO = 0.16
"""Height ratio for fallback paragraph detection."""

_AI_SUPPLEMENT_FALLBACK_WIDTH_RATIO = 0.20
"""Width ratio for fallback paragraph detection."""

from .ai_client import (
    AiOcrClient,
    AiOcrTextRefiner,
    _clone_image_region_payload,
    _is_multiline_candidate_for_linebreak_assist,
)
from .base import (
    _ACRONYM_ALLOWLIST,
    _DEFAULT_PADDLE_OCR_VL_MODEL,
    _clean_str,
    _normalize_paddle_language,
    _normalize_tesseract_language,
    _split_tesseract_languages,
    OcrProvider,
)
from .routing import (
    ROUTE_KIND_HYBRID_AUTO,
    ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR,
    ROUTE_KIND_REMOTE_DOC_PARSER,
    ROUTE_KIND_REMOTE_PROMPT_OCR,
    normalize_ocr_route_kind,
)
from .runtime_probe import (
    probe_local_paddle_models,
    probe_local_paddleocr,
    probe_local_tesseract,
    probe_local_tesseract_models,
)
from .utils import _coerce_bbox_xyxy, _is_paddleocr_vl_model
from .vendors import _normalize_ai_ocr_provider
from .deepseek_parser import _looks_like_ocr_prompt_echo_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteOcrClientSpec:
    requested_provider: str
    route_kind: str
    ai_provider: str | None
    ai_model: str | None


def resolve_remote_ocr_client_spec(
    *,
    provider_id: str,
    ai_provider: str | None,
    ai_base_url: str | None,
    ai_model: str | None,
    route_kind: str | None,
) -> RemoteOcrClientSpec:
    normalized_route_kind = normalize_ocr_route_kind(route_kind)
    resolved_model = _clean_str(ai_model) or None

    if provider_id == "paddle":
        resolved_model = resolved_model or _DEFAULT_PADDLE_OCR_VL_MODEL
        if not _is_paddleocr_vl_model(resolved_model):
            raise ValueError(
                "Paddle OCR provider requires a PaddleOCR-VL model (for example PaddlePaddle/PaddleOCR-VL or PaddlePaddle/PaddleOCR-VL-1.5)"
            )
        normalized_route_kind = ROUTE_KIND_REMOTE_DOC_PARSER
    elif provider_id == "aiocr":
        if normalized_route_kind not in {
            ROUTE_KIND_REMOTE_PROMPT_OCR,
            ROUTE_KIND_REMOTE_DOC_PARSER,
            ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR,
        }:
            normalized_route_kind = (
                ROUTE_KIND_REMOTE_DOC_PARSER
                if _is_paddleocr_vl_model(resolved_model)
                else ROUTE_KIND_REMOTE_PROMPT_OCR
            )
    else:
        raise ValueError(f"Unsupported remote OCR provider: {provider_id}")

    resolved_ai_provider = ai_provider
    if _is_paddleocr_vl_model(resolved_model):
        normalized_vendor = _normalize_ai_ocr_provider(ai_provider)
        if normalized_vendor == "auto" and not _clean_str(ai_base_url):
            resolved_ai_provider = "siliconflow"

    return RemoteOcrClientSpec(
        requested_provider=provider_id,
        route_kind=normalized_route_kind,
        ai_provider=resolved_ai_provider,
        ai_model=resolved_model,
    )


def create_remote_ocr_client(
    *,
    requested_provider: str,
    route_kind: str | None = None,
    ai_provider: str | None = None,
    ai_api_key: str,
    ai_base_url: str | None = None,
    ai_model: str | None = None,
    ai_layout_model: str | None = None,
    paddle_doc_max_side_px: int | None = None,
    layout_block_max_concurrency: int | None = None,
    request_rpm_limit: int | None = None,
    request_tpm_limit: int | None = None,
    request_max_retries: int | None = None,
    prompt_preset: str | None = None,
    direct_prompt_override: str | None = None,
    layout_block_prompt_override: str | None = None,
    image_region_prompt_override: str | None = None,
    allow_paddle_model_downgrade: bool = False,
) -> AiOcrClient:
    spec = resolve_remote_ocr_client_spec(
        provider_id=requested_provider,
        ai_provider=ai_provider,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        route_kind=route_kind,
    )
    return _build_remote_ocr_client_from_spec(
        spec=spec,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_layout_model=ai_layout_model,
        paddle_doc_max_side_px=paddle_doc_max_side_px,
        layout_block_max_concurrency=layout_block_max_concurrency,
        request_rpm_limit=request_rpm_limit,
        request_tpm_limit=request_tpm_limit,
        request_max_retries=request_max_retries,
        prompt_preset=prompt_preset,
        direct_prompt_override=direct_prompt_override,
        layout_block_prompt_override=layout_block_prompt_override,
        image_region_prompt_override=image_region_prompt_override,
        allow_paddle_model_downgrade=allow_paddle_model_downgrade,
    )


def _build_remote_ocr_client_from_spec(
    *,
    spec: RemoteOcrClientSpec,
    ai_api_key: str,
    ai_base_url: str | None,
    ai_layout_model: str | None,
    paddle_doc_max_side_px: int | None,
    layout_block_max_concurrency: int | None,
    request_rpm_limit: int | None,
    request_tpm_limit: int | None,
    request_max_retries: int | None,
    prompt_preset: str | None,
    direct_prompt_override: str | None,
    layout_block_prompt_override: str | None,
    image_region_prompt_override: str | None,
    allow_paddle_model_downgrade: bool,
) -> AiOcrClient:
    client = AiOcrClient(
        api_key=ai_api_key,
        base_url=ai_base_url,
        model=spec.ai_model,
        provider=spec.ai_provider,
        layout_model=ai_layout_model,
        paddle_doc_max_side_px=paddle_doc_max_side_px,
        layout_block_max_concurrency=layout_block_max_concurrency,
        request_rpm_limit=request_rpm_limit,
        request_tpm_limit=request_tpm_limit,
        request_max_retries=request_max_retries,
        route_kind=spec.route_kind,
        prompt_preset=prompt_preset,
        direct_prompt_override=direct_prompt_override,
        layout_block_prompt_override=layout_block_prompt_override,
        image_region_prompt_override=image_region_prompt_override,
    )
    client.allow_model_downgrade = bool(allow_paddle_model_downgrade)
    return client


_resolve_remote_ocr_client_spec = resolve_remote_ocr_client_spec
_build_remote_ocr_client = create_remote_ocr_client


