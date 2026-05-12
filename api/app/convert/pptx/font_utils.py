"""Font mapping, text measurement, and OCR text fit utilities.

Split from a monolithic file into:
- _font_measure.py      – text measurement
- _font_wrap.py         – text wrapping
- _font_fit_mineru.py   – MinerU text style fitting
- _font_fit_ocr.py      – OCR text style fitting
"""

from __future__ import annotations

import math
from typing import Any

from ..ocr.utils import _contains_cjk, _is_cjk_char

# ── re-exports from sub-modules ───────────────────────────────────────────────

from ._font_fit_mineru import _fit_mineru_text_style  # noqa: F401
from ._font_fit_ocr import (  # noqa: F401
    _fit_ocr_text_style,  # noqa: F401
    _prefer_wrap_for_ocr_text,  # noqa: F401
    _resolve_visual_wrap_override_for_ocr_text,  # noqa: F401
)
from ._font_measure import (  # noqa: F401
    _MEASURE_FONT_CACHE,  # noqa: F401
    _char_width_factor,  # noqa: F401
    _measure_text_width_pt,  # noqa: F401
    _try_load_measure_font,  # noqa: F401
)
from ._font_wrap import (  # noqa: F401
    _measure_text_lines,  # noqa: F401
    _token_width_pt,  # noqa: F401
    _tokenize_for_wrap,  # noqa: F401
    _wrap_paragraph_to_lines,  # noqa: F401
    _wrap_text_to_width,  # noqa: F401
)


# ── functions that are used by sub-modules ────────────────────────────────────


def _map_font_name(name: str | None) -> str | None:
    if not name:
        return None
    n = str(name).strip()
    if not n:
        return None
    mapping = {
        "Helvetica": "Arial",
        "Times-Roman": "Times New Roman",
        "Courier": "Courier New",
    }
    return mapping.get(n, n)


def _fit_font_size_pt(
    text: str,
    *,
    bbox_w_pt: float,
    bbox_h_pt: float,
    wrap: bool,
    min_pt: float = 6.0,
    max_pt: float = 48.0,
    width_fit_ratio: float = 0.98,
    height_fit_ratio: float = 0.98,
) -> float:
    """Pick a conservative font size for OCR text in a fixed bbox."""
    from ._font_measure import _measure_text_lines

    text = str(text or "").strip()
    if not text:
        return float(min_pt)

    bbox_w_pt = max(1.0, float(bbox_w_pt))
    bbox_h_pt = max(1.0, float(bbox_h_pt))

    line_height = 1.18 if _contains_cjk(text) else 1.15

    lo = max(1.0, float(min_pt))
    hi = min(float(max_pt), float(bbox_h_pt))
    width_ratio = max(0.85, min(1.20, float(width_fit_ratio)))
    height_ratio = max(0.85, min(1.20, float(height_fit_ratio)))

    if wrap:
        step = 0.2
        size = hi
        while size >= lo:
            lines, max_line_w = _measure_text_lines(
                text, max_width_pt=bbox_w_pt, font_size_pt=size, wrap=wrap
            )
            lines = max(1, int(lines))
            total_h = float(lines) * float(size) * float(line_height)
            width_ok = max_line_w <= (bbox_w_pt * width_ratio)
            height_ok = total_h <= (bbox_h_pt * height_ratio)
            if width_ok and height_ok:
                return max(float(min_pt), min(float(max_pt), round(float(size), 1)))
            size -= step
        return max(float(min_pt), min(float(max_pt), round(float(lo), 1)))

    best = lo
    for _ in range(14):
        mid = (lo + hi) / 2.0
        lines, max_line_w = _measure_text_lines(
            text, max_width_pt=bbox_w_pt, font_size_pt=mid, wrap=wrap
        )
        lines = max(1, int(lines))
        total_h = float(lines) * float(mid) * float(line_height)

        width_ok = max_line_w <= (bbox_w_pt * width_ratio)
        height_ok = total_h <= (bbox_h_pt * height_ratio)

        if width_ok and height_ok:
            best = mid
            lo = mid
        else:
            hi = mid

    return max(float(min_pt), min(float(max_pt), round(float(best), 1)))


def _compact_text_length(text: str) -> int:
    return len("".join(ch for ch in str(text or "") if not ch.isspace()))


def _is_inline_short_token(text: str) -> bool:
    """Heuristic: short parenthetical/label-like token, often not body text."""
    raw = str(text or "").strip()
    if not raw:
        return False
    compact_len = _compact_text_length(raw)
    if compact_len <= 3:
        return True
    if compact_len <= 12 and ("(" in raw or ")" in raw or "/" in raw):
        return True
    alpha = sum(1 for ch in raw if ch.isalpha())
    cjk = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
    digit = sum(1 for ch in raw if ch.isdigit())
    punct = sum(1 for ch in raw if not ch.isalnum() and not ch.isspace())
    if compact_len <= 6 and alpha >= 2 and cjk == 0 and punct <= 2:
        return True
    if compact_len <= 6 and digit >= 2 and cjk == 0:
        return True
    return False


def _normalize_ocr_text_for_render(text: str) -> str:
    """Normalize OCR text while preserving meaningful line structure."""
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines)


def _split_heading_text_after_colon(text: str) -> str:
    """Split heading text at the first colon when it has a meaningful tail."""
    normalized = _normalize_ocr_text_for_render(text)
    if not normalized or "\n" in normalized:
        return normalized

    def _has_ascii_alpha(s: str) -> bool:
        return any(ch.isascii() and ch.isalpha() for ch in (s or ""))

    for sep in ("\uff1a", ":"):
        split_at = normalized.find(sep)
        if split_at < 2 or split_at >= (len(normalized) - 2):
            continue
        left_part = normalized[: split_at + 1].strip()
        right_part = normalized[split_at + 1 :].strip()
        if not left_part or not right_part:
            continue
        if _compact_text_length(right_part) < 2:
            continue
        left_has_paren = ("(" in left_part and ")" in left_part) or (
            "\uff08" in left_part and "\uff09" in left_part
        )
        right_has_paren = ("(" in right_part and ")" in right_part) or (
            "\uff08" in right_part and "\uff09" in right_part
        )
        right_has_struct_tail = any(
            token in right_part for token in ("/", "&", "+", "\u3001")
        )
        has_bilingual_signal = _has_ascii_alpha(left_part) or _has_ascii_alpha(
            right_part
        )
        if not left_has_paren:
            continue
        if not (right_has_paren or right_has_struct_tail or has_bilingual_signal):
            continue
        return f"{left_part}\n{right_part}"

    return normalized
