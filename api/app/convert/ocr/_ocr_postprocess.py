"""OCR post-processing: line merging, deduplication, noise filtering, color sampling."""

import math
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

if TYPE_CHECKING:
    from ..rendered_page import RenderedPage

import numpy as np
from PIL import Image

from .ai_client import AiOcrTextRefiner, _clone_image_region_payload, _is_multiline_candidate_for_linebreak_assist
from .base import _ACRONYM_ALLOWLIST, _clean_str
from .deepseek_parser import _looks_like_ocr_prompt_echo_text
from ._ocr_constants import (
    _BAND_CLOSE_Y_THRESHOLD_MULTIPLIER,
    _BAND_OVERLAP_THRESHOLD_MULTIPLIER,
    _BAND_X_GAP_THRESHOLD_HEIGHT_MULTIPLIER,
    _BAND_X_GAP_THRESHOLD_RATIO,
    _MERGE_GAP_THRESHOLD_MULTIPLIER,
    _MERGE_GAP_THRESHOLD_RATIO,
    _MERGE_Y_THRESHOLD_MULTIPLIER,
    _MERGE_Y_THRESHOLD_RATIO,
)
from .utils import _coerce_bbox_xyxy, _contains_cjk, _is_cjk_char

# Import TYPE_CHECKING to avoid circular import at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ._ocr_manager import OcrManager

# ---------------------------------------------------------------------------
# Constants: Noise detection
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
# Constants: Coarse AI paragraph pruning
# ---------------------------------------------------------------------------
_COARSE_AI_PRUNE_WIDTH_RATIO = 0.90
"""Width ratio threshold for pruning coarse AI paragraph boxes."""

_COARSE_AI_PRUNE_HEIGHT_RATIO = 0.16
"""Height ratio threshold for pruning coarse AI paragraph boxes."""

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Constants: Overlap merge threshold
# ---------------------------------------------------------------------------
_OVERLAP_MERGE_THRESHOLD = 0.90
"""Overlap ratio threshold for merging overlapping boxes."""


# ---------------------------------------------------------------------------
# Constants: OCR item deduplication
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

# ---------------------------------------------------------------------------
# Constants: AI supplement pruning (hybrid mode)
# ---------------------------------------------------------------------------
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

import logging

logger = logging.getLogger(__name__)

