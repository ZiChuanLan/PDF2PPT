"""Parameter normalization for JobOptions.

Extracted from worker.py (originally ~300 lines of normalization boilerplate).
"""

from __future__ import annotations

from ._job_options import JobOptions


# ---------------------------------------------------------------------------
# Constants: OCR render DPI bounds
# ---------------------------------------------------------------------------
OCR_RENDER_DPI_MIN = 72          # minimum allowed OCR render DPI
OCR_RENDER_DPI_MAX = 400         # maximum allowed OCR render DPI
OCR_RENDER_DPI_TURBO_CAP = 120   # turbo mode caps effective DPI to this value
OCR_RENDER_DPI_FAST_CAP = 160    # fast mode caps effective DPI to this value

# ---------------------------------------------------------------------------
# Constants: Image background clear expand parameters
# ---------------------------------------------------------------------------
_IMG_BG_CLEAR_EXPAND_MIN_PT_DEFAULT = 0.35   # default min expansion in points
_IMG_BG_CLEAR_EXPAND_MIN_PT_LOW = 0.0        # lower bound for min expansion
_IMG_BG_CLEAR_EXPAND_MIN_PT_HIGH = 6.0       # upper bound for min expansion

_IMG_BG_CLEAR_EXPAND_MAX_PT_DEFAULT = 1.5    # default max expansion in points
_IMG_BG_CLEAR_EXPAND_MAX_PT_LOW = 0.0        # lower bound for max expansion
_IMG_BG_CLEAR_EXPAND_MAX_PT_HIGH = 8.0       # upper bound for max expansion

_IMG_BG_CLEAR_EXPAND_RATIO_DEFAULT = 0.012   # default expansion ratio
_IMG_BG_CLEAR_EXPAND_RATIO_LOW = 0.0         # lower bound for expansion ratio
_IMG_BG_CLEAR_EXPAND_RATIO_HIGH = 0.12       # upper bound for expansion ratio

# ---------------------------------------------------------------------------
# Constants: Scanned image region detection bounds
# ---------------------------------------------------------------------------
_SCANNED_REGION_MIN_AREA_RATIO_DEFAULT = 0.0025  # default min area ratio
_SCANNED_REGION_MIN_AREA_RATIO_LOW = 0.0         # lower bound
_SCANNED_REGION_MIN_AREA_RATIO_HIGH = 0.35       # upper bound

_SCANNED_REGION_MAX_AREA_RATIO_DEFAULT = 0.72    # default max area ratio
_SCANNED_REGION_MAX_AREA_RATIO_LOW = 0.05        # lower bound
_SCANNED_REGION_MAX_AREA_RATIO_HIGH = 1.0        # upper bound (100% of page)
_SCANNED_REGION_MAX_AREA_CLAMP = 1.0             # clamp ceiling for max area
_SCANNED_REGION_AREA_RATIO_STEP = 0.05           # step to ensure max > min

_SCANNED_REGION_MAX_ASPECT_RATIO_DEFAULT = 4.8   # default max aspect ratio
_SCANNED_REGION_MAX_ASPECT_RATIO_LOW = 1.2       # lower bound
_SCANNED_REGION_MAX_ASPECT_RATIO_HIGH = 30.0     # upper bound

# ---------------------------------------------------------------------------
# Constants: PaddleVL docparser max side pixels
# ---------------------------------------------------------------------------
_PADDLE_VL_MAX_SIDE_PX_DEFAULT = 2200    # default max side in pixels
_PADDLE_VL_MAX_SIDE_PX_LOW = 0          # lower bound (0 = unlimited)
_PADDLE_VL_MAX_SIDE_PX_HIGH = 6000      # upper bound

# ---------------------------------------------------------------------------
# Constants: OCR AI page / block concurrency
# ---------------------------------------------------------------------------
_OCR_AI_PAGE_CONCURRENCY_LOW = 1        # minimum pages in parallel
_OCR_AI_PAGE_CONCURRENCY_HIGH = 8       # maximum pages in parallel

_OCR_AI_BLOCK_CONCURRENCY_LOW = 1       # minimum blocks in parallel
_OCR_AI_BLOCK_CONCURRENCY_HIGH = 8      # maximum blocks in parallel

# ---------------------------------------------------------------------------
# Constants: OCR AI rate limits (RPM / TPM)
# ---------------------------------------------------------------------------
_OCR_AI_RPM_LOW = 1                 # minimum RPM
_OCR_AI_RPM_HIGH = 2000             # maximum RPM

_OCR_AI_TPM_LOW = 1                 # minimum TPM
_OCR_AI_TPM_HIGH = 2_000_000        # maximum TPM

# ---------------------------------------------------------------------------
# Constants: OCR AI max retries
# ---------------------------------------------------------------------------
_OCR_AI_MAX_RETRIES_LOW = 0         # minimum retries
_OCR_AI_MAX_RETRIES_HIGH = 8        # maximum retries


def _normalize_float(
    value: float | None,
    *,
    default: float,
    low: float,
    high: float,
) -> float:
    try:
        num = float(value) if value is not None else float(default)
    except Exception:
        num = float(default)
    if num < low:
        num = float(low)
    if num > high:
        num = float(high)
    return float(num)


def _normalize_int(
    value: int | None,
    *,
    default: int,
    low: int,
    high: int,
) -> int:
    try:
        num = int(value) if value is not None else int(default)
    except Exception:
        num = int(default)
    if num < low:
        num = int(low)
    if num > high:
        num = int(high)
    return int(num)


