"""Shared font discovery and loading utilities.

Provides a canonical list of font fallback paths with OS detection,
plus a Pillow ImageFont loader that tries candidates in order.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from ..config import get_settings

# ---------------------------------------------------------------------------
# Platform-specific fallback font paths
# ---------------------------------------------------------------------------

_CJK_FONT_PATHS_LINUX: list[str] = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

_CJK_FONT_PATHS_MACOS: list[str] = [
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

_CJK_FONT_PATHS_WINDOWS: list[str] = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\yugothb.ttc",
]

_LATIN_FONT_PATHS_LINUX: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_LATIN_FONT_PATHS_MACOS: list[str] = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/SFNSText.ttf",
]

_LATIN_FONT_PATHS_WINDOWS: list[str] = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
]


def _detect_os() -> str:
    """Return 'linux', 'macos', or 'windows'."""
    system = sys.platform or platform.system() or ""
    s = system.lower()
    if s.startswith("linux"):
        return "linux"
    if s.startswith("darwin"):
        return "macos"
    if s.startswith("win"):
        return "windows"
    return "linux"  # fallback


def _parse_extra_font_paths(env_value: str) -> list[str]:
    """Parse a comma-separated list of font paths from an env var."""
    result: list[str] = []
    for item in env_value.replace(";", ",").split(","):
        p = item.strip()
        if p and p not in result:
            result.append(p)
    return result


def get_cjk_font_candidates() -> list[str]:
    """Return an ordered list of CJK font paths to try.

    Includes env-configured extra paths first, then OS-specific fallbacks.
    """
    settings = get_settings()
    extra = _parse_extra_font_paths(settings.extra_font_paths)
    os_name = _detect_os()

    os_cjk: list[str]
    if os_name == "macos":
        os_cjk = list(_CJK_FONT_PATHS_MACOS)
    elif os_name == "windows":
        os_cjk = list(_CJK_FONT_PATHS_WINDOWS)
    else:
        os_cjk = list(_CJK_FONT_PATHS_LINUX)

    return extra + os_cjk


def get_latin_font_candidates() -> list[str]:
    """Return an ordered list of Latin font paths to try.

    Includes env-configured extra paths first, then OS-specific fallbacks.
    """
    settings = get_settings()
    extra = _parse_extra_font_paths(settings.extra_font_paths)
    os_name = _detect_os()

    os_latin: list[str]
    if os_name == "macos":
        os_latin = list(_LATIN_FONT_PATHS_MACOS)
    elif os_name == "windows":
        os_latin = list(_LATIN_FONT_PATHS_WINDOWS)
    else:
        os_latin = list(_LATIN_FONT_PATHS_LINUX)

    return extra + os_latin


def load_pil_font(
    *,
    size_px: int,
    prefer_cjk: bool,
    cache: dict[tuple[int, bool], Any] | None = None,
) -> tuple[Any, bool]:
    """Load a Pillow ImageFont with the given size and CJK preference.

    Returns (font, is_fallback) where is_fallback is True if the default
    Pillow font was used because no candidate could be loaded.

    An optional cache dict keyed by (size_px, prefer_cjk) can be provided
    to avoid repeated font loading across calls.
    """
    key = (int(max(6, size_px)), bool(prefer_cjk))
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached

    candidates = (
        get_cjk_font_candidates() + get_latin_font_candidates()
        if prefer_cjk
        else get_latin_font_candidates() + get_cjk_font_candidates()
    )

    try:
        from PIL import ImageFont
    except Exception:
        result = (None, True)
        if cache is not None:
            cache[key] = result
        return result

    for path in candidates:
        try:
            font = ImageFont.truetype(path, size=key[0])
            result: tuple[Any, bool] = (font, False)
            if cache is not None:
                cache[key] = result
            return result
        except Exception:
            continue

    result = (ImageFont.load_default(), True)
    if cache is not None:
        cache[key] = result
    return result