def _clamp_int(value: float, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _sample_text_color(image: Image.Image, bbox: List[float]) -> str:
    width, height = image.size
    if width <= 0 or height <= 0:
        return "#000000"

    x0, y0, x1, y1 = bbox
    x0 = _clamp_int(x0, 0, width - 1)
    y0 = _clamp_int(y0, 0, height - 1)
    x1 = _clamp_int(x1, 0, width - 1)
    y1 = _clamp_int(y1, 0, height - 1)
    if x1 <= x0 or y1 <= y0:
        return "#000000"

    def _pixel_rgb(px: int, py: int) -> tuple[int, int, int]:
        raw = image.getpixel((px, py))  # type: ignore[misc]
        if isinstance(raw, int):
            v = int(raw)
            return (v, v, v)
        if isinstance(raw, tuple):
            if len(raw) >= 3:
                return (int(raw[0]), int(raw[1]), int(raw[2]))
            if len(raw) == 1:
                v = int(raw[0])
                return (v, v, v)
        return (0, 0, 0)

    def _median_rgb(values: list[tuple[int, int, int]]) -> tuple[int, int, int]:
        if not values:
            return (0, 0, 0)
        rs = sorted(v[0] for v in values)
        gs = sorted(v[1] for v in values)
        bs = sorted(v[2] for v in values)
        mid = len(values) // 2
        return (int(rs[mid]), int(gs[mid]), int(bs[mid]))

    def _luma(rgb: tuple[int, int, int]) -> float:
        return _LUMA_COEFF_RED * float(rgb[0]) + _LUMA_COEFF_GREEN * float(rgb[1]) + _LUMA_COEFF_BLUE * float(rgb[2])

    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    box_w = max(1, int(x1 - x0))
    box_h = max(1, int(y1 - y0))

    # Estimate local background from samples just *outside* the bbox.
    pad = max(_COLOR_SAMPLE_BG_PAD_MIN, min(_COLOR_SAMPLE_BG_PAD_MAX, int(round(max(box_w, box_h) * _COLOR_SAMPLE_BG_PAD_RATIO))))
    bg_points = [
        (x0 - pad, y0 - pad),
        (x1 + pad, y0 - pad),
        (x0 - pad, y1 + pad),
        (x1 + pad, y1 + pad),
        (x0 - pad, cy),
        (x1 + pad, cy),
        (cx, y0 - pad),
        (cx, y1 + pad),
    ]
    bg_samples: list[tuple[int, int, int]] = []
    for px, py in bg_points:
        px = _clamp_int(px, 0, width - 1)
        py = _clamp_int(py, 0, height - 1)
        bg_samples.append(_pixel_rgb(px, py))

    if not bg_samples:
        bg_rgb = (255, 255, 255)
    else:
        bg_rgb = _median_rgb(bg_samples)

    br, bg, bb = float(bg_rgb[0]), float(bg_rgb[1]), float(bg_rgb[2])
    bg_luma = _luma(bg_rgb)

    # Densely scan the bbox and keep only pixels that behave like foreground ink
    # against the local background. This is much more robust than a sparse inner
    # grid for large paragraph boxes with thin multi-line glyph strokes.
    area = float(max(1, box_w * box_h))
    step = max(1, min(6, int(round(math.sqrt(area / _COLOR_SAMPLE_STEP_DIVISOR)))))

    candidates: list[
        tuple[float, float, float, tuple[int, int, int], bool]
    ] = []  # (contrast, dist, luma, rgb, preferred_direction)
    for py in range(y0, y1 + 1, step):
        for px in range(x0, x1 + 1, step):
            rgb = _pixel_rgb(px, py)
            luma = _luma(rgb)
            contrast = abs(luma - bg_luma)
            dist = (
                (float(rgb[0]) - br) ** 2
                + (float(rgb[1]) - bg) ** 2
                + (float(rgb[2]) - bb) ** 2
            )
            preferred_direction = (
                (luma <= (bg_luma - _COLOR_SAMPLE_FOREGROUND_CONTRAST_THRESHOLD))
                if bg_luma >= _COLOR_SAMPLE_BG_LUMA_MIDPOINT
                else (luma >= (bg_luma + _COLOR_SAMPLE_FOREGROUND_CONTRAST_THRESHOLD))
            )
            candidates.append((contrast, dist, luma, rgb, preferred_direction))

    if not candidates:
        return "#000000"

    preferred = [c for c in candidates if c[4] and c[0] >= _COLOR_SAMPLE_PREFERRED_CONTRAST_THRESHOLD]
    if len(preferred) < _COLOR_SAMPLE_KEEP_COUNT_MAX // _COLOR_SAMPLE_KEEP_COUNT_DIVISOR:
        preferred = [c for c in candidates if c[0] >= _COLOR_SAMPLE_FALLBACK_CONTRAST_THRESHOLD]
    if len(preferred) < _COLOR_SAMPLE_KEEP_COUNT_MAX // _COLOR_SAMPLE_KEEP_COUNT_DIVISOR // 2:
        preferred = [c for c in candidates if c[4] and c[1] >= _COLOR_SAMPLE_DISTANCE_THRESHOLD]
    if len(preferred) < _COLOR_SAMPLE_KEEP_COUNT_MAX // _COLOR_SAMPLE_KEEP_COUNT_DIVISOR // 3:
        preferred = sorted(candidates, key=lambda t: (t[0], t[1]), reverse=True)[:_COLOR_SAMPLE_TOP_CANDIDATE_COUNT]

    preferred.sort(key=lambda t: (t[0], t[1]), reverse=True)
    keep_n = len(preferred)
    if keep_n >= _COLOR_SAMPLE_TOP_CANDIDATE_COUNT:
        keep_n = max(_COLOR_SAMPLE_KEEP_COUNT_MIN, min(_COLOR_SAMPLE_KEEP_COUNT_MAX, keep_n // _COLOR_SAMPLE_KEEP_COUNT_DIVISOR))
    top = preferred[:keep_n]

    if bg_luma >= _COLOR_SAMPLE_BG_LUMA_MIDPOINT:
        darker = [c for c in top if c[2] <= (bg_luma - _COLOR_SAMPLE_DARKER_THRESHOLD)]
        if darker:
            top = darker
        top.sort(key=lambda t: t[2])
    else:
        lighter = [c for c in top if c[2] >= (bg_luma + _COLOR_SAMPLE_LIGHTER_THRESHOLD)]
        if lighter:
            top = lighter
        top.sort(key=lambda t: t[2], reverse=True)

    chosen_rgbs = [c[3] for c in top[:_COLOR_SAMPLE_MAX_CHOSEN_RGBS]] or [candidates[0][3]]
    rgb = _median_rgb(chosen_rgbs)
    if abs(_luma(rgb) - bg_luma) < _COLOR_SAMPLE_MIN_LUMA_CONTRAST:
        rgb = (_COLOR_SAMPLE_FALLBACK_DARK_TEXT, _COLOR_SAMPLE_FALLBACK_DARK_TEXT, _COLOR_SAMPLE_FALLBACK_DARK_TEXT) if bg_luma >= _COLOR_SAMPLE_BG_LUMA_MIDPOINT else (_COLOR_SAMPLE_FALLBACK_LIGHT_TEXT, _COLOR_SAMPLE_FALLBACK_LIGHT_TEXT, _COLOR_SAMPLE_FALLBACK_LIGHT_TEXT)
    return _rgb_to_hex(rgb)


def _should_insert_space(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if _contains_cjk(prev) or _contains_cjk(nxt):
        return False
    # Insert spaces for Latin words/numbers where OCR gives tokens without spaces.
    return prev[-1].isalnum() and nxt[0].isalnum()


from .result_parsing import _normalize_bbox_px


def _merge_ocr_items_to_lines(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
    allow_merge: bool = True,
) -> list[dict]:
    """Merge word-level OCR items into line-level items.

    Many OCR engines return per-word boxes which creates thousands of PPT shapes.
    Merging improves editability and fidelity when masking over a background render.
    """

    if not items:
        return []

    # If items contain Tesseract's structural fields, merge by (block, paragraph,
    # line) first. This is significantly more stable than purely geometric
    # clustering for multi-column pages and tables.
    if any(
        isinstance(it, dict)
        and it.get("line_num") is not None
        and it.get("block_num") is not None
        for it in items
    ):
        words: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            text = str(it.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if not text or bbox_n is None:
                continue
            try:
                block_num = int(it.get("block_num") or 0)
                par_num = int(it.get("par_num") or 0)
                line_num = int(it.get("line_num") or 0)
                word_num = int(it.get("word_num") or 0)
            except Exception:
                continue

            x0, y0, x1, y1 = bbox_n
            if x1 <= x0 or y1 <= y0:
                continue
            # Clamp.
            x0 = max(0.0, min(x0, float(image_width - 1)))
            x1 = max(0.0, min(x1, float(image_width)))
            y0 = max(0.0, min(y0, float(image_height - 1)))
            y1 = max(0.0, min(y1, float(image_height)))
            if x1 <= x0 or y1 <= y0:
                continue

            words.append(
                {
                    "text": text,
                    "bbox": [x0, y0, x1, y1],
                    "confidence": float(it.get("confidence") or 0.0),
                    "block_num": block_num,
                    "par_num": par_num,
                    "line_num": line_num,
                    "word_num": word_num,
                }
            )

        if words:
            heights = sorted(max(1.0, it["bbox"][3] - it["bbox"][1]) for it in words)
            median_h = heights[len(heights) // 2] if heights else 10.0
            median_h = max(4.0, float(median_h))
            # Split "line" groups when a large horizontal gap is present.
            #
            # Tesseract can sometimes assign the same (block,par,line) to text
            # tokens that are on the same Y baseline but belong to different
            # visual regions (e.g. paragraph text + a nearby diagram label).
            # Using a slightly stricter gap threshold reduces these accidental
            # cross-region merges while keeping normal word spacing intact.
            gap_thresh = max(_MERGE_GAP_THRESHOLD_MULTIPLIER * median_h, _MERGE_GAP_THRESHOLD_RATIO * float(image_width))

            groups: dict[tuple[int, int, int], list[dict]] = {}
            for w in words:
                key = (int(w["block_num"]), int(w["par_num"]), int(w["line_num"]))
                groups.setdefault(key, []).append(w)

            merged: list[dict] = []
            for group in groups.values():
                # Tesseract occasionally assigns the same (block,par,line) to
                # tokens from multiple visual lines (especially in dense
                # paragraphs on scanned slides). Before splitting by horizontal
                # gaps, we split by Y-center to avoid merging multiple lines
                # into a single tall paragraph-like box.
                def _y_center_word(it: dict) -> float:
                    y0, y1 = float(it["bbox"][1]), float(it["bbox"][3])
                    return (y0 + y1) / 2.0

                y_thresh = max(_MERGE_Y_THRESHOLD_MULTIPLIER * float(median_h), _MERGE_Y_THRESHOLD_RATIO * float(image_height))

                by_y = sorted(
                    group, key=lambda it: (_y_center_word(it), float(it["bbox"][0]))
                )
                sublines: list[list[dict]] = []
                current: list[dict] = []
                current_y: float | None = None
                for it in by_y:
                    yc = _y_center_word(it)
                    if not current:
                        current = [it]
                        current_y = yc
                        continue
                    assert current_y is not None
                    if abs(float(yc) - float(current_y)) > y_thresh:
                        sublines.append(current)
                        current = [it]
                        current_y = yc
                    else:
                        n = len(current)
                        current.append(it)
                        current_y = (float(current_y) * float(n) + float(yc)) / float(
                            n + 1
                        )
                if current:
                    sublines.append(current)

                for line_words in sublines:
                    group_sorted = sorted(
                        line_words,
                        key=lambda it: (
                            int(it.get("word_num") or 0),
                            float(it["bbox"][0]),
                        ),
                    )

                    segment: list[dict] = []
                    prev = None
                    for it in group_sorted:
                        if not segment:
                            segment = [it]
                            prev = it
                            continue
                        assert prev is not None
                        gap = float(it["bbox"][0]) - float(prev["bbox"][2])
                        if gap > gap_thresh:
                            merged.append(_merge_segment(segment))
                            segment = [it]
                        else:
                            segment.append(it)
                        prev = it
                    if segment:
                        merged.append(_merge_segment(segment))

            merged.sort(
                key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0])
            )
            out: list[dict] = []
            for m in merged:
                if not isinstance(m, dict):
                    continue
                text = str(m.get("text") or "").strip()
                bbox_n = _normalize_bbox_px(m.get("bbox"))
                if not text or bbox_n is None:
                    continue
                if _is_probably_noise_line(
                    text,
                    bbox_n,
                    image_width=int(image_width),
                    image_height=int(image_height),
                ):
                    continue
                out.append(m)
            return out

    normalized: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        # Clamp.
        x0 = max(0.0, min(x0, float(image_width - 1)))
        x1 = max(0.0, min(x1, float(image_width - 1)))
        y0 = max(0.0, min(y0, float(image_height - 1)))
        y1 = max(0.0, min(y1, float(image_height - 1)))
        if x1 <= x0 or y1 <= y0:
            continue
        normalized.append(
            {
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "confidence": float(it.get("confidence") or 0.0),
            }
        )

    if not normalized:
        return []

    if not allow_merge:
        normalized.sort(
            key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0])
        )
        out_no_merge: list[dict] = []
        for it in normalized:
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if bbox_n is None:
                continue
            text_value = str(it.get("text") or "").strip()
            if not text_value:
                continue
            if _is_probably_noise_line(
                text_value,
                bbox_n,
                image_width=int(image_width),
                image_height=int(image_height),
            ):
                continue
            out_no_merge.append({**it, "bbox": list(bbox_n), "text": text_value})
        return out_no_merge

    heights = sorted(max(1.0, it["bbox"][3] - it["bbox"][1]) for it in normalized)
    median_h = heights[len(heights) // 2] if heights else 10.0
    median_h = max(4.0, float(median_h))

    def y_center(it: dict) -> float:
        y0, y1 = it["bbox"][1], it["bbox"][3]
        return (y0 + y1) / 2.0

    normalized.sort(key=lambda it: (y_center(it), it["bbox"][0]))

    # Band clustering by vertical proximity/overlap.
    #
    # IMPORTANT: scanned slides often have multiple "cards" (left/right columns)
    # whose text lines share similar Y ranges. Purely Y-based banding can merge
    # unrelated items across columns; a tall bbox on the right column can then
    # expand the band's Y range and accidentally merge multiple rows from the
    # left column (we observed this with Baidu OCR tokens in small tables).
    #
    # To keep line merging stable, we also gate band membership by horizontal
    # proximity (x-gap threshold).
    bands: list[list[dict]] = []
    band_stats: list[
        dict[str, float]
    ] = []  # min_y0, max_y1, min_x0, max_x1, center_y, n
    for it in normalized:
        x0, y0, x1, y1 = it["bbox"]
        yc = y_center(it)
        if not bands:
            bands.append([it])
            band_stats.append(
                {
                    "min_y0": float(y0),
                    "max_y1": float(y1),
                    "min_x0": float(x0),
                    "max_x1": float(x1),
                    "center_y": float(yc),
                    "n": 1.0,
                }
            )
            continue

        st = band_stats[-1]
        min_y0 = float(st.get("min_y0", 0.0))
        max_y1 = float(st.get("max_y1", 0.0))
        min_x0 = float(st.get("min_x0", 0.0))
        max_x1 = float(st.get("max_x1", 0.0))
        center_y = float(st.get("center_y", (min_y0 + max_y1) / 2.0))

        overlap = min(y1, max_y1) - max(y0, min_y0)
        band_h = max(1.0, max_y1 - min_y0)
        it_h = max(1.0, y1 - y0)

        # Horizontal gap between this item and the band's x-range.
        if x1 < min_x0:
            x_gap = float(min_x0 - x1)
        elif x0 > max_x1:
            x_gap = float(x0 - max_x1)
        else:
            x_gap = 0.0

        # Allow modest gaps for table columns (e.g. "label 70%"), but prevent
        # merging across distinct slide columns/cards.
        x_gap_thresh = max(_BAND_X_GAP_THRESHOLD_RATIO * float(image_width), _BAND_X_GAP_THRESHOLD_HEIGHT_MULTIPLIER * float(median_h))

        close = abs(float(yc) - center_y) <= _BAND_CLOSE_Y_THRESHOLD_MULTIPLIER * float(median_h)
        same_line = (x_gap <= x_gap_thresh) and (
            close or (overlap >= _BAND_OVERLAP_THRESHOLD_MULTIPLIER * min(band_h, it_h))
        )
        if same_line:
            bands[-1].append(it)
            st["min_y0"] = float(min(min_y0, y0))
            st["max_y1"] = float(max(max_y1, y1))
            st["min_x0"] = float(min(min_x0, x0))
            st["max_x1"] = float(max(max_x1, x1))
            n = int(float(st.get("n", 1.0) or 1.0))
            st["n"] = float(n + 1)
            st["center_y"] = float((center_y * n + float(yc)) / float(n + 1))
        else:
            bands.append([it])
            band_stats.append(
                {
                    "min_y0": float(y0),
                    "max_y1": float(y1),
                    "min_x0": float(x0),
                    "max_x1": float(x1),
                    "center_y": float(yc),
                    "n": 1.0,
                }
            )

    # Within each band, split by large horizontal gaps (multi-column / table cells).
    merged: list[dict] = []
    # Split segments on gaps that likely indicate a separate column/region.
    gap_thresh = max(_MERGE_GAP_THRESHOLD_MULTIPLIER * median_h, _MERGE_GAP_THRESHOLD_RATIO * float(image_width))

    for band in bands:
        band_sorted = sorted(band, key=lambda it: it["bbox"][0])
        segment: list[dict] = []
        prev = None
        for it in band_sorted:
            if not segment:
                segment = [it]
                prev = it
                continue
            assert prev is not None
            gap = float(it["bbox"][0]) - float(prev["bbox"][2])
            if gap > gap_thresh:
                # Flush current segment.
                merged.append(_merge_segment(segment))
                segment = [it]
            else:
                segment.append(it)
            prev = it
        if segment:
            merged.append(_merge_segment(segment))

    # Filter empty merges.
    out: list[dict] = []
    for m in merged:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(m.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(
            text,
            bbox_n,
            image_width=int(image_width),
            image_height=int(image_height),
        ):
            continue
        out.append(m)
    return out


def _merge_segment(segment: list[dict]) -> dict:
    seg_sorted = sorted(segment, key=lambda it: it["bbox"][0])
    parts: list[str] = []
    prev_text = ""
    for it in seg_sorted:
        t = str(it.get("text") or "").strip()
        if not t:
            continue
        if parts and _should_insert_space(prev_text, t):
            parts.append(" ")
        parts.append(t)
        prev_text = t
    text = "".join(parts).strip()

    x0 = min(float(it["bbox"][0]) for it in seg_sorted)
    y0 = min(float(it["bbox"][1]) for it in seg_sorted)
    x1 = max(float(it["bbox"][2]) for it in seg_sorted)
    y1 = max(float(it["bbox"][3]) for it in seg_sorted)
    confs = [float(it.get("confidence") or 0.0) for it in seg_sorted]
    confidence = sum(confs) / len(confs) if confs else 0.0
    return {"text": text, "bbox": [x0, y0, x1, y1], "confidence": confidence}


def _normalize_ocr_items_as_lines(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Normalize OCR items that are already *line-level*.

    Some providers (notably Baidu's general/accurate OCR and many AI OCR
    prompts) output one item per visual line. Re-running the geometric merge
    step on such items can accidentally merge unrelated lines into huge boxes,
    which then causes over-masking and missing text in the generated PPT.
    """

    if not items:
        return []

    W = int(image_width)
    H = int(image_height)

    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _looks_like_ocr_prompt_echo_text(text):
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue

        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        # Clamp to image bounds.
        x0 = max(0.0, min(x0, float(W - 1)))
        x1 = max(0.0, min(x1, float(W)))
        y0 = max(0.0, min(y0, float(H - 1)))
        y1 = max(0.0, min(y1, float(H)))
        if x1 <= x0 or y1 <= y0:
            continue

        out.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})

    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _build_primary_ocr_quality_notes(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
    provider_name: str | None,
    model_name: str | None,
) -> list[str]:
    """Emit lightweight quality notes when OCR output looks suspiciously coarse."""

    if str(provider_name or "") != "AiOcrClient":
        return []
    lowered_model = str(model_name or "").strip().lower()
    if "paddleocr-vl" not in lowered_model:
        return []
    if not items:
        return []

    W = max(1, int(image_width))
    H = max(1, int(image_height))
    if float(W) < (_QUALITY_NOTES_LANDSCAPE_ASPECT_RATIO * float(H)):
        return []

    valid: list[tuple[tuple[float, float, float, float], str]] = []
    heights: list[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(item.get("bbox"))
        if not text or bbox_n is None:
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        compact = re.sub(r"\s+", "", text)
        valid.append((bbox_n, compact))
        heights.append(max(1.0, float(y1 - y0)))

    count = len(valid)
    if count < _QUALITY_NOTES_ITEM_COUNT_MIN or count > _QUALITY_NOTES_ITEM_COUNT_MAX:
        return []

    heights.sort()
    median_h = heights[len(heights) // 2] if heights else max(10.0, 0.02 * float(H))
    median_h = max(8.0, float(median_h))

    large_boxes = 0
    small_boxes = 0
    right_boxes = 0
    for bbox_n, compact in valid:
        x0, y0, x1, y1 = bbox_n
        w = max(1.0, float(x1 - x0))
        h = max(1.0, float(y1 - y0))
        cx = (float(x0) + float(x1)) / 2.0

        if h >= max(_QUALITY_NOTES_LARGE_BOX_HEIGHT_MULTIPLIER * median_h, _QUALITY_NOTES_LARGE_BOX_HEIGHT_RATIO * float(H)) or (
            w >= _QUALITY_NOTES_LARGE_BOX_WIDTH_RATIO * float(W) and len(compact) >= _QUALITY_NOTES_LARGE_BOX_TEXT_LENGTH
        ):
            large_boxes += 1
        if w <= _QUALITY_NOTES_SMALL_BOX_WIDTH_RATIO * float(W) and h <= _QUALITY_NOTES_SMALL_BOX_HEIGHT_RATIO * float(H) and len(compact) <= _QUALITY_NOTES_SMALL_BOX_TEXT_LENGTH:
            small_boxes += 1
        if cx >= _QUALITY_NOTES_RIGHT_BOX_CENTER_RATIO * float(W):
            right_boxes += 1

    if large_boxes >= max(_QUALITY_NOTES_ITEM_COUNT_MIN, count - _QUALITY_NOTES_LARGE_BOX_COUNT_RATIO) and small_boxes <= _QUALITY_NOTES_SMALL_BOX_MAX and right_boxes <= _QUALITY_NOTES_RIGHT_BOX_MAX:
        return [
            "paddle_vl_sparse_slide_layout:"
            f" items={count}"
            f" large_boxes={large_boxes}"
            f" small_boxes={small_boxes}"
            f" right_boxes={right_boxes}"
        ]
    return []


def _bbox_iou(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
    union = area_a + area_b - inter
    return float(inter) / float(max(1.0, union))


def _bbox_overlap_smaller(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
    return float(inter) / float(min(area_a, area_b))


def _normalize_text_for_dedupe(text: str) -> str:
    # Keep alnum/CJK, drop punctuation/whitespace for robust OCR text matching.
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())


def _texts_are_similar_for_dedupe(a: str, b: str) -> bool:
    na = _normalize_text_for_dedupe(a)
    nb = _normalize_text_for_dedupe(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        short = min(len(na), len(nb))
        long = max(len(na), len(nb))
        return short >= 3 and (float(short) / float(long)) >= _DEDUPE_TEXT_SIMILARITY_SHORT_RATIO
    return False


def _dedupe_overlapping_ocr_items(items: list[dict]) -> list[dict]:
    """Drop near-duplicate OCR items caused by multi-engine merge/refinement.

    For single-provider runs (for example pure AI OCR), we only remove exact-ish
    duplicates and keep potentially overlapping lines/paragraph splits. Aggressive
    overlap dedupe is used only for mixed-provider merges.
    """

    candidates: list[dict] = []
    providers_seen: set[str] = set()
    heights: list[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        conf = float(it.get("confidence") or 0.0)
        area = float((x1 - x0) * (y1 - y0))
        h = float(y1 - y0)
        heights.append(max(1.0, h))
        provider_name = (
            str(it.get("provider") or it.get("source") or "").strip().lower()
        )
        if provider_name:
            providers_seen.add(provider_name)
        candidates.append(
            {
                **it,
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "_bbox_t": (x0, y0, x1, y1),
                "_conf": conf,
                "_area": area,
                "_provider": provider_name,
                "_cx": float(x0 + x1) / 2.0,
                "_cy": float(y0 + y1) / 2.0,
                "_h": float(h),
            }
        )

    if len(candidates) <= 1:
        for it in candidates:
            it.pop("_bbox_t", None)
            it.pop("_conf", None)
            it.pop("_area", None)
            it.pop("_provider", None)
        return candidates

    # Prefer higher confidence, then smaller area (usually tighter line bbox).
    candidates.sort(key=lambda it: (-float(it["_conf"]), float(it["_area"])))

    multi_provider = len(providers_seen) >= 2
    heights.sort()
    median_h = float(heights[len(heights) // 2]) if heights else 10.0
    median_h = max(4.0, float(median_h))

    kept: list[dict] = []
    dropped = 0
    for cur in candidates:
        cur_bbox = cur["_bbox_t"]
        cur_text = str(cur.get("text") or "")
        cur_cx = float(cur.get("_cx") or 0.0)
        cur_cy = float(cur.get("_cy") or 0.0)
        duplicate = False
        for prev in kept:
            prev_bbox = prev["_bbox_t"]
            prev_cx = float(prev.get("_cx") or 0.0)
            prev_cy = float(prev.get("_cy") or 0.0)
            iou = _bbox_iou(cur_bbox, prev_bbox)
            overlap_small = _bbox_overlap_smaller(cur_bbox, prev_bbox)

            # Same-geometry duplicates can appear in malformed AI grounding output
            # (different text strings mapped to the exact same bbox). Keep only one.
            strong_same_bbox = overlap_small >= _DEDUPE_STRONG_SAME_BBOX_OVERLAP and iou >= _DEDUPE_STRONG_SAME_BBOX_IOU
            if strong_same_bbox:
                duplicate = True
                break

            # AI OCR (and some gateways) can also output near-identical boxes with
            # small jitter. Treat them as duplicates even if the text differs.
            near_same_bbox = overlap_small >= _DEDUPE_NEAR_SAME_BBOX_OVERLAP and iou >= _DEDUPE_NEAR_SAME_BBOX_IOU
            if near_same_bbox:
                duplicate = True
                break

            # Exact-ish duplicate candidate.
            exact_like = overlap_small >= _DEDUPE_EXACT_LIKE_OVERLAP and _texts_are_similar_for_dedupe(
                cur_text, str(prev.get("text") or "")
            )
            if exact_like:
                duplicate = True
                break

            # In single-provider runs we are intentionally conservative, but we
            # still want to suppress obvious "same text, slightly shifted bbox"
            # duplicates which otherwise show up as stacked/offset glyphs.
            if not multi_provider:
                if _texts_are_similar_for_dedupe(cur_text, str(prev.get("text") or "")):
                    if overlap_small >= _DEDUPE_SINGLE_PROVIDER_OVERLAP:
                        duplicate = True
                        break
                    # Some AI OCR engines (notably DeepSeek grounding outputs on
                    # gateways) can emit the same line twice with a slightly
                    # larger jitter (overlap ~0.70-0.85). Use a vertical-center
                    # guard to avoid deleting distinct nearby lines.
                    dy = abs(cur_cy - prev_cy)
                    if dy <= (_DEDUPE_SINGLE_PROVIDER_Y_THRESHOLD_MULTIPLIER * median_h) and (
                        overlap_small >= _DEDUPE_SINGLE_PROVIDER_OVERLAP_ALT or iou >= _DEDUPE_SINGLE_PROVIDER_IOU
                    ):
                        duplicate = True
                        break

            if multi_provider:
                # Only do aggressive overlap pruning for mixed-provider merges,
                # where stacked duplicate lines are common.
                if overlap_small >= _DEDUPE_MULTI_PROVIDER_OVERLAP or iou >= _DEDUPE_MULTI_PROVIDER_IOU:
                    duplicate = True
                    break
                if iou >= _DEDUPE_MULTI_PROVIDER_IOU_ALT and _texts_are_similar_for_dedupe(
                    cur_text, str(prev.get("text") or "")
                ):
                    duplicate = True
                    break

        if duplicate:
            dropped += 1
            continue
        kept.append(cur)

    if dropped > 0:
        logger.info("OCR dedupe dropped %s overlapping items", dropped)

    out: list[dict] = []
    for it in kept:
        cp = dict(it)
        cp.pop("_bbox_t", None)
        cp.pop("_conf", None)
        cp.pop("_area", None)
        cp.pop("_provider", None)
        cp.pop("_cx", None)
        cp.pop("_cy", None)
        cp.pop("_h", None)
        out.append(cp)

    # Stable reading order for downstream conversion.
    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _is_probably_noise_line(
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    t = str(text or "").strip()
    if not t:
        return True

    if _looks_like_ocr_prompt_echo_text(t):
        return True

    # Skip pure punctuation / dots (common false positives in scans).
    stripped = "".join(ch for ch in t if not ch.isspace())
    if stripped and all((not ch.isalnum()) for ch in stripped):
        return True
    if len(stripped) >= 6 and set(stripped) <= {"."}:
        return True

    cjk = _contains_cjk(t)
    has_digit = any(ch.isdigit() for ch in t)
    has_alpha = any(ch.isalpha() for ch in t)

    x0, y0, x1, y1 = bbox
    w = max(0.0, x1 - x0)
    h = max(0.0, y1 - y0)
    area = w * h
    img_area = float(max(1, int(image_width) * int(image_height)))

    # Common acronyms that can appear as standalone tokens in slide decks.
    # We keep these even when other heuristics would treat them as noise.
    # Short Latin-only tokens inside small/odd boxes are frequently garbage
    # (icons/logos or screenshot UI chrome). However, 2-letter ALLCAPS tokens
    # like "AI" / "EF" can be meaningful abbreviations in decks, so we keep them
    # unless they are extremely tiny.
    if (not cjk) and (not has_digit) and has_alpha:
        alpha_only = "".join(ch for ch in stripped if ch.isalpha())
        if alpha_only and alpha_only.upper() in _ACRONYM_ALLOWLIST:
            return False

        if len(stripped) == 1:
            # Single-letter hits are almost always noise on scanned slides.
            if area / img_area < _CONTEXTUAL_NOISE_SINGLE_LETTER_AREA_RATIO:
                return True
            if image_height > 0 and (h / float(image_height)) >= _CONTEXTUAL_NOISE_SINGLE_LETTER_HEIGHT_RATIO:
                return True
        elif len(stripped) == 2:
            if stripped.isupper():
                # Two-letter ALLCAPS tokens can be meaningful ("AI", "UI"), but
                # most random ones on scanned slides are icon false positives.
                # Keep a small allowlist and be stricter otherwise.
                min_area = (
                    _CONTEXTUAL_NOISE_ACRONYM_AREA_RATIO if stripped.upper() in _ACRONYM_ALLOWLIST else _CONTEXTUAL_NOISE_NON_ACRONYM_AREA_RATIO
                )
                if area / img_area < min_area:
                    return True
                if image_height > 0 and (h / float(image_height)) >= _CONTEXTUAL_NOISE_TWO_LETTER_HEIGHT_RATIO:
                    return True
            else:
                if area / img_area < _CONTEXTUAL_NOISE_TWO_LETTER_NON_UPPER_AREA_RATIO:
                    return True
                # If the bbox is *very* tall relative to the page but contains
                # only 1-2 Latin letters, it is almost certainly an icon false
                # positive.
                if image_height > 0 and (h / float(image_height)) >= _CONTEXTUAL_NOISE_SINGLE_LETTER_HEIGHT_RATIO:
                    return True
        elif stripped.isupper() and 3 <= len(stripped) <= 4:
            # 3-4 uppercase tokens are often noise ("FRM", "GFE") produced by
            # icons / diagram strokes. Keep only if the bbox is reasonably large.
            if area / img_area < _CONTEXTUAL_NOISE_THREE_FOUR_UPPER_AREA_RATIO:
                return True
            if image_height > 0 and (h / float(image_height)) >= _CONTEXTUAL_NOISE_THREE_FOUR_UPPER_HEIGHT_RATIO:
                return True

    return False


def _filter_contextual_noise_items(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Page-contextual OCR cleanup to reduce image-internal gibberish tokens.

    This is intentionally conservative and only applies stricter rules when the
    page is clearly CJK-dominant (common in scanned slides where icons/figures
    leak short Latin fragments like "T os", "RAN," etc.).
    """

    W = max(1, int(image_width))
    H = max(1, int(image_height))

    candidates: list[dict] = []
    cjk_chars = 0
    total_chars = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        candidates.append({**it, "text": text, "bbox": list(bbox_n)})
        for ch in text:
            if ch.isspace():
                continue
            total_chars += 1
            if _is_cjk_char(ch):
                cjk_chars += 1

    if not candidates:
        return []

    cjk_ratio = (float(cjk_chars) / float(total_chars)) if total_chars > 0 else 0.0
    cjk_dominant = cjk_ratio >= _CONTEXTUAL_NOISE_CJK_DOMINANT_RATIO

    out: list[dict] = []
    for it in candidates:
        text = str(it.get("text") or "").strip()
        bbox = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w = max(1.0, float(x1 - x0))
        h = max(1.0, float(y1 - y0))
        area_ratio = (w * h) / float(W * H)

        stripped = "".join(ch for ch in text if not ch.isspace())
        alpha_only = "".join(ch for ch in stripped if ch.isalpha())
        has_alpha = bool(alpha_only)
        has_digit = any(ch.isdigit() for ch in stripped)
        has_cjk = any(_is_cjk_char(ch) for ch in stripped)
        conf = float(it.get("confidence") or 0.0)

        drop = False

        if cjk_dominant:
            if has_alpha and not has_digit:
                up = alpha_only.upper()
                # Very short Latin tokens on CJK pages are usually icon/UI noise.
                if len(alpha_only) <= _CONTEXTUAL_NOISE_SHORT_ALPHA_MAX_LENGTH and up not in _ACRONYM_ALLOWLIST:
                    if area_ratio < _CONTEXTUAL_NOISE_SHORT_LATIN_AREA_RATIO:
                        drop = True
                # Lowercase short words are rarely meaningful in CJK titles/body.
                if len(alpha_only) <= _CONTEXTUAL_NOISE_LOWERCASE_MAX_LENGTH and alpha_only.islower() and area_ratio < _CONTEXTUAL_NOISE_LOWERCASE_AREA_RATIO:
                    drop = True
                # Long pure-Latin words on CJK-dominant pages are commonly
                # labels from embedded screenshots/diagrams (e.g. "Probability").
                # Keep larger heading-like words, drop tiny ones.
                if (not has_cjk) and len(alpha_only) >= _CONTEXTUAL_NOISE_LONG_LATIN_MIN_LENGTH and area_ratio < _CONTEXTUAL_NOISE_LONG_LATIN_AREA_RATIO:
                    drop = True
                # Mixed short CJK+Latin fragments like "它crt".
                if has_cjk and len(stripped) <= 7 and len(alpha_only) <= _CONTEXTUAL_NOISE_LONG_LATIN_ALPHA_MAX_LENGTH:
                    drop = True

            # Repetitive ultra-short CJK fragments like "一国一一".
            if (not has_alpha) and has_cjk and len(stripped) <= 4:
                freq: dict[str, int] = {}
                for ch in stripped:
                    freq[ch] = freq.get(ch, 0) + 1
                max_freq = max(freq.values()) if freq else 0
                if max_freq >= max(_NOISE_MIN_TEXT_LENGTH, len(stripped) - _CONTEXTUAL_NOISE_REPETITIVE_MAX_FREQ_OFFSET):
                    drop = True

            # Small mixed alpha+digit snippets on CJK pages are usually from
            # UI fragments in screenshots (e.g. "worst70%", "A1", "x3.2").
            if has_alpha and has_digit and (not has_cjk):
                if len(stripped) <= _CONTEXTUAL_NOISE_MIXED_ALPHA_DIGIT_MAX_LENGTH and area_ratio < _CONTEXTUAL_NOISE_MIXED_ALPHA_DIGIT_AREA_RATIO:
                    drop = True

            # Tiny numeric-only fragments (e.g. "5%", "14%") are often chart
            # labels inside image regions and should not become editable text.
            if has_digit and (not has_alpha) and (not has_cjk):
                if len(stripped) <= _CONTEXTUAL_NOISE_TINY_NUMERIC_MAX_LENGTH and area_ratio < _CONTEXTUAL_NOISE_TINY_NUMERIC_AREA_RATIO:
                    drop = True

        # Confidence-aware cleanup for tiny non-CJK snippets.
        if (not has_cjk) and len(stripped) <= _CONTEXTUAL_NOISE_LOW_CONFIDENCE_MAX_LENGTH and conf > 0.0 and conf < _CONTEXTUAL_NOISE_LOW_CONFIDENCE_THRESHOLD:
            if area_ratio < _CONTEXTUAL_NOISE_LOW_CONFIDENCE_AREA_RATIO:
                drop = True

        if not drop:
            out.append({**it, "bbox": [x0, y0, x1, y1]})

    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _merge_line_items_prefer_primary(
    primary: list[dict],
    secondary: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Merge two *line-level* OCR item lists.

    We keep all primary items and only add secondary items that do not overlap
    meaningfully with any primary bbox. This improves recall without producing
    duplicate lines.
    """

    W = int(image_width)
    H = int(image_height)

    prim: list[dict] = []
    prim_boxes: list[tuple[float, float, float, float]] = []
    prim_heights: list[float] = []

    for it in primary:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        prim.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})
        prim_boxes.append((x0, y0, x1, y1))
        prim_heights.append(max(1.0, y1 - y0))

    prim_heights.sort()
    median_prim_h = prim_heights[len(prim_heights) // 2] if prim_heights else 10.0
    median_prim_h = max(4.0, float(median_prim_h))

    out: list[dict] = list(prim)

    def _matches_primary(bbox: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        for pb in prim_boxes:
            iou = _bbox_iou(bbox, pb)
            # Use a slightly stricter IoU threshold so we don't incorrectly
            # treat nearby-but-distinct lines as duplicates.
            if iou >= _MERGE_LINE_ITEMS_IOU_THRESHOLD:
                return True
            px0, py0, px1, py1 = pb
            p_w = max(1.0, px1 - px0)
            p_h = max(1.0, py1 - py0)
            s_w = max(1.0, x1 - x0)
            s_h = max(1.0, y1 - y0)

            # Center-in-box match is helpful for minor jitter, but it's also
            # very aggressive when the primary box is abnormally large (e.g.
            # paragraph-level). In those cases we avoid suppressing secondary
            # lines which may contain the missing text geometry.
            primary_is_reasonable_line = p_h <= (_MERGE_LINE_ITEMS_PRIMARY_HEIGHT_MULTIPLIER * median_prim_h) and p_w <= (
                _MERGE_LINE_ITEMS_PRIMARY_WIDTH_RATIO * float(W)
            )
            secondary_is_reasonable_line = s_h <= (_MERGE_LINE_ITEMS_SECONDARY_HEIGHT_MULTIPLIER * median_prim_h)
            if primary_is_reasonable_line and secondary_is_reasonable_line:
                if (
                    cx >= (px0 - _MERGE_LINE_ITEMS_CENTER_MATCH_TOLERANCE)
                    and cx <= (px1 + _MERGE_LINE_ITEMS_CENTER_MATCH_TOLERANCE)
                    and cy >= (py0 - _MERGE_LINE_ITEMS_CENTER_MATCH_TOLERANCE)
                    and cy <= (py1 + _MERGE_LINE_ITEMS_CENTER_MATCH_TOLERANCE)
                ):
                    return True
            # High overlap relative to the smaller box.
            ix0 = max(x0, px0)
            iy0 = max(y0, py0)
            ix1 = min(x1, px1)
            iy1 = min(y1, py1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            area_s = max(1.0, (x1 - x0) * (y1 - y0))
            area_p = max(1.0, (px1 - px0) * (py1 - py0))
            if inter >= _MERGE_LINE_ITEMS_OVERLAP_THRESHOLD * float(min(area_s, area_p)):
                return True
        return False

    for it in secondary:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue
        if _matches_primary(bbox_n):
            continue
        x0, y0, x1, y1 = bbox_n
        out.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})

    # Stable reading order.
    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _convert_geometry_points_px_to_pdf_coords(
    geometry_points: Any,
    *,
    image_width: int,
    image_height: int,
    page_width_pt: float,
    page_height_pt: float,
) -> list[list[float]] | None:
    if not isinstance(geometry_points, (list, tuple)):
        return None
    if image_width <= 0 or image_height <= 0:
        return None

    scale_x = float(page_width_pt) / float(image_width)
    scale_y = float(page_height_pt) / float(image_height)
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


def ocr_image_to_elements(
    image_path: str,
    *,
    page_width_pt: float,
    page_height_pt: float,
    ocr_manager: "OcrManager",
    text_refiner: AiOcrTextRefiner | None = None,
    linebreak_refiner: AiOcrTextRefiner | None = None,
    strict_no_fallback: bool = True,
    linebreak_assist: bool | None = None,
    rendered_page: "RenderedPage | None" = None,
) -> List[Dict]:
    if rendered_page is not None:
        image = rendered_page.as_pil_image()
        width, height = rendered_page.width, rendered_page.height
    else:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
    if width <= 0 or height <= 0:
        return []

    def _split_text_into_n_lines(text: str, *, n: int) -> list[str] | None:
        """Heuristically split a paragraph into N lines (no OCR re-run).

        This is a best-effort fallback used when we can *see* multi-line ink
        in a bbox (via projection), but do not have an AI vision model to
        split the text accurately. The main goal is layout fidelity (line
        count + approximate balance) rather than perfect linguistic wrapping.
        """

        n = int(n)
        raw = str(text or "").strip()
        if n <= 1 or not raw:
            return None

        # Punctuation line-breaking guards. We do not want a line to *start*
        # with closing punctuation (e.g. "：" or "）") because it is visually
        # jarring and causes obvious layout drift in PPT output.
        NO_BREAK_BEFORE = set(",.;:!?)]}、，。！？：；）】」』》〉%‰°")
        NO_BREAK_AFTER = set("([{（《【「『“‘")

        def _fix_punctuation_breaks(lines: list[str]) -> list[str]:
            if len(lines) <= 1:
                return lines

            out = [str(seg or "") for seg in lines]
            for _ in range(3):
                changed = False
                for i in range(1, len(out)):
                    prev = out[i - 1]
                    cur = out[i]
                    if not prev or not cur:
                        continue

                    # If current line begins with forbidden punctuation, move it
                    # to the end of previous line.
                    while cur and cur[0] in NO_BREAK_BEFORE and prev:
                        prev = prev + cur[0]
                        cur = cur[1:].lstrip()
                        changed = True
                        if not cur:
                            break

                    # If previous line ends with an opening punctuation, move it
                    # to the start of current line.
                    while prev and prev[-1] in NO_BREAK_AFTER and cur:
                        cur = prev[-1] + cur
                        prev = prev[:-1].rstrip()
                        changed = True
                        if not prev:
                            break

                    out[i - 1] = prev
                    out[i] = cur

                if not changed:
                    break

            return [seg for seg in (s.strip() for s in out) if seg]

        # If the upstream provider already inserted line breaks, do not
        # override them here.
        if "\n" in raw:
            lines = [seg.strip() for seg in raw.splitlines() if seg.strip()]
            if len(lines) >= 2:
                return _fix_punctuation_breaks(lines)
            return None

        is_cjk = _contains_cjk(raw)

        # Prefer word-level split when there is whitespace and we are not on a
        # CJK-heavy string.
        if (not is_cjk) and re.search(r"\s", raw):
            words = [w for w in re.split(r"\s+", raw) if w]
            if len(words) <= 1:
                return None
            total_chars = sum(len(w) for w in words) + max(0, len(words) - 1)
            target = max(1.0, float(total_chars) / float(n))
            lines: list[str] = []
            cur: list[str] = []
            cur_len = 0

            def _flush() -> None:
                nonlocal cur, cur_len
                if cur:
                    lines.append(" ".join(cur).strip())
                cur = []
                cur_len = 0

            for word in words:
                add_len = len(word) + (1 if cur else 0)
                if (
                    lines
                    and len(lines) < (n - 1)
                    and cur
                    and (float(cur_len + add_len) >= (_LINEBREAK_LINE_LENGTH_TOLERANCE * target))
                ):
                    _flush()
                cur.append(word)
                cur_len += add_len
            _flush()

            if len(lines) == n and all(lines):
                return _fix_punctuation_breaks(lines)
            # Try to rebalance by splitting the longest line(s).
            while len(lines) < n:
                longest_idx = max(range(len(lines)), key=lambda i: len(lines[i]))
                parts = lines[longest_idx].split()
                if len(parts) <= 1:
                    break
                mid = max(1, len(parts) // 2)
                left = " ".join(parts[:mid]).strip()
                right = " ".join(parts[mid:]).strip()
                if not left or not right:
                    break
                lines[longest_idx : longest_idx + 1] = [left, right]

            if len(lines) == n and all(lines):
                return _fix_punctuation_breaks(lines)
            return None

        # CJK or compact text: split by character count with punctuation-aware cuts.
        compact = re.sub(r"\s+", "", raw)
        if len(compact) < max(4, n * 2):
            return None

        break_chars = set("，。、；：！？,.!?:;）)】]》>、")
        breakpoints = [
            idx + 1
            for idx, ch in enumerate(compact)
            if ch in break_chars and idx + 1 < len(compact)
        ]
        target = float(len(compact)) / float(n)
        cuts: list[int] = []
        last = 0
        for k in range(1, n):
            ideal = int(round(float(k) * target))
            ideal = max(last + 1, min(len(compact) - 1, ideal))
            chosen = ideal
            # Pick a nearby punctuation breakpoint when available.
            if breakpoints:
                candidates = [
                    p for p in breakpoints if (last + 1) <= p <= (len(compact) - 1)
                ]
                if candidates:
                    nearest = min(candidates, key=lambda p: abs(p - ideal))
                    if abs(nearest - ideal) <= max(2, int(round(_LINEBREAK_BREAKPOINT_TOLERANCE_RATIO * target))):
                        chosen = nearest
            chosen = max(last + 1, min(len(compact) - 1, chosen))
            cuts.append(chosen)
            last = chosen

        parts: list[str] = []
        start = 0
        for cut in cuts + [len(compact)]:
            seg = compact[start:cut].strip()
            if seg:
                parts.append(seg)
            start = cut

        if len(parts) != n or not all(parts):
            return None
        return _fix_punctuation_breaks(parts)

    def _estimate_line_ranges_by_ink(
        bbox_n: tuple[float, float, float, float],
        *,
        typical_line_height: float,
        max_lines: int,
    ) -> list[tuple[float, float]] | None:
        """Estimate per-line vertical ranges using ink projection inside a bbox."""

        x0, y0, x1, y1 = bbox_n
        W = int(width)
        H = int(height)

        xi0 = max(0, min(W - 1, int(math.floor(float(x0)))))
        yi0 = max(0, min(H - 1, int(math.floor(float(y0)))))
        xi1 = max(0, min(W, int(math.ceil(float(x1)))))
        yi1 = max(0, min(H, int(math.ceil(float(y1)))))
        if xi1 - xi0 < _LINEBREAK_MIN_WIDTH_PX or yi1 - yi0 < _LINEBREAK_MIN_HEIGHT_PX:
            return None

        try:
            gray = image.crop((xi0, yi0, xi1, yi1)).convert("L")
            arr = np.asarray(gray, dtype=np.float32)
        except Exception:
            return None

        if arr.ndim != 2 or arr.size <= 0:
            return None
        h_px, w_px = arr.shape
        if h_px < _LINEBREAK_MIN_HEIGHT_PX or w_px < _LINEBREAK_MIN_WIDTH_PX:
            return None

        p95 = float(np.percentile(arr, 95.0))
        p10 = float(np.percentile(arr, 10.0))
        contrast = max(1.0, p95 - p10)
        if contrast < _LINEBREAK_INK_PROJECTION_CONTRAST_MIN:
            return None

        ink = np.clip((p95 - arr) / contrast, 0.0, 1.0)
        ink_mask = (ink >= _LINEBREAK_INK_MASK_THRESHOLD).astype(np.float32)
        row_profile = ink_mask.mean(axis=1)
        if float(np.sum(row_profile)) <= max(_LINEBREAK_MIN_ROW_PROFILE_SUM_RATIO * h_px, 1.0):
            return None

        k = max(1, int(round(h_px / _LINEBREAK_SMOOTHING_KERNEL_DIVISOR)))
        if k > 1:
            kernel = np.ones((k,), dtype=np.float32) / float(k)
            smooth = np.convolve(row_profile, kernel, mode="same")
        else:
            smooth = row_profile

        # Use an adaptive threshold: above this value we consider the row part
        # of a text line. Keep a floor to avoid missing very light text.
        th = float(np.percentile(smooth, _LINEBREAK_PERCENTILE_THRESHOLD))
        th = max(_LINEBREAK_MIN_THRESHOLD, min(_LINEBREAK_MAX_THRESHOLD, th))

        active = smooth >= th
        segments: list[tuple[int, int]] = []
        start: int | None = None
        for idx, on in enumerate(active.tolist()):
            if on and start is None:
                start = idx
            elif (not on) and start is not None:
                segments.append((start, idx))
                start = None
        if start is not None:
            segments.append((start, h_px))

        if not segments:
            return None

        min_seg_h = max(2, int(round(_LINEBREAK_MIN_SEGMENT_HEIGHT_RATIO * float(typical_line_height))))
        filtered: list[tuple[int, int]] = []
        for s, e in segments:
            if e - s < min_seg_h:
                continue
            filtered.append((s, e))
        segments = filtered
        if len(segments) < 2:
            return None

        # Merge segments separated by tiny gaps (diacritics / punctuation noise).
        merge_gap = max(1, int(round(_LINEBREAK_MERGE_GAP_RATIO * float(typical_line_height))))
        merged: list[tuple[int, int]] = []
        cur_s, cur_e = segments[0]
        for s, e in segments[1:]:
            if s - cur_e <= merge_gap:
                cur_e = e
            else:
                merged.append((cur_s, cur_e))
                cur_s, cur_e = s, e
        merged.append((cur_s, cur_e))
        segments = merged

        if len(segments) < 2:
            return None
        if len(segments) > max(2, int(max_lines)):
            return None

        ranges: list[tuple[float, float]] = []
        prev_y = float(y0)
        for s, e in segments:
            ly0 = float(y0) + float(s)
            ly1 = float(y0) + float(e)
            # Clamp and enforce monotonic.
            ly0 = max(float(y0), min(float(y1) - 1.0, ly0))
            ly1 = max(ly0 + 1.0, min(float(y1), ly1))
            if ly0 < prev_y:
                ly0 = prev_y
            if ly1 <= ly0:
                continue
            ranges.append((ly0, ly1))
            prev_y = ly1

        if len(ranges) < 2:
            return None
        return ranges

    def _heuristic_assist_line_breaks(items: list[dict], *, force: bool) -> list[dict]:
        if not items:
            return items

        heights: list[float] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if bbox_n is None:
                continue
            _, y0, _, y1 = bbox_n
            h = float(y1 - y0)
            if h > 0:
                heights.append(h)
        if heights:
            heights.sort()
            # Use a lower quantile to avoid paragraph boxes dominating the median.
            q_idx = int(round(_LINEBREAK_TYPICAL_HEIGHT_QUANTILE * float(len(heights) - 1)))
            typical_h = max(4.0, float(heights[max(0, min(len(heights) - 1, q_idx))]))
        else:
            typical_h = max(10.0, 0.02 * float(height))

        max_lines = _LINEBREAK_MAX_LINES
        split_count = 0
        out: list[dict] = []

        candidates: list[tuple[int, dict, tuple[float, float, float, float], str]] = []
        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            text = str(original.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(original.get("bbox"))
            if not text or bbox_n is None:
                continue
            if "\n" in text:
                continue
            if _is_multiline_candidate_for_linebreak_assist(
                text=text,
                bbox=bbox_n,
                image_width=int(width),
                image_height=int(height),
                median_line_height=float(typical_h),
            ):
                candidates.append((idx, original, bbox_n, text))

        # Auto-mode guard: only apply the heuristic when we have enough strong
        # multiline candidates to justify splitting. This avoids accidentally
        # splitting a small number of tall headings on otherwise line-level OCR.
        if (not force) and len(candidates) < max(
            3, int(round(_LINEBREAK_MIN_CANDIDATES_RATIO * float(len(items))))
        ):
            return items

        candidate_by_idx: dict[
            int, tuple[dict, tuple[float, float, float, float], str]
        ] = {int(idx): (orig, bb, txt) for idx, orig, bb, txt in candidates}

        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            cand = candidate_by_idx.get(int(idx))
            if cand is None:
                out.append(dict(original))
                continue
            cand_original, bbox_n, text = cand

            x0, y0, x1, y1 = bbox_n
            box_h = max(1.0, float(y1 - y0))

            ranges = _estimate_line_ranges_by_ink(
                bbox_n,
                typical_line_height=float(typical_h),
                max_lines=max_lines,
            )

            n_lines = 0
            if ranges is not None:
                n_lines = len(ranges)
            else:
                est = int(round(box_h / max(1.0, float(typical_h))))
                n_lines = max(1, min(max_lines, est))
                if n_lines < 2:
                    out.append(dict(original))
                    continue
                total_h = float(y1 - y0)
                ranges = [
                    (
                        float(y0) + total_h * float(i) / float(n_lines),
                        float(y0) + total_h * float(i + 1) / float(n_lines),
                    )
                    for i in range(n_lines)
                ]

            if ranges is None or len(ranges) < 2:
                out.append(dict(cand_original))
                continue

            # Text split fallback: balance text across detected lines.
            lines = _split_text_into_n_lines(text, n=len(ranges))
            if not lines or len(lines) != len(ranges):
                out.append(dict(cand_original))
                continue

            for (ly0, ly1), text_line in zip(ranges, lines):
                cleaned_line = str(text_line or "").strip()
                if not cleaned_line:
                    continue
                if float(ly1 - ly0) < 1.0:
                    continue
                new_item = dict(cand_original)
                new_item["text"] = cleaned_line
                new_item["bbox"] = [float(x0), float(ly0), float(x1), float(ly1)]
                new_item["linebreak_assisted"] = True
                new_item["linebreak_assist_source"] = "heuristic"
                out.append(new_item)

            split_count += 1

        if split_count > 0:
            logger.info(
                "Heuristic line-break assist applied (no AI): split_boxes=%s/%s",
                split_count,
                len(items),
            )
        return out

    elements: List[Dict] = []
    merged_items = ocr_manager.ocr_image_lines(
        image_path, image_width=width, image_height=height
    )
    last_provider_name = str(getattr(ocr_manager, "last_provider_name", "") or "")
    provider_id = str(getattr(ocr_manager, "provider_id", "") or "").lower()
    ai_primary_fallback_mode = provider_id in {"aiocr", "paddle"}
    ai_provider_used_for_page = last_provider_name == "AiOcrClient"
    skip_ai_refiners_for_page = (
        ai_primary_fallback_mode and not ai_provider_used_for_page
    )
    effective_linebreak_refiner = (
        None if skip_ai_refiners_for_page else linebreak_refiner
    )
    effective_text_refiner = None if skip_ai_refiners_for_page else text_refiner

    if (
        effective_linebreak_refiner is not None
        and merged_items
        and linebreak_assist is True
    ):
        try:
            merged_items = effective_linebreak_refiner.assist_line_breaks(
                image_path,
                items=merged_items,
                allow_heuristic_fallback=False,
            )
        except Exception as e:
            logger.warning("AI OCR line-break assist failed: %s", e)
    elif linebreak_assist is True and merged_items:
        # Fallback: when user requests line-break assist (or backend auto-enabled
        # it) but no AI vision refiner is available, split coarse paragraph-like
        # boxes using pixel projection + text balancing. This is much better
        # than letting PPT guess wraps, and keeps the pipeline usable in fully
        # open-source deployments.
        try:
            merged_items = _heuristic_assist_line_breaks(merged_items, force=True)
        except Exception as e:
            logger.warning("Heuristic line-break assist failed: %s", e)
    elif (
        merged_items
        and linebreak_assist is None
        and (not strict_no_fallback)
        and effective_linebreak_refiner is None
    ):
        # Auto best-effort: AI OCR and some gateways return paragraph-like boxes
        # even when the user didn't enable explicit line-break assist. In
        # non-strict mode we can try a conservative heuristic split to reduce
        # wrap drift in PPT output.
        try:
            provider_id = str(getattr(ocr_manager, "provider_id", "") or "").lower()
            last_provider = str(getattr(ocr_manager, "last_provider_name", "") or "")
            should_try = (
                provider_id in {"aiocr", "paddle"} or last_provider == "AiOcrClient"
            )
            if should_try:
                merged_items = _heuristic_assist_line_breaks(merged_items, force=False)
        except Exception as e:
            logger.warning("Auto heuristic line-break assist failed: %s", e)

    if (
        effective_text_refiner is not None
        and merged_items
        and last_provider_name != "AiOcrClient"
    ):
        try:
            merged_items = effective_text_refiner.refine_items(
                image_path, items=merged_items
            )
        except Exception as e:
            logger.warning("AI OCR text refinement failed: %s", e)
    # Multi-engine merge + AI refinement can still leave near-identical line boxes.
    # Deduplicate here to prevent stacked text boxes in PPT output.
    merged_items = _dedupe_overlapping_ocr_items(merged_items)
    merged_items = _filter_contextual_noise_items(
        merged_items, image_width=width, image_height=height
    )
    for item in merged_items:
        bbox = item.get("bbox")
        text = str(item.get("text") or "").strip()
        if not bbox or not text:
            continue

        try:
            bbox_pt = ocr_manager.convert_bbox_to_pdf_coords(
                bbox=bbox,
                image_width=width,
                image_height=height,
                page_width_pt=page_width_pt,
                page_height_pt=page_height_pt,
            )
        except Exception:
            continue

        geometry_points_pt = None
        if not bool(item.get("linebreak_assisted")):
            geometry_points_pt = _convert_geometry_points_px_to_pdf_coords(
                item.get("ocr_layout_geometry_points"),
                image_width=width,
                image_height=height,
                page_width_pt=page_width_pt,
                page_height_pt=page_height_pt,
            )

        elements.append(
            {
                "type": "text",
                "bbox_pt": bbox_pt,
                "text": text,
                "confidence": item.get("confidence"),
                "source": "ocr",
                "color": _sample_text_color(image, bbox),
                # Lightweight provenance for downstream QA/dedupe (no secrets).
                "ocr_provider": item.get("provider") or item.get("source"),
                "ocr_model": item.get("model"),
                "ocr_linebreak_assisted": bool(item.get("linebreak_assisted")),
                "ocr_linebreak_assist_source": item.get("linebreak_assist_source"),
                "ocr_layout_geometry_source": item.get("ocr_layout_geometry_source"),
                "ocr_layout_geometry_kind": item.get("ocr_layout_geometry_kind"),
                "ocr_layout_geometry_points_pt": geometry_points_pt,
                "ocr_image_like": bool(item.get("ocr_image_like")),
            }
        )

    return elements