def normalize_job_options(
    options: JobOptions,
    default_ocr_render_dpi: int,
    ocr_concurrency: dict[str, int],
) -> JobOptions:
    """Normalize all numeric parameters in-place, fill defaults, clamp out-of-range values.

    Returns the same JobOptions instance with all fields normalized.
    """
    # --- OCR render DPI ---
    options.ocr_render_dpi = _normalize_int(
        options.ocr_render_dpi,
        default=default_ocr_render_dpi,
        low=OCR_RENDER_DPI_MIN,
        high=OCR_RENDER_DPI_MAX,
    )

    # --- Image background clear expand ---
    options.image_bg_clear_expand_min_pt = _normalize_float(
        options.image_bg_clear_expand_min_pt,
        default=_IMG_BG_CLEAR_EXPAND_MIN_PT_DEFAULT,
        low=_IMG_BG_CLEAR_EXPAND_MIN_PT_LOW,
        high=_IMG_BG_CLEAR_EXPAND_MIN_PT_HIGH,
    )
    options.image_bg_clear_expand_max_pt = _normalize_float(
        options.image_bg_clear_expand_max_pt,
        default=_IMG_BG_CLEAR_EXPAND_MAX_PT_DEFAULT,
        low=_IMG_BG_CLEAR_EXPAND_MAX_PT_LOW,
        high=_IMG_BG_CLEAR_EXPAND_MAX_PT_HIGH,
    )
    if options.image_bg_clear_expand_max_pt < options.image_bg_clear_expand_min_pt:
        options.image_bg_clear_expand_max_pt = options.image_bg_clear_expand_min_pt

    options.image_bg_clear_expand_ratio = _normalize_float(
        options.image_bg_clear_expand_ratio,
        default=_IMG_BG_CLEAR_EXPAND_RATIO_DEFAULT,
        low=_IMG_BG_CLEAR_EXPAND_RATIO_LOW,
        high=_IMG_BG_CLEAR_EXPAND_RATIO_HIGH,
    )

    # --- Scanned image region detection ---
    options.scanned_image_region_min_area_ratio = _normalize_float(
        options.scanned_image_region_min_area_ratio,
        default=_SCANNED_REGION_MIN_AREA_RATIO_DEFAULT,
        low=_SCANNED_REGION_MIN_AREA_RATIO_LOW,
        high=_SCANNED_REGION_MIN_AREA_RATIO_HIGH,
    )
    options.scanned_image_region_max_area_ratio = _normalize_float(
        options.scanned_image_region_max_area_ratio,
        default=_SCANNED_REGION_MAX_AREA_RATIO_DEFAULT,
        low=_SCANNED_REGION_MAX_AREA_RATIO_LOW,
        high=_SCANNED_REGION_MAX_AREA_RATIO_HIGH,
    )
    if (
        options.scanned_image_region_max_area_ratio
        <= options.scanned_image_region_min_area_ratio
    ):
        options.scanned_image_region_max_area_ratio = min(
            _SCANNED_REGION_MAX_AREA_CLAMP,
            options.scanned_image_region_min_area_ratio + _SCANNED_REGION_AREA_RATIO_STEP,
        )

    options.scanned_image_region_max_aspect_ratio = _normalize_float(
        options.scanned_image_region_max_aspect_ratio,
        default=_SCANNED_REGION_MAX_ASPECT_RATIO_DEFAULT,
        low=_SCANNED_REGION_MAX_ASPECT_RATIO_LOW,
        high=_SCANNED_REGION_MAX_ASPECT_RATIO_HIGH,
    )

    # --- PaddleVL docparser ---
    options.ocr_paddle_vl_docparser_max_side_px = _normalize_int(
        options.ocr_paddle_vl_docparser_max_side_px,
        default=_PADDLE_VL_MAX_SIDE_PX_DEFAULT,
        low=_PADDLE_VL_MAX_SIDE_PX_LOW,
        high=_PADDLE_VL_MAX_SIDE_PX_HIGH,
    )

    # --- OCR AI page concurrency ---
    options.ocr_ai_page_concurrency = _normalize_int(
        options.ocr_ai_page_concurrency,
        default=ocr_concurrency["page_concurrency_default"],
        low=_OCR_AI_PAGE_CONCURRENCY_LOW,
        high=ocr_concurrency["page_concurrency_max"],
    )

    # --- OCR AI block concurrency (optional) ---
    if options.ocr_ai_block_concurrency is not None:
        options.ocr_ai_block_concurrency = _normalize_int(
            options.ocr_ai_block_concurrency,
            default=ocr_concurrency["block_concurrency_default"],
            low=_OCR_AI_BLOCK_CONCURRENCY_LOW,
            high=ocr_concurrency["block_concurrency_max"],
        )

    # --- OCR AI RPM (optional) ---
    if options.ocr_ai_requests_per_minute is not None:
        options.ocr_ai_requests_per_minute = _normalize_int(
            options.ocr_ai_requests_per_minute,
            default=ocr_concurrency["rpm_default"],
            low=_OCR_AI_RPM_LOW,
            high=ocr_concurrency["rpm_max"],
        )

    # --- OCR AI TPM (optional) ---
    if options.ocr_ai_tokens_per_minute is not None:
        options.ocr_ai_tokens_per_minute = _normalize_int(
            options.ocr_ai_tokens_per_minute,
            default=ocr_concurrency["tpm_default"],
            low=_OCR_AI_TPM_LOW,
            high=ocr_concurrency["tpm_max"],
        )

    # --- OCR AI max retries ---
    options.ocr_ai_max_retries = _normalize_int(
        options.ocr_ai_max_retries,
        default=ocr_concurrency["max_retries_default"],
        low=_OCR_AI_MAX_RETRIES_LOW,
        high=ocr_concurrency["max_retries_max"],
    )

    return options
