"""Module-level helpers for AI OCR client."""

import copy
import hashlib
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any

from .base import _clean_str, _env_flag, _env_float, _normalize_paddle_doc_backend, _normalize_paddle_doc_server_url, _resolve_paddle_doc_model_and_pipeline, _run_in_daemon_thread_with_timeout
from .result_parsing import _derive_paddle_doc_predict_max_pixels, _normalize_layout_label
from .routing import ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR
from ._ai_rate_limiter import _AiRequestRateLimiter, _AiRequestReservation, _estimate_chat_completion_tokens, _extract_completion_total_tokens
from .utils import _coerce_bbox_xyxy, _is_paddleocr_vl_model

# ---------------------------------------------------------------------------
# OCR Pipeline Constants
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# OCR Pipeline Constants
# ---------------------------------------------------------------------------

# Rate limiter
_RATE_LIMITER_CUTOFF_WINDOW_S = 60.0  # Rate limiter cutoff window (seconds)
_RATE_LIMITER_MAX_WAIT_S = 60.0  # Rate limiter max wait (seconds)
_RATE_LIMITER_SLEEP_MIN_S = 0.05  # Rate limiter min sleep (seconds)
_RATE_LIMITER_SLEEP_MAX_S = 5.0  # Rate limiter max sleep (seconds)
_CHARS_PER_TOKEN = 4.0  # Chars per token estimate

# Retry / backoff
_RETRY_BACKOFF_BASE_S = 8.0  # Retry backoff base (seconds)
_RETRY_BACKOFF_MAX_S = 0.75  # Retry backoff max (seconds)
_RETRY_BACKOFF_MULTIPLIER = 2  # Retry backoff multiplier
_RATE_LIMITED_MIN_DELAY_S = 2.0  # Rate-limited min delay (seconds)
_NON_RATE_LIMITED_MIN_DELAY_S = 0.25  # Non-rate-limited min delay (seconds)

# Debug text limits
_DEBUG_TEXT_COMPACT_LIMIT = 160  # Debug text compact limit (chars)
_DEBUG_TEXT_CONTENT_LIMIT = 400  # Debug text limit for content (chars)
_DEBUG_TEXTS_LIMIT = 240  # Debug text limit for texts (chars)
_DEBUG_LABEL_LIMIT = 64  # Debug text limit for label (chars)

# Paddle / singleflight
_PADDLE_DOC_MAX_SIDE_PX = 6000  # Max paddle doc max side px
_PADDLE_VL15_PREDICT_TIMEOUT_S = 180.0  # PaddleOCR-VL-1.5 predict timeout (env overridable)
_PADDLE_MIN_PREDICT_TIMEOUT_S = 10.0  # Min predict timeout (seconds)
_PADDLE_RETRY_TIMEOUT_CAP_S = 90.0  # Default retry timeout cap (seconds)
_SINGLEFLIGHT_WAIT_S = 3.0  # Singleflight wait default (seconds)

# Concurrency wait
_CONCURRENCY_WAIT_MIN_S = 0.01  # Min wait for concurrency (seconds)
_CONCURRENCY_WAIT_MAX_S = 0.1  # Max wait for concurrency (seconds)
_DONE_WAIT_TIMEOUT_S = 1.0  # Done wait timeout (seconds)

# Layout model
_LAYOUT_MODEL_INIT_TIMEOUT_MIN_S = 5.0  # Min layout model init timeout (seconds)
_LAYOUT_BLOCK_DIMENSION_MIN_PX = 3.0  # Min block dimension threshold (pixels)
_LAYOUT_BLOCK_PREDICT_TIMEOUT_MIN_S = 5.0  # Min layout block predict timeout (seconds)

# Image processing: padding / crop
_BLOCK_CROP_PAD_MAX_PX = 24  # Max padding pixels for block crop
_BLOCK_CROP_PAD_MIN_PX = 2  # Min padding pixels for block crop
_BLOCK_CROP_PAD_RATIO = 0.03  # Padding ratio for block crop
_BLOCK_CROP_YPAD_MAX_PX = 24  # Max Y-padding pixels for block crop
_BLOCK_CROP_YPAD_MIN_PX = 2  # Min Y-padding pixels for block crop
_BLOCK_CROP_YPAD_RATIO = 0.18  # Y-padding ratio for block crop

