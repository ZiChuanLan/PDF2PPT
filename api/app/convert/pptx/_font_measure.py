"""Font measurement helpers (extracted from font_utils.py)."""

from __future__ import annotations

import math
from typing import Any

from ..ocr.utils import _contains_cjk, _is_cjk_char


_MEASURE_FONT_CACHE: dict[tuple[int, bool], Any] = {}


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


def _char_width_factor(ch: str) -> float:
    """Very rough glyph width estimate relative to font size."""
    if not ch:
        return 0.0
    if ch.isspace():
        return 0.33
    if _is_cjk_char(ch):
        return 1.0
    if "0" <= ch <= "9":
        return 0.58
    if "A" <= ch <= "Z":
        return 0.70
    if "a" <= ch <= "z":
        return 0.56
    return 0.38


def _try_load_measure_font(*, size_px: int, prefer_cjk: bool) -> Any | None:
    """Load a reasonably representative font for measuring text width."""
    from ...utils.fonts import load_pil_font

    key = (int(max(6, size_px)), bool(prefer_cjk))
    if key in _MEASURE_FONT_CACHE:
        return _MEASURE_FONT_CACHE[key]

    font, is_fallback = load_pil_font(
        size_px=size_px,
        prefer_cjk=prefer_cjk,
    )

    if is_fallback or font is None:
        _MEASURE_FONT_CACHE[key] = None
        return None

    _MEASURE_FONT_CACHE[key] = font
    return font


def _measure_text_width_pt(
    text: str,
    *,
    font_size_pt: float,
    prefer_cjk: bool,
) -> float:
    """Best-effort text width in the same 'pt-like' space used by bbox_w_pt."""
    if not text:
        return 0.0

    font_size_pt = max(1.0, float(font_size_pt))
    font = _try_load_measure_font(
        size_px=int(round(font_size_pt)),
        prefer_cjk=prefer_cjk,
    )
    if font is None:
        return sum(_char_width_factor(ch) for ch in text) * font_size_pt

    try:
        width = float(font.getlength(text))  # type: ignore[attr-defined]
        if math.isfinite(width) and width > 0.0:
            return width
    except Exception:
        pass

    try:
        bbox = font.getbbox(text)
        width = float(bbox[2] - bbox[0])
        if math.isfinite(width) and width > 0.0:
            return width
    except Exception:
        pass

    return sum(_char_width_factor(ch) for ch in text) * font_size_pt