# Ring margin (visual bounds tightening)
_RING_YMARGIN_MAX_PX = 18  # Ring Y margin max (pixels)
_RING_YMARGIN_MIN_PX = 2  # Ring Y margin min (pixels)
_RING_YMARGIN_RATIO = 0.10  # Ring Y margin ratio
_RING_XMARGIN_MAX_PX = 18  # Ring X margin max (pixels)
_RING_XMARGIN_MIN_PX = 2  # Ring X margin min (pixels)
_RING_XMARGIN_RATIO = 0.04  # Ring X margin ratio

# Background diff thresholds
_BG_DIFF_LIGHT_THRESHOLD = 18.0  # Background diff threshold (light bg)
_BG_DIFF_DARK_THRESHOLD = 22.0  # Background diff threshold (dark bg)
_BG_DIFF_LIGHT_BG_LUMA = 150.0  # Background luma cutoff for light/dark

# Edge thresholds
_EDGE_THRESH_LOW = 22  # Edge threshold for short crops
_EDGE_THRESH_HIGH = 26  # Edge threshold for tall crops
_EDGE_HEIGHT_CUTOFF = 96  # Height cutoff for edge threshold selection

# Outer margin
_OUTER_MARGIN_MAX_PX = 12  # Outer margin max (pixels)
_OUTER_MARGIN_MIN_PX = 2  # Outer margin min (pixels)
_OUTER_MARGIN_RATIO = 0.05  # Outer margin ratio

# Row / col thresholds
_ROW_THRESHOLD_MIN_PX = 2  # Row threshold min (pixels)
_ROW_THRESHOLD_RATIO = 0.0035  # Row threshold ratio
_COL_THRESHOLD_MIN_PX = 1  # Col threshold min (pixels)
_COL_THRESHOLD_RATIO = 0.020  # Col threshold ratio

# Keep ratios (skip tightening if crop already tight)
_KEEP_AREA_RATIO = 0.94  # Keep area ratio threshold
_KEEP_WIDTH_RATIO = 0.97  # Width keep ratio threshold
_KEEP_HEIGHT_RATIO = 0.90  # Height keep ratio threshold

# Local padding (after tightening)
_PAD_X_MAX_PX = 18  # Pad X local max (pixels)
_PAD_X_MIN_PX = 2  # Pad X local min (pixels)
_PAD_X_RATIO = 0.08  # Pad X local ratio
_PAD_Y_MAX_PX = 12  # Pad Y local max (pixels)
_PAD_Y_MIN_PX = 2  # Pad Y local min (pixels)
_PAD_Y_RATIO = 0.12  # Pad Y local ratio

# Tightened keep ratios (skip if tightening barely changed bbox)
_TIGHTENED_WIDTH_RATIO = 0.985  # Tightened width keep ratio
_TIGHTENED_HEIGHT_RATIO = 0.94  # Tightened height keep ratio

# Geometry tolerance
_DEFAULT_TOLERANCE_PX = 1.5  # Default tolerance for geometry fit (pixels)

# ---------------------------------------------------------------------------
# Runtime-overridable timeout helpers
# ---------------------------------------------------------------------------
# These read from api.app.config.Settings so they can be tuned via env vars
# without code changes. Module-level constants are used as fallbacks.



logger = logging.getLogger(__name__)

_SPECIAL_OCR_TOKEN_PATTERN = re.compile(
    r"<\|/?[a-zA-Z0-9_]+\|>|</?image>|</?box>|</?text>",
    re.IGNORECASE,
)
_STANDALONE_BOX_COORDS_PATTERN = re.compile(
    r"^\s*\[\[\s*"
    r"-?\d+(?:\.\d+)?\s*,\s*"
    r"-?\d+(?:\.\d+)?\s*,\s*"
    r"-?\d+(?:\.\d+)?\s*,\s*"
    r"-?\d+(?:\.\d+)?\s*"
    r"\]\]\s*$"
)

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        value = int(str(raw).strip())
    except Exception:
        return int(default)
    return int(value)


def _get_paddle_predict_timeout() -> float:
    return _PADDLE_VL15_PREDICT_TIMEOUT_S


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _compact_debug_text(value: Any, *, limit: int = _DEBUG_TEXT_COMPACT_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _sanitize_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_"):
                continue
            sanitized[str(key)] = _sanitize_debug_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_debug_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_debug_value(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(float(value), 4)
    return value


def _coerce_layout_geometry_points(raw_bbox: Any) -> list[list[float]] | None:
    if raw_bbox is None:
        return None

    if hasattr(raw_bbox, "tolist"):
        try:
            raw_bbox = raw_bbox.tolist()
        except Exception:
            pass

    if isinstance(raw_bbox, dict):
        if all(k in raw_bbox for k in ("left", "top", "width", "height")):
            try:
                x0 = float(raw_bbox.get("left") or 0)
                y0 = float(raw_bbox.get("top") or 0)
                width = float(raw_bbox.get("width") or 0)
                height = float(raw_bbox.get("height") or 0)
                x1 = x0 + width
                y1 = y0 + height
                return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            except Exception:
                return None
        for keys in (("x0", "y0", "x1", "y1"), ("xmin", "ymin", "xmax", "ymax")):
            if not all(k in raw_bbox for k in keys):
                continue
            try:
                x0 = float(raw_bbox.get(keys[0]))
                y0 = float(raw_bbox.get(keys[1]))
                x1 = float(raw_bbox.get(keys[2]))
                y1 = float(raw_bbox.get(keys[3]))
                return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            except Exception:
                return None
        return None

    if isinstance(raw_bbox, tuple):
        raw_bbox = list(raw_bbox)
    if not isinstance(raw_bbox, list):
        return None

    if raw_bbox and all(isinstance(v, dict) for v in raw_bbox):
        points: list[list[float]] = []
        for point in raw_bbox:
            try:
                x = point.get("x")
                y = point.get("y")
                if x is None:
                    x = point.get("left")
                if y is None:
                    y = point.get("top")
                points.append([float(x), float(y)])
            except Exception:
                return None
        return points or None

    if raw_bbox and all(isinstance(v, list) and len(v) >= 2 for v in raw_bbox):
        points = []
        for point in raw_bbox:
            try:
                points.append([float(point[0]), float(point[1])])
            except Exception:
                return None
        return points or None

    if (
        len(raw_bbox) >= 8
        and len(raw_bbox) % 2 == 0
        and all(isinstance(v, (int, float)) for v in raw_bbox)
    ):
        points = []
        for idx in range(0, len(raw_bbox), 2):
            points.append([float(raw_bbox[idx]), float(raw_bbox[idx + 1])])
        return points or None

    if len(raw_bbox) == 4 and all(isinstance(v, (int, float)) for v in raw_bbox):
        x0 = float(raw_bbox[0])
        y0 = float(raw_bbox[1])
        x1 = float(raw_bbox[2])
        y1 = float(raw_bbox[3])
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    return None


def _layout_geometry_kind(raw_bbox: Any, geometry_source: str | None) -> str:
    if geometry_source == "polygon_points":
        return "polygon"
    if isinstance(raw_bbox, tuple):
        raw_bbox = list(raw_bbox)
    if isinstance(raw_bbox, list):
        if raw_bbox and all(isinstance(v, dict) for v in raw_bbox):
            return "polygon"
        if raw_bbox and all(isinstance(v, list) and len(v) >= 2 for v in raw_bbox):
            return "polygon"
        if len(raw_bbox) >= 8 and len(raw_bbox) % 2 == 0:
            return "polygon"
    return "bbox"


def _clone_image_region_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _clone_image_region_payload(item) for key, item in value.items()
        }
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        return [_clone_image_region_payload(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return float(value)
    return value


def _build_layout_image_region_payload(
    *,
    bbox: list[float],
    label: str,
    score: float | None,
    order: int | None,
    geometry_source: str | None,
    geometry_kind: str | None,
    geometry_points: list[list[float]] | None,
) -> Any:
    bbox_xyxy = [float(v) for v in bbox[:4]]
    polygon_points = (
        _coerce_layout_geometry_points(geometry_points)
        if str(geometry_kind or "").strip().lower() == "polygon"
        else None
    )
    if polygon_points is None:
        return bbox_xyxy
    return {
        "bbox": bbox_xyxy,
        "label": str(label or ""),
        "score": score,
        "order": order,
        "geometry_source": geometry_source,
        "geometry_kind": "polygon",
        "geometry_points": polygon_points,
    }


def _normalize_ai_layout_model_name(value: Any) -> str:
    """Normalize layout model name using the centralized registry."""
    from app.convert.ocr.layout_models import normalize_layout_model_id

    return normalize_layout_model_id(str(value) if value is not None else None)


def _resolve_paddlex_layout_model_name(value: Any) -> str:
    """Resolve a layout model ID to its PaddleX model name."""
    from app.convert.ocr.layout_models import LAYOUT_MODELS, normalize_layout_model_id

    normalized = normalize_layout_model_id(str(value) if value is not None else None)
    info = LAYOUT_MODELS.get(normalized)
    if info and info.paddlex_model_name:
        return info.paddlex_model_name
    return "PP-DocLayoutV3"


def _coerce_int_in_range(
    value: Any,
    *,
    low: int,
    high: int,
    default: int | None = None,
) -> int | None:
    try:
        if value is None:
            raise ValueError("value is none")
        parsed = int(value)
    except Exception:
        return default
    if parsed < low:
        return low
    if parsed > high:
        return high
    return int(parsed)



def _extract_error_status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        try:
            value = getattr(error, attr)
        except Exception:
            value = None
        if isinstance(value, int) and value > 0:
            return value
    response = getattr(error, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            try:
                value = getattr(response, attr)
            except Exception:
                value = None
            if isinstance(value, int) and value > 0:
                return value
    return None


def _is_retryable_chat_completion_error(error: BaseException) -> bool:
    status_code = _extract_error_status_code(error)
    if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    lowered = str(error or "").strip().lower()
    retry_markers = (
        "timed out",
        "timeout",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection refused",
        "remote protocol error",
        "server disconnected",
        "service unavailable",
        "gateway",
        "try again",
        "overloaded",
    )
    return any(marker in lowered for marker in retry_markers)


def _get_retry_backoff_base() -> float:
    """Return the base retry backoff in seconds (env-overridable)."""
    return _RETRY_BACKOFF_BASE_S


def _get_rate_limited_min_delay() -> float:
    """Return the minimum delay for rate-limited requests (env-overridable)."""
    return _RATE_LIMITED_MIN_DELAY_S


def _retry_delay_s_for_chat_completion(
    *,
    attempt_index: int,
    error: BaseException,
) -> float:
    status_code = _extract_error_status_code(error)
    base_delay = min(_get_retry_backoff_base(), _RETRY_BACKOFF_MAX_S * (_RETRY_BACKOFF_MULTIPLIER ** max(0, int(attempt_index))))
    if status_code == 429:
        return max(_get_rate_limited_min_delay(), base_delay)
    return max(_NON_RATE_LIMITED_MIN_DELAY_S, base_delay)


def _run_chat_completion_request(
    *,
    client: Any,
    provider_id: str | None,
    model: str,
    timeout_s: float,
    max_retries: int,
    request_limiter: _AiRequestRateLimiter | None,
    request_label: str,
    logger_obj: logging.Logger,
    messages: Any,
    max_tokens: int | None,
    **kwargs: Any,
) -> Any:
    estimated_tokens = _estimate_chat_completion_tokens(
        messages=messages,
        max_tokens=max_tokens,
    )
    total_attempts = max(0, int(max_retries))
    attempt_index = 0
    while True:
        reservation: _AiRequestReservation | None = None
        try:
            if request_limiter is not None:
                reservation = request_limiter.acquire(estimated_tokens=estimated_tokens)
            completion = client.with_options(
                timeout=timeout_s,
                max_retries=0,
            ).chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                **kwargs,
            )
            if reservation is not None:
                reservation.finalize(
                    actual_tokens=_extract_completion_total_tokens(completion)
                )
            return completion
        except Exception as exc:
            if reservation is not None:
                reservation.finalize(actual_tokens=None)
            if (
                attempt_index >= total_attempts
                or not _is_retryable_chat_completion_error(exc)
            ):
                raise
            delay_s = _retry_delay_s_for_chat_completion(
                attempt_index=attempt_index,
                error=exc,
            )
            logger_obj.warning(
                "AI OCR request retrying (label=%s, provider=%s, model=%s, attempt=%s/%s, delay_s=%.2f): %s",
                request_label,
                provider_id or "",
                model or "",
                attempt_index + 1,
                total_attempts,
                delay_s,
                exc,
            )
            time.sleep(delay_s)
            attempt_index += 1

