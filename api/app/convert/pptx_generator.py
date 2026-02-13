"""IR -> PPTX generation (python-pptx).

This module renders a PDF layout IR (produced by :func:`app.convert.pdf_parser.parse_pdf_to_ir`
and optionally enriched by OCR) into an editable PowerPoint presentation.

Key behaviors:
- Default slide size matches the PDF page size (in points) for 1:1 coordinate mapping.
- Optional 16:9 mode letterboxes and centers the PDF content.
- Text elements become editable textboxes with best-effort font preservation.
- Image elements are placed by bbox.
- Table elements are rendered as PPT tables when structured cells are available.
- Scanned pages (no text layer): render the page as a background image, mask OCR regions,
  erase OCR/image regions in the render, then overlay editable text.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models.error import AppException, ErrorCode


# PowerPoint uses EMUs (English Metric Units): 914400 EMU = 1 inch.
_EMU_PER_INCH = 914_400
_PTS_PER_INCH = 72.0
_EMU_PER_PT = _EMU_PER_INCH / _PTS_PER_INCH  # 12700.0


@dataclass(frozen=True)
class SlideTransform:
    """Coordinate transform from a PDF page (pt, bottom-left origin) to PPT slide EMUs."""

    page_width_pt: float
    page_height_pt: float
    slide_width_emu: int
    slide_height_emu: int
    scale: float
    offset_x_emu: float
    offset_y_emu: float


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _coerce_bbox_pt(bbox: Any) -> tuple[float, float, float, float]:
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x0, y0, x1, y1 = bbox
        x0f, y0f, x1f, y1f = float(x0), float(y0), float(x1), float(y1)
        # Normalize ordering in case upstream produced inverted coordinates.
        return (min(x0f, x1f), min(y0f, y1f), max(x0f, x1f), max(y0f, y1f))
    raise ValueError(f"Invalid bbox_pt: {bbox!r}")


def _bbox_area_ratio_pt(
    bbox: Any, *, page_w_pt: float, page_h_pt: float
) -> float:
    """Return bbox/page area ratio in pt-space, or 0 for invalid inputs."""

    if page_w_pt <= 0 or page_h_pt <= 0:
        return 0.0
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return 0.0
    area = max(0.0, float(x1 - x0) * float(y1 - y0))
    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    return float(area) / float(page_area)


def _is_near_full_page_bbox_pt(
    bbox: Any,
    *,
    page_w_pt: float,
    page_h_pt: float,
    min_area_ratio: float = 0.88,
    edge_tol_ratio: float = 0.015,
) -> bool:
    """Whether bbox is essentially a page-sized background image."""

    if page_w_pt <= 0 or page_h_pt <= 0:
        return False
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return False
    if x1 <= x0 or y1 <= y0:
        return False

    area_ratio = _bbox_area_ratio_pt(
        [x0, y0, x1, y1], page_w_pt=page_w_pt, page_h_pt=page_h_pt
    )
    tol_x = max(2.0, float(edge_tol_ratio) * float(page_w_pt))
    tol_y = max(2.0, float(edge_tol_ratio) * float(page_h_pt))
    touches_edges = (
        x0 <= tol_x
        and y0 <= tol_y
        and (float(page_w_pt) - x1) <= tol_x
        and (float(page_h_pt) - y1) <= tol_y
    )
    return bool(area_ratio >= float(min_area_ratio) and touches_edges)


def _hex_to_rgb(color: str | None) -> tuple[int, int, int] | None:
    if not color:
        return None
    s = str(color).strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        return None
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def _rgb_luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (0.2126 * float(r)) + (0.7152 * float(g)) + (0.0722 * float(b))


def _rgb_sq_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    dr = int(a[0]) - int(b[0])
    dg = int(a[1]) - int(b[1])
    db = int(a[2]) - int(b[2])
    return (dr * dr) + (dg * dg) + (db * db)


def _pick_contrasting_text_rgb(bg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return (0, 0, 0) if _rgb_luma(bg_rgb) >= 130.0 else (255, 255, 255)


def _map_font_name(name: str | None) -> str | None:
    if not name:
        return None
    n = str(name).strip()
    if not n:
        return None
    # Best-effort font mapping. PowerPoint will substitute missing fonts, but mapping
    # common PDF fonts to safe fonts helps consistency across platforms.
    mapping = {
        "Helvetica": "Arial",
        "Times-Roman": "Times New Roman",
        "Courier": "Courier New",
    }
    return mapping.get(n, n)


def _contains_cjk(text: str) -> bool:
    for ch in text or "":
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
            or 0x3400 <= code <= 0x4DBF  # CJK Unified Ideographs Extension A
            or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
            or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
        ):
            return True
    return False


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0x3400 <= code <= 0x4DBF  # CJK Unified Ideographs Extension A
        or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
        or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
    )


def _char_width_factor(ch: str) -> float:
    """Very rough glyph width estimate relative to font size.

    We use this to pick a conservative font size for OCR text boxes without
    relying on Office-specific rendering APIs.
    """

    if not ch:
        return 0.0
    if ch.isspace():
        return 0.33
    if _is_cjk_char(ch):
        return 1.0
    # ASCII-ish heuristics.
    if "0" <= ch <= "9":
        return 0.58
    if "A" <= ch <= "Z":
        return 0.70
    if "a" <= ch <= "z":
        return 0.56
    # punctuation / symbols
    return 0.38


_MEASURE_FONT_CACHE: dict[tuple[int, bool], Any] = {}


def _try_load_measure_font(*, size_px: int, prefer_cjk: bool) -> Any | None:
    """Load a reasonably representative font for measuring text width.

    The PPT generator runs on Linux, while the resulting PPTX is viewed in
    Office/WPS on different OSes. We only need *approximate* metrics to decide
    font size and line breaks. If no suitable font is available, callers should
    fall back to heuristic width factors.
    """

    try:
        from PIL import ImageFont
    except Exception:
        return None

    key = (int(max(6, size_px)), bool(prefer_cjk))
    if key in _MEASURE_FONT_CACHE:
        return _MEASURE_FONT_CACHE[key]

    candidates: list[str] = []
    if prefer_cjk:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            ]
        )

    # Latin fallbacks (Arial-like) for width estimation.
    candidates.extend(
        [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )

    for path in candidates:
        try:
            font = ImageFont.truetype(path, size=key[0])
            _MEASURE_FONT_CACHE[key] = font
            return font
        except Exception:
            continue

    _MEASURE_FONT_CACHE[key] = None
    return None


def _measure_text_width_pt(
    text: str,
    *,
    font_size_pt: float,
    prefer_cjk: bool,
) -> float:
    """Best-effort text width in the same 'pt-like' space used by bbox_w_pt.

    We treat the font size (pt) as a pixel size at 72 DPI. That keeps ratios
    consistent and is sufficient for line-break/fit heuristics.
    """

    if not text:
        return 0.0

    font_size_pt = max(1.0, float(font_size_pt))
    font = _try_load_measure_font(
        size_px=int(round(font_size_pt)),
        prefer_cjk=prefer_cjk,
    )
    if font is None:
        return sum(_char_width_factor(ch) for ch in text) * font_size_pt

    # Pillow >=8 exposes getlength() for accurate advance-width measurement.
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


def _measure_text_lines(
    text: str,
    *,
    max_width_pt: float,
    font_size_pt: float,
    wrap: bool,
) -> tuple[int, float]:
    """Return (line_count, max_line_width_pt) for a text string."""

    if not text:
        return (0, 0.0)

    max_width_pt = max(1.0, float(max_width_pt))
    font_size_pt = max(1.0, float(font_size_pt))

    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs = [p for p in paragraphs if p.strip()]
    if not paragraphs:
        return (0, 0.0)

    total_lines = 0
    max_line_w = 0.0

    for para in paragraphs:
        prefer_cjk = _contains_cjk(para)
        if not wrap:
            w = _measure_text_width_pt(
                para,
                font_size_pt=font_size_pt,
                prefer_cjk=prefer_cjk,
            )
            total_lines += 1
            max_line_w = max(max_line_w, w)
            continue

        wrapped = _wrap_paragraph_to_lines(
            para, max_width_pt=max_width_pt, font_size_pt=font_size_pt
        )
        if not wrapped:
            wrapped = [para]
        total_lines += len(wrapped)
        for line in wrapped:
            line_w = _measure_text_width_pt(
                line,
                font_size_pt=font_size_pt,
                prefer_cjk=prefer_cjk,
            )
            max_line_w = max(max_line_w, float(line_w))

    return (total_lines, float(max_line_w))


def _tokenize_for_wrap(para: str) -> list[str]:
    if (not _contains_cjk(para)) and (" " in para):
        tokens: list[str] = []
        parts = [p for p in para.split(" ") if p != ""]
        for i, part in enumerate(parts):
            if i > 0:
                tokens.append(" ")
            tokens.append(part)
        return tokens
    return list(para)


def _token_width_pt(token: str, *, font_size_pt: float, prefer_cjk: bool) -> float:
    return _measure_text_width_pt(
        token,
        font_size_pt=float(font_size_pt),
        prefer_cjk=bool(prefer_cjk),
    )


def _wrap_paragraph_to_lines(
    para: str, *, max_width_pt: float, font_size_pt: float
) -> list[str]:
    max_width_pt = max(1.0, float(max_width_pt))
    font_size_pt = max(1.0, float(font_size_pt))
    if not para:
        return [""]

    tokens = _tokenize_for_wrap(para)
    prefer_cjk = _contains_cjk(para)
    lines: list[str] = []
    current_tokens: list[str] = []
    current_width = 0.0

    def _flush_current() -> None:
        nonlocal current_tokens, current_width
        if not current_tokens:
            return
        line = "".join(current_tokens).rstrip()
        if line:
            lines.append(line)
        current_tokens = []
        current_width = 0.0

    for token in tokens:
        token_w = _token_width_pt(token, font_size_pt=font_size_pt, prefer_cjk=prefer_cjk)
        if token == " " and not current_tokens:
            continue

        if token_w <= max_width_pt:
            if current_width <= 0.0:
                current_tokens = [token]
                current_width = token_w
                continue
            if current_width + token_w <= max_width_pt:
                current_tokens.append(token)
                current_width += token_w
                continue
            _flush_current()
            if token != " ":
                current_tokens = [token]
                current_width = token_w
            continue

        # Token itself is wider than one line; split by character.
        for ch in token:
            ch_w = _measure_text_width_pt(
                ch,
                font_size_pt=font_size_pt,
                prefer_cjk=prefer_cjk,
            )
            if current_width <= 0.0:
                current_tokens = [ch]
                current_width = ch_w
                continue
            if current_width + ch_w <= max_width_pt:
                current_tokens.append(ch)
                current_width += ch_w
                continue
            _flush_current()
            current_tokens = [ch]
            current_width = ch_w

    _flush_current()
    if not lines:
        return [para]

    # Punctuation guards: avoid line breaks that leave closing punctuation at
    # the beginning of a line (e.g. "：") or opening punctuation at the end of
    # a line (e.g. "（"). This improves visual fidelity for CJK headings.
    NO_BREAK_BEFORE = set(",.;:!?)]}、，。！？：；）】」』》〉%‰°")
    NO_BREAK_AFTER = set("([{（《【「『“‘")

    out = [str(seg or "") for seg in lines]
    for _ in range(3):
        changed = False
        for i in range(1, len(out)):
            prev = out[i - 1]
            cur = out[i]
            if not prev or not cur:
                continue

            while cur and cur[0] in NO_BREAK_BEFORE and prev:
                prev = prev + cur[0]
                cur = cur[1:].lstrip()
                changed = True
                if not cur:
                    break

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

    out = [seg for seg in (s.strip() for s in out) if seg]
    return out if out else [para]


def _wrap_text_to_width(
    text: str, *, max_width_pt: float, font_size_pt: float
) -> str:
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    wrapped_lines: list[str] = []
    for para in paragraphs:
        cleaned = para.strip()
        if not cleaned:
            continue
        wrapped_lines.extend(
            _wrap_paragraph_to_lines(
                cleaned, max_width_pt=max_width_pt, font_size_pt=font_size_pt
            )
        )
    return "\n".join([line for line in wrapped_lines if line.strip()])


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

    text = str(text or "").strip()
    if not text:
        return float(min_pt)

    bbox_w_pt = max(1.0, float(bbox_w_pt))
    bbox_h_pt = max(1.0, float(bbox_h_pt))

    # A rough line-height multiplier; PowerPoint text metrics vary by font, but
    # we want to avoid overflow in common viewers (Office/WPS/Google Slides).
    line_height = 1.18 if _contains_cjk(text) else 1.15

    lo = max(1.0, float(min_pt))
    hi = min(float(max_pt), float(bbox_h_pt))
    width_ratio = max(0.85, min(1.20, float(width_fit_ratio)))
    height_ratio = max(0.85, min(1.20, float(height_fit_ratio)))

    # For wrapped text, layout fit is not monotonic (line breaks jump between
    # candidate sizes), so binary search can get trapped in tiny fonts.
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
    # Non-wrap is close to monotonic; binary search is fine.
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


def _set_slide_size_type(prs: Any, *, slide_w_emu: int, slide_h_emu: int) -> None:
    """Set sldSz@type to reduce size/aspect surprises in some viewers."""

    try:
        w = float(slide_w_emu)
        h = float(slide_h_emu)
        if w <= 0 or h <= 0:
            return
        ratio = w / h
    except Exception:
        return

    # Prefer "custom" unless we're close to a known widescreen/standard ratio.
    candidates: dict[str, float] = {
        "screen4x3": 4.0 / 3.0,
        "screen16x10": 16.0 / 10.0,
        "screen16x9": 16.0 / 9.0,
    }
    best_type = min(candidates, key=lambda k: abs(ratio - candidates[k]))
    if abs(ratio - candidates[best_type]) > 0.08:
        best_type = "custom"

    try:
        prs.part.presentation._element.sldSz.set("type", best_type)  # type: ignore[attr-defined]
    except Exception:
        pass


def _infer_font_size_pt(element: dict[str, Any], *, bbox_h_pt: float) -> float:
    size = float(element.get("font_size_pt") or 0.0)
    if size > 0.1:
        return size
    # OCR blocks may not have font info. Use bbox height as a rough proxy.
    source = str(element.get("source") or "")
    if source == "ocr":
        # For scanned pages we want to visually match the source slide. OCR line
        # boxes are usually tight, so we can start from the bbox height and let
        # PowerPoint shrink text if needed (TEXT_TO_FIT_SHAPE).
        multiplier = 0.85
        return max(4.5, min(96.0, bbox_h_pt * multiplier))
    multiplier = 0.8
    return max(8.0, min(48.0, bbox_h_pt * multiplier))


def _build_transform(
    *,
    page_width_pt: float,
    page_height_pt: float,
    slide_width_emu: int,
    slide_height_emu: int,
) -> SlideTransform:
    if page_width_pt <= 0 or page_height_pt <= 0:
        raise ValueError("Invalid page dimensions")

    content_w_emu = page_width_pt * _EMU_PER_PT
    content_h_emu = page_height_pt * _EMU_PER_PT

    # Fit page content into slide while preserving aspect ratio.
    scale = min(slide_width_emu / content_w_emu, slide_height_emu / content_h_emu)
    offset_x = (slide_width_emu - content_w_emu * scale) / 2.0
    offset_y = (slide_height_emu - content_h_emu * scale) / 2.0

    return SlideTransform(
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
        slide_width_emu=int(slide_width_emu),
        slide_height_emu=int(slide_height_emu),
        scale=float(scale),
        offset_x_emu=float(offset_x),
        offset_y_emu=float(offset_y),
    )


def _bbox_pt_to_slide_emu(
    bbox_pt: Any, *, transform: SlideTransform
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)

    left = transform.offset_x_emu + x0 * _EMU_PER_PT * transform.scale
    # IR coordinates come from PyMuPDF (`page.get_text("dict")`) and OCR which both
    # use a top-left origin with Y increasing downward.
    top = transform.offset_y_emu + y0 * _EMU_PER_PT * transform.scale
    width = (x1 - x0) * _EMU_PER_PT * transform.scale
    height = (y1 - y0) * _EMU_PER_PT * transform.scale

    # PowerPoint expects integer EMUs.
    return (
        int(round(left)),
        int(round(top)),
        max(0, int(round(width))),
        max(0, int(round(height))),
    )


def _iter_page_elements(
    page: dict[str, Any], *, type_name: str
) -> Iterable[dict[str, Any]]:
    for el in page.get("elements") or []:
        if isinstance(el, dict) and el.get("type") == type_name:
            yield el


def _render_pdf_page_png(
    pdf_path: Path,
    *,
    page_index: int,
    dpi: int,
    out_path: Path,
) -> Any:
    try:
        pymupdf = importlib.import_module("pymupdf")
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="PyMuPDF (pymupdf) is required for scanned-page rendering",
            details={"error": str(e)},
        )
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Unable to open source PDF for scanned-page rendering",
            details={"path": str(pdf_path), "error": str(e)},
        )

    try:
        page = doc.load_page(int(page_index))
        _ensure_parent_dir(out_path)
        cs_rgb = getattr(pymupdf, "csRGB", None)
        try:
            if cs_rgb is not None:
                pix = page.get_pixmap(dpi=int(dpi), colorspace=cs_rgb, alpha=False)
            else:
                pix = page.get_pixmap(dpi=int(dpi), alpha=False)
        except TypeError:
            # Older/newer PyMuPDF versions may not accept colorspace/alpha arguments.
            pix = page.get_pixmap(dpi=int(dpi))
        pix.save(str(out_path))
        return pix
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Failed to render scanned PDF page to image",
            details={"path": str(pdf_path), "page_index": page_index, "error": str(e)},
        )
    finally:
        doc.close()


def _detect_image_regions_from_render(
    render_path: Path,
    *,
    page_width_pt: float,
    page_height_pt: float,
    dpi: int,
    ocr_text_elements: list[dict[str, Any]] | None = None,
    max_regions: int = 12,
    merge_gap_scale: float = 0.06,
) -> list[list[float]]:
    """Heuristically detect non-text image regions on a scanned page.

    This is a best-effort fallback when AI layout assist is disabled/unavailable.
    It tries to find "busy" visual regions (diagrams, screenshots, photos) by:
    - masking out OCR text boxes on the rendered page image
    - edge-detecting the remaining content
    - connected-component grouping of edge pixels

    Returns bboxes in *PDF point* coordinates using the IR convention (top-left
    origin, y increasing downward).
    """

    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return []

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return []

    W, H = img.size
    if W <= 0 or H <= 0:
        return []

    scale = float(dpi) / _PTS_PER_INCH  # px per pt

    # 1) Build a text mask to reduce edges caused by glyph strokes.
    #
    # NOTE: OCR engines sometimes output spurious bboxes inside icons/photos
    # (e.g. "Br" inside a logo). If we mask those boxes we may erase the very
    # edges we need to detect the image region. We therefore ignore OCR boxes
    # that look abnormally tall/small relative to a baseline line height.
    mask = Image.new("L", (W, H), 0)
    # Keep the concrete pixel rectangles we masked so we can also "paint out"
    # text in the RGB image using a *local* background color. This avoids
    # creating hard-edged rectangles when the slide background is non-uniform
    # (gradients / cards), which otherwise confuses the edge detector.
    masked_rects_px: list[tuple[int, int, int, int]] = []
    if ocr_text_elements:
        baseline_h_pt = _estimate_baseline_ocr_line_height_pt(
            ocr_text_elements=ocr_text_elements,
            page_w_pt=float(page_width_pt),
        )

        draw = ImageDraw.Draw(mask)
        for el in ocr_text_elements:
            bbox_pt = el.get("bbox_pt")
            try:
                x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue

            w_pt = max(1.0, float(x1 - x0))
            h_pt = max(1.0, float(y1 - y0))
            if h_pt < (0.35 * baseline_h_pt):
                continue
            width_ratio = w_pt / max(1.0, float(page_width_pt))
            # Better OCR models often detect lots of small UI lines inside
            # screenshots/diagrams. Masking those bboxes erases the edges we
            # need to detect the screenshot region, causing the region to be
            # split into multiple fragments. Skip narrow+short boxes so we
            # mostly mask real slide text (wider and/or taller).
            if width_ratio < 0.18 and h_pt < (0.78 * baseline_h_pt):
                continue
            if h_pt > (2.8 * baseline_h_pt):
                # Keep wide headings (real text), but ignore tall+narrow boxes
                # which are often false positives inside icons/photos.
                if w_pt < (3.2 * h_pt):
                    continue
            # Expand a bit to cover anti-aliased edges around characters.
            pad_pt = max(1.0, min(5.0, 0.14 * h_pt))
            x0p = int(round((x0 - pad_pt) * scale))
            y0p = int(round((y0 - pad_pt) * scale))
            x1p = int(round((x1 + pad_pt) * scale))
            y1p = int(round((y1 + pad_pt) * scale))

            x0p = max(0, min(W - 1, x0p))
            y0p = max(0, min(H - 1, y0p))
            x1p = max(0, min(W, x1p))
            y1p = max(0, min(H, y1p))
            if x1p <= x0p or y1p <= y0p:
                continue

            draw.rectangle([x0p, y0p, x1p, y1p], fill=255)
            masked_rects_px.append((x0p, y0p, x1p, y1p))

        # Dilate the mask a bit to cover edge halos.
        try:
            mask = mask.filter(ImageFilter.MaxFilter(5))
        except Exception:
            pass

    def _median_rgb(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
        if not samples:
            return (255, 255, 255)
        rs = sorted(int(s[0]) for s in samples)
        gs = sorted(int(s[1]) for s in samples)
        bs = sorted(int(s[2]) for s in samples)
        mid = len(rs) // 2
        return (rs[mid], gs[mid], bs[mid])

    def _sample_local_bg_rgb(
        source: Image.Image, *, x0: int, y0: int, x1: int, y1: int
    ) -> tuple[int, int, int]:
        # Sample just outside the bbox so we don't hit glyph pixels.
        pad = 4
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2
        pts = [
            (x0 - pad, y0 - pad),
            (x1 + pad, y0 - pad),
            (x0 - pad, y1 + pad),
            (x1 + pad, y1 + pad),
            (x0 - pad, cy),
            (x1 + pad, cy),
            (cx, y0 - pad),
            (cx, y1 + pad),
        ]
        cols: list[tuple[int, int, int]] = []
        for px, py in pts:
            px = max(0, min(int(px), int(W - 1)))
            py = max(0, min(int(py), int(H - 1)))
            try:
                r, g, b = source.getpixel((px, py))
                cols.append((int(r), int(g), int(b)))
            except Exception:
                continue
        return _median_rgb(cols)

    if masked_rects_px and mask.getbbox():
        try:
            masked_img = img.copy()
            draw_masked = ImageDraw.Draw(masked_img)
            for x0p, y0p, x1p, y1p in masked_rects_px:
                bg = _sample_local_bg_rgb(img, x0=x0p, y0=y0p, x1=x1p, y1=y1p)
                draw_masked.rectangle([x0p, y0p, x1p, y1p], fill=bg)
            # A tiny blur helps hide hard boundaries of painted regions.
            try:
                masked_img = masked_img.filter(ImageFilter.BoxBlur(0.6))
            except Exception:
                pass
            img = masked_img
        except Exception:
            # If this fails for any reason, fall back to using the original image.
            pass

    # 2) Edge-detect + threshold.
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    # Threshold chosen empirically for rendered PDF pages (antialiasing present).
    # Slightly lower improves recall for screenshots with soft drop-shadows.
    threshold = 32
    bw = edges.point(lambda p: 255 if p > threshold else 0, "L")
    # Thicken edges to connect disjoint strokes belonging to the same image.
    try:
        bw = bw.filter(ImageFilter.MaxFilter(5))
    except Exception:
        pass

    # 3) Connected components on a downsampled binary image.
    factor = 8 if max(W, H) >= 3000 else (6 if max(W, H) >= 1600 else 4)
    SW = max(1, W // factor)
    SH = max(1, H // factor)
    small = bw.resize((SW, SH), Image.NEAREST)
    px = small.load()

    visited: list[bytearray] = [bytearray(SW) for _ in range(SH)]
    comps: list[tuple[int, float, tuple[int, int, int, int]]] = []  # (area, density, bbox)
    page_area = float(SW * SH)

    for y in range(SH):
        row = visited[y]
        for x in range(SW):
            if row[x]:
                continue
            if px[x, y] == 0:
                continue
            # BFS over 4-neighborhood.
            q: list[tuple[int, int]] = [(x, y)]
            row[x] = 1
            minx = maxx = x
            miny = maxy = y
            count = 0
            while q:
                cx, cy = q.pop()
                count += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                nx = cx - 1
                if nx >= 0 and not visited[cy][nx] and px[nx, cy] != 0:
                    visited[cy][nx] = 1
                    q.append((nx, cy))
                nx = cx + 1
                if nx < SW and not visited[cy][nx] and px[nx, cy] != 0:
                    visited[cy][nx] = 1
                    q.append((nx, cy))
                ny = cy - 1
                if ny >= 0 and not visited[ny][cx] and px[cx, ny] != 0:
                    visited[ny][cx] = 1
                    q.append((cx, ny))
                ny = cy + 1
                if ny < SH and not visited[ny][cx] and px[cx, ny] != 0:
                    visited[ny][cx] = 1
                    q.append((cx, ny))

            w = (maxx - minx + 1)
            h = (maxy - miny + 1)
            area = int(w * h)
            if area <= 0:
                continue
            density = float(count) / float(area)
            # Store bbox in small-image coords as [x0,y0,x1,y1) (exclusive max).
            comps.append((area, density, (minx, miny, maxx + 1, maxy + 1)))

    # Filter candidates.
    min_area = max(80, int(0.0012 * page_area))
    candidates: list[tuple[int, float, tuple[int, int, int, int]]] = []
    for area, density, (x0, y0, x1, y1) in comps:
        if area < min_area:
            continue
        if page_area > 0 and (float(area) / page_area) > 0.60:
            continue
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            continue
        # Discard extremely thin components (likely borders/lines).
        if (w >= 12 and h <= 2) or (h >= 12 and w <= 2):
            continue
        if w > 16 * h or h > 16 * w:
            continue
        # Screenshots often have scattered edges (low density) but are still
        # visually important. Lowering this cutoff improves recall; additional
        # size/shape filtering happens later.
        if density < 0.04:
            continue
        candidates.append((area, density, (x0, y0, x1, y1)))

    # Prefer larger regions.
    candidates.sort(key=lambda t: t[0], reverse=True)

    def _merge_boxes(
        boxes: list[tuple[int, int, int, int]],
        *,
        iou_thresh: float = 0.18,
        gap: int = 6,
    ) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for b in boxes:
            bx0, by0, bx1, by1 = b
            did_merge = False
            for i, a in enumerate(merged):
                ax0, ay0, ax1, ay1 = a
                # Expand by a small gap so near-touching regions merge.
                ax0g, ay0g, ax1g, ay1g = ax0 - gap, ay0 - gap, ax1 + gap, ay1 + gap
                inter_x0 = max(ax0g, bx0)
                inter_y0 = max(ay0g, by0)
                inter_x1 = min(ax1g, bx1)
                inter_y1 = min(ay1g, by1)
                if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
                    continue
                inter = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
                area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
                area_b = max(1, (bx1 - bx0) * (by1 - by0))
                union = area_a + area_b - inter
                iou = float(inter) / float(max(1, union))
                if iou >= iou_thresh or inter >= 0.45 * float(min(area_a, area_b)):
                    merged[i] = (
                        min(ax0, bx0),
                        min(ay0, by0),
                        max(ax1, bx1),
                        max(ay1, by1),
                    )
                    did_merge = True
                    break
            if not did_merge:
                merged.append((bx0, by0, bx1, by1))
        return merged

    # Convert candidate boxes from small coords to pt coords.
    boxes_small = [bbox for _, _, bbox in candidates[: max_regions * 3]]
    # Screenshots often yield multiple disjoint edge components (text blocks,
    # icons, UI chrome) that don't strictly overlap. Use a larger merge gap on
    # the downsampled grid so we can recover a single screenshot bbox.
    merge_gap_scale = float(merge_gap_scale)
    merge_gap_scale = max(0.02, min(0.25, merge_gap_scale))
    merge_gap = max(6, int(round(merge_gap_scale * float(min(SW, SH)))))
    boxes_small = _merge_boxes(boxes_small, gap=merge_gap)

    regions_pt: list[list[float]] = []
    for x0, y0, x1, y1 in boxes_small[:max_regions]:
        # Convert to pixel coordinates on full-size render.
        px0 = int(x0 * factor)
        py0 = int(y0 * factor)
        px1 = int(min(W, x1 * factor))
        py1 = int(min(H, y1 * factor))
        if px1 <= px0 or py1 <= py0:
            continue

        # Pad slightly to include soft shadows/anti-aliasing.
        pad = int(round(0.03 * float(min(px1 - px0, py1 - py0))))
        pad = max(3, min(24, pad))
        px0 = max(0, px0 - pad)
        py0 = max(0, py0 - pad)
        px1 = min(W, px1 + pad)
        py1 = min(H, py1 + pad)

        x0_pt = float(px0) / scale
        y0_pt = float(py0) / scale
        x1_pt = float(px1) / scale
        y1_pt = float(py1) / scale

        # Clamp to page bounds in pt.
        x0_pt = max(0.0, min(float(page_width_pt), x0_pt))
        y0_pt = max(0.0, min(float(page_height_pt), y0_pt))
        x1_pt = max(0.0, min(float(page_width_pt), x1_pt))
        y1_pt = max(0.0, min(float(page_height_pt), y1_pt))
        if x1_pt <= x0_pt or y1_pt <= y0_pt:
            continue

        # Skip near-full-page regions (usually background).
        area_pt = (x1_pt - x0_pt) * (y1_pt - y0_pt)
        if area_pt / max(1.0, float(page_width_pt) * float(page_height_pt)) > 0.80:
            continue

        regions_pt.append([x0_pt, y0_pt, x1_pt, y1_pt])

    # De-duplicate nearly identical bboxes.
    uniq: list[list[float]] = []
    for bb in regions_pt:
        x0, y0, x1, y1 = bb
        keep = True
        for ub in uniq:
            ux0, uy0, ux1, uy1 = ub
            if (
                abs(x0 - ux0) <= 2.0
                and abs(y0 - uy0) <= 2.0
                and abs(x1 - ux1) <= 2.0
                and abs(y1 - uy1) <= 2.0
            ):
                keep = False
                break
        if keep:
            uniq.append(bb)
    return uniq[:max_regions]


def _analyze_shape_crop(crop_path: Path) -> dict[str, Any]:
    """Return best-effort "image-likeness" stats for a rendered crop.

    This is a lightweight *visual* heuristic that helps answer:
    - does this crop look like a real screenshot/diagram/icon?
    - is it likely a text-only panel/strip?

    It intentionally avoids any extra model calls (VLM/LLM) so it stays cheap
    and works offline. The output is used as an internal quality signal for
    merging fragmented image regions.
    """

    try:
        from PIL import Image, ImageFilter
    except Exception:
        return {"confirmed": False, "score": 0.0}

    try:
        img = Image.open(crop_path).convert("L")
    except Exception:
        return {"confirmed": False, "score": 0.0}

    w, h = img.size
    if w < 18 or h < 18:
        return {"confirmed": False, "score": 0.0, "w": int(w), "h": int(h)}

    # Normalize size for stable thresholds.
    max_side = max(w, h)
    if max_side > 320:
        scale = 320.0 / float(max_side)
        w2 = max(16, int(round(float(w) * scale)))
        h2 = max(16, int(round(float(h) * scale)))
        img = img.resize((w2, h2))
        w, h = img.size

    edges = img.filter(ImageFilter.FIND_EDGES)
    bw = edges.point(lambda p: 255 if p > 34 else 0, "L")
    pix = bw.load()

    if pix is None or w <= 0 or h <= 0:
        return {"confirmed": False, "score": 0.0, "w": int(w), "h": int(h)}

    band = max(2, min(7, int(round(0.03 * float(min(w, h))))))

    def _edge_ratio_rect(x0: int, y0: int, x1: int, y1: int) -> float:
        x0 = max(0, min(x0, w))
        x1 = max(0, min(x1, w))
        y0 = max(0, min(y0, h))
        y1 = max(0, min(y1, h))
        if x1 <= x0 or y1 <= y0:
            return 0.0
        total = max(1, (x1 - x0) * (y1 - y0))
        on = 0
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                if pix[xx, yy] > 0:
                    on += 1
        return float(on) / float(total)

    top_r = _edge_ratio_rect(0, 0, w, band)
    bottom_r = _edge_ratio_rect(0, h - band, w, h)
    left_r = _edge_ratio_rect(0, 0, band, h)
    right_r = _edge_ratio_rect(w - band, 0, w, h)

    border_side_hits = sum(
        1 for r in (top_r, bottom_r, left_r, right_r) if r >= 0.06
    )

    inset = max(2 * band, int(round(0.10 * float(min(w, h)))))
    interior_r = _edge_ratio_rect(inset, inset, w - inset, h - inset)

    has_h_pair = top_r >= 0.07 and bottom_r >= 0.07
    has_v_pair = left_r >= 0.07 and right_r >= 0.07
    has_frame = has_h_pair or has_v_pair

    aspect = max(float(w) / max(1.0, float(h)), float(h) / max(1.0, float(w)))
    icon_like = aspect <= 1.8 and interior_r >= 0.075 and (w * h) >= 1200
    screenshot_like = (
        (w * h) >= 8500
        and aspect <= 3.8
        and interior_r >= 0.032
        and border_side_hits >= 1
    )

    confirmed = False
    if has_frame and border_side_hits >= 2 and interior_r >= 0.010:
        confirmed = True
    elif screenshot_like:
        confirmed = True
    elif icon_like and border_side_hits >= 1:
        confirmed = True

    # Soft score: in [0..1], higher means "more likely a real image crop".
    border_avg = (top_r + bottom_r + left_r + right_r) / 4.0
    border_strength = min(1.0, float(border_avg) / 0.10)
    interior_strength = min(1.0, float(interior_r) / 0.06)
    score = 0.55 * interior_strength + 0.35 * border_strength
    if has_frame:
        score += 0.08
    if screenshot_like:
        score += 0.08
    if icon_like:
        score += 0.05
    score = max(0.0, min(1.0, float(score)))

    return {
        "confirmed": bool(confirmed),
        "score": float(score),
        "w": int(w),
        "h": int(h),
        "aspect": float(aspect),
        "border_side_hits": int(border_side_hits),
        "top_r": float(top_r),
        "bottom_r": float(bottom_r),
        "left_r": float(left_r),
        "right_r": float(right_r),
        "interior_r": float(interior_r),
        "has_frame": bool(has_frame),
        "icon_like": bool(icon_like),
        "screenshot_like": bool(screenshot_like),
    }


def _is_shape_confirmed_crop(crop_path: Path) -> bool:
    """Best-effort check whether a crop looks like a real image/diagram region.

    We treat regions with clear rectangular edges and non-trivial interior
    structure as "confirmed image". This helps suppress OCR edits *inside*
    screenshots/diagrams while avoiding false positives on plain text blocks.
    """

    try:
        return bool(_analyze_shape_crop(crop_path).get("confirmed"))
    except Exception:
        return False


def _sample_pixmap_rgb(
    pix: Any,
    *,
    x_px: int,
    y_px: int,
) -> tuple[int, int, int]:
    x = max(0, min(int(x_px), int(pix.width) - 1))
    y = max(0, min(int(y_px), int(pix.height) - 1))

    n = int(getattr(pix, "n", 0) or 0)
    if n <= 0:
        return (255, 255, 255)
    samples = pix.samples
    idx = (y * int(pix.width) + x) * n
    if idx + 1 >= len(samples):
        return (255, 255, 255)

    if n == 1:
        v = samples[idx]
        return (v, v, v)
    if n >= 3 and idx + 2 < len(samples):
        return (samples[idx], samples[idx + 1], samples[idx + 2])
    v = samples[idx]
    return (v, v, v)


def _sample_bbox_background_rgb(
    pix: Any,
    *,
    bbox_pt: Any,
    page_height_pt: float,
    dpi: int,
) -> tuple[int, int, int]:
    """Best-effort background color sampling for a text bbox.

    Sampling the bbox center can hit foreground glyph pixels (dark text / white
    text), producing obvious masking artifacts. Instead sample just outside the
    bbox and average.
    """

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return (255, 255, 255)

    h = max(1.0, y1 - y0)
    pad_pt = max(1.0, min(3.0, 0.1 * h))

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    sample_pts = [
        (x0 - pad_pt, y0 - pad_pt),
        (x1 + pad_pt, y0 - pad_pt),
        (x0 - pad_pt, y1 + pad_pt),
        (x1 + pad_pt, y1 + pad_pt),
        (x0 - pad_pt, cy),
        (x1 + pad_pt, cy),
        (cx, y0 - pad_pt),
        (cx, y1 + pad_pt),
    ]

    colors: list[tuple[int, int, int]] = []
    for px_pt, py_pt in sample_pts:
        px, py = _pdf_pt_to_pix_px(
            float(px_pt),
            float(py_pt),
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        colors.append(_sample_pixmap_rgb(pix, x_px=px, y_px=py))

    if not colors:
        return (255, 255, 255)
    # Median is more robust than mean when one of the sample points hits a glyph
    # stroke or a nearby colorful element.
    rs = sorted(c[0] for c in colors)
    gs = sorted(c[1] for c in colors)
    bs = sorted(c[2] for c in colors)
    mid = len(rs) // 2
    r = int(rs[mid])
    g = int(gs[mid])
    b = int(bs[mid])
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _sample_bbox_text_rgb(
    pix: Any,
    *,
    bbox_pt: Any,
    page_height_pt: float,
    dpi: int,
    bg_rgb: tuple[int, int, int],
) -> tuple[int, int, int] | None:
    """Estimate text color inside a bbox by selecting high-contrast pixels."""

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return None

    x0p, y0p = _pdf_pt_to_pix_px(
        float(x0), float(y0), page_height_pt=page_height_pt, dpi=int(dpi)
    )
    x1p, y1p = _pdf_pt_to_pix_px(
        float(x1), float(y1), page_height_pt=page_height_pt, dpi=int(dpi)
    )
    left = max(0, min(int(x0p), int(x1p)))
    right = max(0, max(int(x0p), int(x1p)))
    top = max(0, min(int(y0p), int(y1p)))
    bottom = max(0, max(int(y0p), int(y1p)))

    width = max(0, right - left)
    height = max(0, bottom - top)
    if width < 2 or height < 2:
        return None

    max_samples = 1600
    area = max(1, width * height)
    step = max(1, int(round((float(area) / float(max_samples)) ** 0.5)))

    bg_luma = _rgb_luma(bg_rgb)
    candidates: list[tuple[float, tuple[int, int, int]]] = []
    for yp in range(top, bottom, step):
        for xp in range(left, right, step):
            rgb = _sample_pixmap_rgb(pix, x_px=int(xp), y_px=int(yp))
            luma = _rgb_luma(rgb)
            contrast = abs(float(luma) - float(bg_luma))
            if contrast >= 14.0:
                candidates.append((contrast, rgb))

    if len(candidates) < 6:
        return None

    candidates.sort(key=lambda row: row[0], reverse=True)
    top_k = max(6, int(round(0.25 * len(candidates))))
    selected = [rgb for _, rgb in candidates[:top_k]]
    rs = sorted(int(c[0]) for c in selected)
    gs = sorted(int(c[1]) for c in selected)
    bs = sorted(int(c[2]) for c in selected)
    mid = len(rs) // 2
    estimated = (int(rs[mid]), int(gs[mid]), int(bs[mid]))
    if _rgb_sq_distance(estimated, bg_rgb) < (24 * 24):
        return None
    return estimated


def _pdf_pt_to_pix_px(
    x_pt: float,
    y_pt: float,
    *,
    page_height_pt: float,
    dpi: int,
) -> tuple[int, int]:
    # IR coordinates and rendered pixmaps both use a top-left origin.
    x_px = x_pt * dpi / _PTS_PER_INCH
    y_px = y_pt * dpi / _PTS_PER_INCH
    return (int(round(x_px)), int(round(y_px)))


_PREVIEW_FONT_CACHE: dict[tuple[int, bool], Any] = {}


def _load_preview_font(*, size_px: int, prefer_cjk: bool) -> Any:
    from PIL import ImageFont

    key = (int(max(6, size_px)), bool(prefer_cjk))
    cached = _PREVIEW_FONT_CACHE.get(key)
    if cached is not None:
        return cached

    candidates: list[str] = []
    if prefer_cjk:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            ]
        )
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )

    for path in candidates:
        try:
            font = ImageFont.truetype(path, size=key[0])
            _PREVIEW_FONT_CACHE[key] = font
            return font
        except Exception:
            continue

    font = ImageFont.load_default()
    _PREVIEW_FONT_CACHE[key] = font
    return font


def _resolve_preview_image_path(
    *,
    image_path: Any,
    artifacts_dir: Path,
) -> Path | None:
    raw = str(image_path or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return None
    try:
        img_path = _as_path(raw)
    except Exception:
        return None
    if not img_path.is_absolute():
        candidate = artifacts_dir / img_path
        if candidate.exists():
            img_path = candidate
    if not img_path.exists() or not img_path.is_file():
        return None
    return img_path


def _bbox_pt_to_preview_px(
    bbox: Any,
    *,
    page_w_pt: float,
    page_h_pt: float,
    img_w_px: int,
    img_h_px: int,
) -> tuple[int, int, int, int] | None:
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return None
    if page_w_pt <= 0 or page_h_pt <= 0 or img_w_px <= 0 or img_h_px <= 0:
        return None
    sx = float(img_w_px) / float(page_w_pt)
    sy = float(img_h_px) / float(page_h_pt)
    x0p = max(0, min(int(round(x0 * sx)), int(img_w_px - 1)))
    y0p = max(0, min(int(round(y0 * sy)), int(img_h_px - 1)))
    x1p = max(0, min(int(round(x1 * sx)), int(img_w_px)))
    y1p = max(0, min(int(round(y1 * sy)), int(img_h_px)))
    if x1p <= x0p or y1p <= y0p:
        return None
    return (x0p, y0p, x1p, y1p)


def _export_final_preview_page_image(
    *,
    page: dict[str, Any],
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    source_pdf: Path,
    artifacts_dir: Path,
    dpi: int,
    scanned_image_region_crops: list[tuple[list[float], Path]] | None = None,
) -> None:
    """Export a visual approximation of the converted slide for tracking UI."""

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return

    preview_dir = artifacts_dir / "final_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    base_candidates = [
        artifacts_dir / "page_renders" / f"page-{page_index:04d}.mineru.clean.png",
        artifacts_dir / "page_renders" / f"page-{page_index:04d}.clean.png",
        artifacts_dir / "page_renders" / f"page-{page_index:04d}.png",
        artifacts_dir / "page_renders" / f"page-{page_index:04d}.mineru.png",
    ]
    base_path = next((p for p in base_candidates if p.exists()), None)

    if base_path is None and source_pdf.exists():
        try:
            base_path = preview_dir / f"page-{page_index:04d}.base.png"
            _render_pdf_page_png(
                source_pdf,
                page_index=page_index,
                dpi=int(dpi),
                out_path=base_path,
            )
        except Exception:
            base_path = None

    if base_path is None:
        return

    try:
        img = Image.open(base_path).convert("RGB")
    except Exception:
        return

    img_w, img_h = img.size
    if img_w <= 0 or img_h <= 0:
        return

    draw = ImageDraw.Draw(img)

    scanned_crop_rects: list[tuple[int, int, int, int]] = []
    for crop_info in scanned_image_region_crops or []:
        if not isinstance(crop_info, tuple) or len(crop_info) != 2:
            continue
        bbox_pt, _ = crop_info
        rect = _bbox_pt_to_preview_px(
            bbox_pt,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            img_w_px=img_w,
            img_h_px=img_h,
        )
        if rect is None:
            continue
        scanned_crop_rects.append(rect)

    is_scanned_page = not bool(page.get("has_text_layer"))
    baseline_ocr_h_pt: float | None = None
    if is_scanned_page:
        try:
            ocr_text_elements = [
                el
                for el in _iter_page_elements(page, type_name="text")
                if str(el.get("source") or "").strip().lower() == "ocr"
            ]
            if ocr_text_elements:
                baseline_ocr_h_pt = _estimate_baseline_ocr_line_height_pt(
                    ocr_text_elements=ocr_text_elements,
                    page_w_pt=float(page_w_pt),
                )
        except Exception:
            baseline_ocr_h_pt = None

    for el in _iter_page_elements(page, type_name="image"):
        # For scanned-page OCR IR, a full-page image element is often just the
        # original rendered background. Re-pasting it on top of a cleaned base
        # preview causes apparent "double text"/ghosting.
        if _is_near_full_page_bbox_pt(
            el.get("bbox_pt"), page_w_pt=page_w_pt, page_h_pt=page_h_pt
        ):
            continue

        rect = _bbox_pt_to_preview_px(
            el.get("bbox_pt"),
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            img_w_px=img_w,
            img_h_px=img_h,
        )
        img_path = _resolve_preview_image_path(
            image_path=el.get("image_path"), artifacts_dir=artifacts_dir
        )
        if rect is None or img_path is None:
            continue
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            continue
        try:
            patch = Image.open(img_path).convert("RGB").resize(
                (max(1, x1 - x0), max(1, y1 - y0))
            )
            img.paste(patch, (x0, y0))
        except Exception:
            continue

    # Scanned-page overlay crops are not always present in IR `image` elements.
    # Include them explicitly in preview so users can visually verify image
    # recovery/parity with PPT composition.
    for crop_info in scanned_image_region_crops or []:
        if not isinstance(crop_info, tuple) or len(crop_info) != 2:
            continue
        bbox_pt, crop_path = crop_info
        rect = _bbox_pt_to_preview_px(
            bbox_pt,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            img_w_px=img_w,
            img_h_px=img_h,
        )
        if rect is None:
            continue
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            continue
        try:
            crop = Image.open(crop_path).convert("RGBA").resize(
                (max(1, x1 - x0), max(1, y1 - y0))
            )
            img.paste(crop.convert("RGB"), (x0, y0), crop)
        except Exception:
            continue

    for el in _iter_page_elements(page, type_name="text"):
        rect = _bbox_pt_to_preview_px(
            el.get("bbox_pt"),
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            img_w_px=img_w,
            img_h_px=img_h,
        )
        if rect is None:
            continue
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            continue

        raw_text = str(el.get("text") or "")
        source_id = str(el.get("source") or "").strip().lower()
        is_scanned_ocr = bool(is_scanned_page and source_id == "ocr")
        is_layout_text = source_id in {"mineru"} or is_scanned_ocr

        # When we overlay a scanned crop (screenshot/diagram), we also suppress
        # OCR text inside that crop in the PPT composition. Mirror that here so
        # the preview doesn't show confusing "extra" text on top of images.
        if scanned_crop_rects and source_id == "ocr":
            t_area = max(1.0, float((x1 - x0) * (y1 - y0)))
            tcx = (float(x0) + float(x1)) / 2.0
            tcy = (float(y0) + float(y1)) / 2.0
            suppressed = False
            for ix0, iy0, ix1, iy1 in scanned_crop_rects:
                inter_x0 = max(int(x0), int(ix0))
                inter_y0 = max(int(y0), int(iy0))
                inter_x1 = min(int(x1), int(ix1))
                inter_y1 = min(int(y1), int(iy1))
                if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
                    continue
                inter = float((inter_x1 - inter_x0) * (inter_y1 - inter_y0))
                overlap_ratio = inter / t_area
                center_inside = (
                    tcx >= float(ix0)
                    and tcx <= float(ix1)
                    and tcy >= float(iy0)
                    and tcy <= float(iy1)
                )
                if overlap_ratio >= 0.72 or (center_inside and overlap_ratio >= 0.25):
                    suppressed = True
                    break
            if suppressed:
                continue

        if is_layout_text:
            text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            text = "\n".join([line.strip() for line in text.split("\n") if line.strip()]).strip()
        else:
            text = raw_text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
        if not text:
            continue

        if is_scanned_ocr and baseline_ocr_h_pt is not None:
            try:
                x0_pt, y0_pt, x1_pt, y1_pt = _coerce_bbox_pt(el.get("bbox_pt"))
            except Exception:
                continue
            bbox_w_pt = max(1.0, float(x1_pt - x0_pt))
            bbox_h_pt = max(1.0, float(y1_pt - y0_pt))
            is_heading = (
                y0_pt <= 0.22 * float(page_h_pt)
                and bbox_h_pt >= 1.6 * float(baseline_ocr_h_pt)
                and len(text) <= 40
            )
            text_to_render, font_size_pt, _ = _fit_ocr_text_style(
                text=text,
                bbox_w_pt=bbox_w_pt,
                bbox_h_pt=bbox_h_pt,
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                is_heading=bool(is_heading),
            )
        else:
            bbox_w_pt = max(1.0, float(x1 - x0) * _PTS_PER_INCH / float(dpi))
            bbox_h_pt = max(1.0, float(y1 - y0) * _PTS_PER_INCH / float(dpi))
            if is_layout_text:
                font_size_pt = _fit_font_size_pt(
                    text,
                    bbox_w_pt=bbox_w_pt,
                    bbox_h_pt=bbox_h_pt,
                    wrap=True,
                    min_pt=6.0,
                    max_pt=min(24.0, max(9.0, 0.60 * bbox_h_pt)),
                    width_fit_ratio=0.98,
                    height_fit_ratio=0.95,
                )
                text_to_render = _wrap_text_to_width(
                    text,
                    max_width_pt=max(1.0, 0.98 * bbox_w_pt),
                    font_size_pt=float(font_size_pt),
                )
                text_to_render = text_to_render if text_to_render.strip() else text
            else:
                font_size_pt = _infer_font_size_pt(el, bbox_h_pt=bbox_h_pt)
                text_to_render = text

        size_px = int(round(max(7.0, float(font_size_pt)) * float(dpi) / _PTS_PER_INCH))
        font = _load_preview_font(size_px=size_px, prefer_cjk=_contains_cjk(text_to_render))
        rgb = _hex_to_rgb(el.get("color")) or (0, 0, 0)
        # For scanned OCR we already insert explicit line breaks when needed.
        # Additional PIL line spacing can drift from PPT rendering.
        spacing = 0 if is_scanned_ocr else max(1, int(round(0.18 * float(size_px))))

        try:
            # Draw into a clipped patch so preview text cannot overflow across
            # neighboring cards/areas, matching PPT textbox boundaries better.
            box_w = max(1, int(x1 - x0))
            box_h = max(1, int(y1 - y0))
            patch = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            patch_draw = ImageDraw.Draw(patch)
            patch_draw.multiline_text(
                (0, 0),
                text_to_render,
                fill=(int(rgb[0]), int(rgb[1]), int(rgb[2]), 255),
                font=font,
                spacing=spacing,
            )
            img.paste(patch.convert("RGB"), (int(x0), int(y0)), patch)
        except Exception:
            continue

    out_path = preview_dir / f"page-{page_index:04d}.final.png"
    try:
        img.save(out_path)
    except Exception:
        return


def _erase_regions_in_render_image(
    render_path: Path,
    *,
    out_path: Path,
    erase_bboxes_pt: list[list[float]],
    protect_bboxes_pt: list[list[float]] | None = None,
    page_height_pt: float,
    dpi: int,
    text_erase_mode: str = "fill",
) -> Path:
    """Erase bboxes directly in the rendered background image.

    This avoids PPT rectangle masks (which can look like color blocks) and
    produces a cleaner editable overlay: erase first, then place text boxes.
    """

    if not erase_bboxes_pt:
        return render_path

    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter
    except Exception:
        return render_path

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return render_path

    W, H = img.size
    if W <= 0 or H <= 0:
        return render_path

    def _bbox_pt_to_rect_px(
        bb: list[float], *, pad: int = 0
    ) -> tuple[int, int, int, int] | None:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            return None
        x0p, y0p = _pdf_pt_to_pix_px(
            x0, y0, page_height_pt=page_height_pt, dpi=int(dpi)
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1, y1, page_height_pt=page_height_pt, dpi=int(dpi)
        )
        x0p = max(0, min(int(W - 1), int(x0p) - int(pad)))
        y0p = max(0, min(int(H - 1), int(y0p) - int(pad)))
        x1p = max(0, min(int(W), int(x1p) + int(pad)))
        y1p = max(0, min(int(H), int(y1p) + int(pad)))
        if x1p <= x0p or y1p <= y0p:
            return None
        return (x0p, y0p, x1p, y1p)

    rects: list[tuple[int, int, int, int]] = []
    core_rects: list[tuple[int, int, int, int]] = []
    for bb in erase_bboxes_pt:
        core = _bbox_pt_to_rect_px(bb, pad=0)
        if core is None:
            continue
        expanded = _bbox_pt_to_rect_px(bb, pad=1)
        if expanded is None:
            expanded = core
        rects.append(expanded)
        core_rects.append(core)

    if not rects:
        return render_path

    protect_rects: list[tuple[int, int, int, int]] = []
    for bb in protect_bboxes_pt or []:
        rect = _bbox_pt_to_rect_px(bb, pad=2)
        if rect is not None:
            protect_rects.append(rect)

    erase_mode = str(text_erase_mode or "smart").strip().lower()
    if erase_mode not in {"smart", "fill"}:
        erase_mode = "smart"

    if erase_mode == "fill":
        dilate_size = 5 if max(W, H) >= 1600 else 3

        def _point_in_protect(x: int, y: int) -> bool:
            for px0, py0, px1, py1 in protect_rects:
                if px0 <= x < px1 and py0 <= y < py1:
                    return True
            return False

        def _median_color(values: list[tuple[int, int, int]]) -> tuple[int, int, int]:
            if not values:
                return (255, 255, 255)
            rs = sorted(v[0] for v in values)
            gs = sorted(v[1] for v in values)
            bs = sorted(v[2] for v in values)
            mid = len(values) // 2
            return (int(rs[mid]), int(gs[mid]), int(bs[mid]))

        def _estimate_fill_color(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int]:
            h = max(1, int(y1 - y0))
            w = max(1, int(x1 - x0))
            # Keep sampling close to the text bbox; too-large pads can pull colors
            # from unrelated nearby cards/charts and create obvious fill blocks.
            pad = max(1, min(8, int(round(0.28 * float(h)))))

            sample_points: list[tuple[int, int]] = []
            x_fracs = [0.15, 0.35, 0.50, 0.65, 0.85]
            y_fracs = [0.15, 0.35, 0.50, 0.65, 0.85]
            for frac in x_fracs:
                px = int(round(x0 + frac * float(w)))
                sample_points.append((px, y0 - pad))
                sample_points.append((px, y1 + pad))
            for frac in y_fracs:
                py = int(round(y0 + frac * float(h)))
                sample_points.append((x0 - pad, py))
                sample_points.append((x1 + pad, py))

            sample_points.extend(
                [
                    (x0 - pad, y0 - pad),
                    (x1 + pad, y0 - pad),
                    (x0 - pad, y1 + pad),
                    (x1 + pad, y1 + pad),
                ]
            )

            values: list[tuple[int, int, int]] = []
            for sx, sy in sample_points:
                cx = max(0, min(W - 1, int(sx)))
                cy = max(0, min(H - 1, int(sy)))
                if _point_in_protect(cx, cy):
                    continue
                values.append(tuple(int(c) for c in img.getpixel((cx, cy))[:3]))

            if not values:
                values.append(tuple(int(c) for c in img.getpixel((max(0, min(W - 1, x0)), max(0, min(H - 1, y0))))[:3]))
            return _median_color(values)

        try:
            fill_img = img.copy()
            protect_mask_img = Image.new("L", (W, H), 0)
            if protect_rects:
                protect_draw = ImageDraw.Draw(protect_mask_img)
                for x0, y0, x1, y1 in protect_rects:
                    protect_draw.rectangle(
                        [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
                    )

            for x0, y0, x1, y1 in rects:
                color = _estimate_fill_color(x0, y0, x1, y1)
                rect_mask = Image.new("L", (W, H), 0)
                rect_draw = ImageDraw.Draw(rect_mask)
                rect_draw.rectangle(
                    [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
                )
                try:
                    # Expand mask by ~1px to cover anti-aliased text edges.
                    rect_mask = rect_mask.filter(ImageFilter.MaxFilter(dilate_size))
                except Exception:
                    pass
                if protect_rects:
                    rect_mask = ImageChops.subtract(rect_mask, protect_mask_img)
                    if rect_mask.getbbox() is None:
                        continue
                fill_img.paste(color, (0, 0, W, H), rect_mask)

            _ensure_parent_dir(out_path)
            fill_img.save(out_path)
            return out_path
        except Exception:
            return render_path

    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None  # type: ignore

    if np is None:
        # Degraded mode when numpy is unavailable (e.g. partially installed
        # local environments). We still erase text using PIL masks so we don't
        # fall back to "no erase" overlap behavior.
        blur_radius = 2.2 if max(W, H) >= 1600 else 1.6
        strong_blur_radius = min(34.0, max(18.0, 7.5 * float(blur_radius)))
        try:
            bg_img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            bg_strong_img = img.filter(
                ImageFilter.GaussianBlur(radius=strong_blur_radius)
            )
        except Exception:
            bg_img = img.copy()
            bg_strong_img = img.copy()

        remove_mask = Image.new("L", (W, H), 0)
        fallback_mask = Image.new("L", (W, H), 0)
        protect_mask_img = Image.new("L", (W, H), 0)
        draw_remove = ImageDraw.Draw(remove_mask)
        draw_fallback = ImageDraw.Draw(fallback_mask)
        draw_protect = ImageDraw.Draw(protect_mask_img)

        for x0, y0, x1, y1 in rects:
            draw_remove.rectangle(
                [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
            )
        for x0, y0, x1, y1 in core_rects:
            draw_fallback.rectangle(
                [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
            )
        for x0, y0, x1, y1 in protect_rects:
            draw_protect.rectangle(
                [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
            )

        try:
            dilate_size = 5 if max(W, H) >= 1600 else 3
            remove_mask = remove_mask.filter(ImageFilter.MaxFilter(dilate_size))
            fallback_mask = fallback_mask.filter(ImageFilter.MaxFilter(dilate_size))
        except Exception:
            pass

        if protect_rects:
            try:
                remove_mask = ImageChops.subtract(remove_mask, protect_mask_img)
                fallback_mask = ImageChops.subtract(fallback_mask, protect_mask_img)
            except Exception:
                pass

        out_img = Image.composite(bg_img, img, remove_mask)
        out_img = Image.composite(bg_strong_img, out_img, fallback_mask)
        try:
            _ensure_parent_dir(out_path)
            out_img.save(out_path)
            return out_path
        except Exception:
            return render_path

    arr = np.array(img, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return render_path

    # Smooth background estimate used for pixel-level replacement. This avoids
    # rectangle color blocks and is visually closer to "text removed".
    try:
        blur_radius = 2.2 if max(W, H) >= 1600 else 1.6
        bg_arr = np.array(
            img.filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.uint8
        )
        strong_blur_radius = min(34.0, max(18.0, 7.5 * float(blur_radius)))
        bg_strong_arr = np.array(
            img.filter(ImageFilter.GaussianBlur(radius=strong_blur_radius)),
            dtype=np.uint8,
        )
    except Exception:
        bg_arr = arr.copy()
        bg_strong_arr = arr.copy()

    # Luma map from the *original* render; detection should not depend on
    # sequential edits to nearby boxes.
    gray = (
        0.299 * arr[:, :, 0].astype(np.float32)
        + 0.587 * arr[:, :, 1].astype(np.float32)
        + 0.114 * arr[:, :, 2].astype(np.float32)
    )

    protect_mask = np.zeros((H, W), dtype=bool)
    for x0p, y0p, x1p, y1p in protect_rects:
        protect_mask[y0p:y1p, x0p:x1p] = True

    out = arr.copy()
    rects.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    remove_mask = np.zeros((H, W), dtype=bool)
    fallback_mask = np.zeros((H, W), dtype=bool)
    remove_color_mask = np.zeros((H, W), dtype=bool)
    remove_color_map = np.zeros((H, W, 3), dtype=np.uint8)

    def _dilate_mask(mask: Any, radius: int = 1) -> Any:
        if radius <= 0:
            return mask
        hh, ww = mask.shape
        pad = int(radius)
        src = np.pad(
            mask, ((pad, pad), (pad, pad)), mode="constant", constant_values=False
        )
        dil = np.zeros_like(mask, dtype=bool)
        for dy in range(0, 2 * pad + 1):
            y_slice = slice(dy, dy + hh)
            for dx in range(0, 2 * pad + 1):
                dil |= src[y_slice, dx : dx + ww]
        return dil

    def _median_ring_rgb(
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> tuple[int, int, int]:
        if x1 <= x0 or y1 <= y0:
            return (255, 255, 255)

        h = max(1, int(y1 - y0))
        pad = max(2, min(12, int(round(0.45 * float(h)))))
        rx0 = max(0, x0 - pad)
        ry0 = max(0, y0 - pad)
        rx1 = min(W, x1 + pad)
        ry1 = min(H, y1 + pad)
        if rx1 <= rx0 or ry1 <= ry0:
            return (255, 255, 255)

        ring = np.ones((ry1 - ry0, rx1 - rx0), dtype=bool)
        ix0 = max(0, x0 - rx0)
        iy0 = max(0, y0 - ry0)
        ix1 = min(ring.shape[1], x1 - rx0)
        iy1 = min(ring.shape[0], y1 - ry0)
        ring[iy0:iy1, ix0:ix1] = False

        sub_protect = protect_mask[ry0:ry1, rx0:rx1]
        if sub_protect.any():
            ring &= ~sub_protect

        ring_pixels = arr[ry0:ry1, rx0:rx1][ring]
        if ring_pixels.size <= 0:
            # Fallback: median of the local strong-blur patch.
            sub_blur = bg_strong_arr[y0:y1, x0:x1]
            if sub_blur.size <= 0:
                return (255, 255, 255)
            med = np.median(sub_blur.reshape(-1, 3), axis=0)
        else:
            med = np.median(ring_pixels.reshape(-1, 3), axis=0)

        return (
            int(max(0, min(255, round(float(med[0]))))),
            int(max(0, min(255, round(float(med[1]))))),
            int(max(0, min(255, round(float(med[2]))))),
        )

    for x0, y0, x1, y1 in rects:
        w = max(1, int(x1 - x0))
        h = max(1, int(y1 - y0))

        # Expand mostly in X so we can remove missed glyph tails in the same line
        # without crossing to unrelated rows.
        grow_x = max(2, min(18, int(round(0.55 * float(h)))))
        grow_y = max(1, min(4, int(round(0.18 * float(h)))))
        ex0 = max(0, x0 - grow_x)
        ey0 = max(0, y0 - grow_y)
        ex1 = min(W, x1 + grow_x)
        ey1 = min(H, y1 + grow_y)
        if ex1 <= ex0 or ey1 <= ey0:
            continue

        sub_gray = gray[ey0:ey1, ex0:ex1]
        sub_protect = protect_mask[ey0:ey1, ex0:ex1]

        ix0 = max(0, x0 - ex0)
        iy0 = max(0, y0 - ey0)
        ix1 = min(sub_gray.shape[1], x1 - ex0)
        iy1 = min(sub_gray.shape[0], y1 - ey0)
        if ix1 <= ix0 or iy1 <= iy0:
            continue

        # Local background estimate from the ring around the core box.
        ring_mask = np.ones_like(sub_gray, dtype=bool)
        ring_mask[iy0:iy1, ix0:ix1] = False
        if sub_protect.any():
            ring_mask &= ~sub_protect
        ring_vals = sub_gray[ring_mask]
        local_bg = float(np.median(ring_vals)) if ring_vals.size > 0 else float(
            np.median(sub_gray)
        )

        # Text-like pixel mask (dark on light, and bright on dark backgrounds).
        delta_dark = max(8.0, min(26.0, 0.14 * local_bg + 4.0))
        delta_bright = max(9.0, min(30.0, 0.13 * (255.0 - local_bg) + 6.0))
        dark_mask = sub_gray <= (local_bg - delta_dark)
        if local_bg < 125.0:
            bright_mask = sub_gray >= (local_bg + delta_bright)
            text_like = dark_mask | bright_mask
        else:
            text_like = dark_mask

        # Constrain to a near-line band to avoid touching unrelated content.
        band_pad = max(0, min(2, int(round(0.10 * float(h)))))
        by0 = max(0, iy0 - band_pad)
        by1 = min(sub_gray.shape[0], iy1 + band_pad)
        band_mask = np.zeros_like(sub_gray, dtype=bool)
        band_mask[by0:by1, :] = True

        m = text_like & band_mask & (~sub_protect)

        # If the mask is unexpectedly huge, tighten threshold for stability.
        band_area = max(1, int(np.count_nonzero(band_mask & (~sub_protect))))
        if (int(np.count_nonzero(m)) / float(band_area)) > 0.42:
            stricter = max(10.0, delta_dark + 5.0)
            m = (sub_gray <= (local_bg - stricter)) & band_mask & (~sub_protect)

        # Include anti-aliased fringes while staying around text-like pixels.
        near_delta = max(4.0, min(14.0, 0.55 * delta_dark))
        near_mask = (np.abs(sub_gray - local_bg) >= near_delta) & band_mask
        m = (m | (_dilate_mask(m, radius=1) & near_mask)) & (~sub_protect)

        core = np.zeros_like(sub_gray, dtype=bool)
        core[iy0:iy1, ix0:ix1] = True
        core &= ~sub_protect
        core_pixels = int(np.count_nonzero(core))
        masked_pixels = int(np.count_nonzero(m))

        # If pixel mask misses too much of the OCR bbox, force a fallback wipe on
        # the bbox core. This prevents the "no erase -> text overlap" failure mode.
        need_fallback = False
        if masked_pixels <= 0:
            need_fallback = True
        elif core_pixels > 0 and (masked_pixels / float(core_pixels)) < 0.08:
            need_fallback = True

        if masked_pixels > 0:
            remove_mask[ey0:ey1, ex0:ex1] |= m
            fr, fg, fb = _median_ring_rgb(x0, y0, x1, y1)
            sub_color_map = remove_color_map[ey0:ey1, ex0:ex1]
            sub_color_map[m] = (fr, fg, fb)
            remove_color_map[ey0:ey1, ex0:ex1] = sub_color_map
            remove_color_mask[ey0:ey1, ex0:ex1] |= m
        if need_fallback and core_pixels > 0:
            fallback_mask[ey0:ey1, ex0:ex1] |= core

    if np.any(remove_mask) or np.any(fallback_mask):
        # A tiny dilation better covers anti-aliased fringes.
        remove_mask = _dilate_mask(remove_mask, radius=1)
        fallback_mask = _dilate_mask(fallback_mask, radius=1)
        remove_mask &= ~protect_mask
        fallback_mask &= ~protect_mask
        fallback_only = fallback_mask & (~remove_mask)

        # Prefer local ring-color replacement to avoid long blur streaks.
        fill_remove_mask = remove_mask & remove_color_mask
        if np.any(fill_remove_mask):
            out[fill_remove_mask] = remove_color_map[fill_remove_mask]

        residual_remove_mask = remove_mask & (~remove_color_mask)
        if np.any(residual_remove_mask):
            out[residual_remove_mask] = bg_arr[residual_remove_mask]

        if np.any(fallback_only):
            out[fallback_only] = bg_arr[fallback_only]

    # Second pass: if a core OCR box changed too little, force a stronger wipe.
    # This specifically addresses "old text still visible under new text".
    unresolved_mask = np.zeros((H, W), dtype=bool)
    try:
        diff_changed = (
            np.abs(out.astype(np.int16) - arr.astype(np.int16)).sum(axis=2) >= 8
        )
        for x0, y0, x1, y1 in core_rects:
            sub_protect = protect_mask[y0:y1, x0:x1]
            eligible = ~sub_protect
            eligible_px = int(np.count_nonzero(eligible))
            if eligible_px <= 0:
                continue
            changed_px = int(np.count_nonzero(diff_changed[y0:y1, x0:x1] & eligible))
            # Require a fairly high changed ratio in the OCR core box. If too
            # little changed, we still risk visible old glyphs under new text.
            if (changed_px / float(eligible_px)) < 0.72:
                unresolved_mask[y0:y1, x0:x1] |= eligible
    except Exception:
        unresolved_mask = np.zeros((H, W), dtype=bool)

    if np.any(unresolved_mask):
        unresolved_mask = _dilate_mask(unresolved_mask, radius=1)
        unresolved_mask &= ~protect_mask
        out[unresolved_mask] = bg_arr[unresolved_mask]

    # Local final touch: only repaint OCR core pixels that still look like
    # high-contrast glyph strokes, and keep image-protected areas untouched.
    if core_rects:
        final_force_mask = np.zeros((H, W), dtype=bool)
        for x0, y0, x1, y1 in core_rects:
            if x1 <= x0 or y1 <= y0:
                continue
            sub_protect = protect_mask[y0:y1, x0:x1]
            if sub_protect.shape[0] <= 0 or sub_protect.shape[1] <= 0:
                continue

            sub_gray = gray[y0:y1, x0:x1]
            sub_out = out[y0:y1, x0:x1]
            out_luma = (
                0.299 * sub_out[:, :, 0].astype(np.float32)
                + 0.587 * sub_out[:, :, 1].astype(np.float32)
                + 0.114 * sub_out[:, :, 2].astype(np.float32)
            )
            residual = np.abs(sub_gray - out_luma)
            # Repaint only pixels that still differ notably from the surrounding
            # smoothed background estimate (likely residual old glyph strokes).
            local_mask = (residual >= 10.0) & (~sub_protect)
            if not np.any(local_mask):
                continue
            sub_force = final_force_mask[y0:y1, x0:x1]
            sub_force |= local_mask
            final_force_mask[y0:y1, x0:x1] = sub_force

        if np.any(final_force_mask):
            final_force_mask = _dilate_mask(final_force_mask, radius=1)
            final_force_mask &= ~protect_mask
            out[final_force_mask] = bg_arr[final_force_mask]

    # Avoid an additional whole-core repaint pass here. It can create
    # visible blur bands on light templates when OCR boxes are slightly wide.

    try:
        out_img = Image.fromarray(out.astype(np.uint8), mode="RGB")
        _ensure_parent_dir(out_path)
        out_img.save(out_path)
        return out_path
    except Exception:
        return render_path


@dataclass(frozen=True)
class _ScannedImageRegionInfo:
    bbox_pt: list[float]
    suppress_bbox_pt: list[float]
    crop_path: Path
    shape_confirmed: bool
    background_removed: bool = False


def _bbox_intersection_area_pt(a: list[float], b: list[float]) -> float:
    try:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)
    except Exception:
        return 0.0
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return float((ix1 - ix0) * (iy1 - iy0))


def _bbox_iou_pt(a: list[float], b: list[float]) -> float:
    inter = _bbox_intersection_area_pt(a, b)
    if inter <= 0.0:
        return 0.0
    try:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)
    except Exception:
        return 0.0
    a_area = max(1.0, float((ax1 - ax0) * (ay1 - ay0)))
    b_area = max(1.0, float((bx1 - bx0) * (by1 - by0)))
    return float(inter) / max(1.0, float(a_area + b_area - inter))


def _compact_text_length(text: str) -> int:
    return len("".join(ch for ch in str(text or "") if not ch.isspace()))


def _estimate_baseline_ocr_line_height_pt(
    *,
    ocr_text_elements: list[dict[str, Any]],
    page_w_pt: float,
) -> float:
    """Estimate a "typical" OCR line height (pt) on scanned pages.

    Many scanned-slide OCR engines also detect lots of tiny UI text inside
    screenshots/diagrams. Using a raw median/low-quantile can be skewed toward
    those tiny boxes, which then breaks downstream heuristics (wrap decision,
    image-region detection, dedupe thresholds).

    We therefore:
    - filter invalid/extreme boxes
    - focus on the *widest* OCR lines (more likely slide body text)
    - compute a width-weighted upper-median (slightly biased toward larger text)
    """

    samples: list[tuple[float, float]] = []  # (height_pt, width_ratio)
    width_pt = max(1.0, float(page_w_pt))

    for el in ocr_text_elements:
        if not isinstance(el, dict):
            continue
        bbox_pt = el.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        w = max(0.0, float(x1 - x0))
        h = max(0.0, float(y1 - y0))
        if w <= 0.0 or h <= 0.0:
            continue
        # Filter extreme outliers.
        if h < 4.5 or h > 96.0:
            continue
        width_ratio = w / width_pt
        samples.append((float(h), float(width_ratio)))

    if not samples:
        return 12.0

    # Use only the widest OCR lines to avoid being skewed by many tiny UI
    # elements inside screenshots. For small sample sizes keep all.
    samples.sort(key=lambda t: float(t[1]), reverse=True)
    if len(samples) > 24:
        k = max(12, int(round(0.25 * float(len(samples)))))
        k = max(12, min(int(k), len(samples)))
        samples = samples[:k]

    # Compute a width-weighted quantile on heights. Squaring width_ratio makes
    # narrow UI lines contribute much less even when they are numerous.
    weighted: list[tuple[float, float]] = []
    for h, width_ratio in samples:
        wr = max(0.0, min(1.0, float(width_ratio)))
        weight = max(1e-4, float(wr) * float(wr))
        weighted.append((float(h), float(weight)))

    weighted.sort(key=lambda t: float(t[0]))
    total_w = sum(float(w) for _, w in weighted) or 1.0
    target = 0.60 * total_w
    acc = 0.0
    baseline = float(weighted[len(weighted) // 2][0])
    for h, w in weighted:
        acc += float(w)
        if acc >= target:
            baseline = float(h)
            break

    return max(6.0, min(48.0, float(baseline)))


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
    cjk = sum(1 for ch in raw if "一" <= ch <= "鿿")
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


def _prefer_wrap_for_ocr_text(
    *,
    text: str,
    bbox_w_pt: float,
    bbox_h_pt: float,
    baseline_ocr_h_pt: float,
) -> bool:
    """Heuristic wrap decision for scanned OCR text.

    The goal is to be robust across pages/models instead of relying on a fixed
    threshold: estimate both width and likely line count from geometry/text.
    """

    compact_len = _compact_text_length(text)
    if compact_len <= 0:
        return False
    if "\n" in text:
        return True

    w = max(1.0, float(bbox_w_pt))
    h = max(1.0, float(bbox_h_pt))
    baseline = max(4.0, float(baseline_ocr_h_pt))

    # Very line-like boxes generally should not wrap.
    #
    # Many OCR engines return slightly padded bboxes (h ~ 1.2-1.4x baseline)
    # even for single visual lines. Treat those as single-line and prefer
    # shrinking font size (non-wrap) over inserting synthetic line breaks,
    # which often causes "wrong wrap" reports from users.
    # OCR bbox heights are often padded (especially for CJK + punctuation).
    # If we are not clearly multi-line, prefer *no wrap* and rely on font-size
    # fitting + right-side slack to avoid spurious line breaks like
    # "标题（Title）\n：".
    # NOTE: Some OCR backends (notably PaddleOCR-VL doc_parser) can emit
    # paragraph-like bboxes that are only ~1.4-1.6x the typical line height.
    # Treating those as "single line" makes the font fitter shrink text into
    # illegible tiny sizes. Keep the single-line guard stricter so we still
    # wrap these moderate-height blocks.
    if h <= max(1.45 * baseline, 10.5) and compact_len <= 120:
        return False

    width_pressure = float(compact_len) / max(1.0, w)
    # Height-based line estimation: use a slightly larger divisor to avoid
    # misclassifying single-line headers as 2-line blocks.
    est_lines_by_height = max(1, int(round(h / max(8.0, 1.10 * baseline))))

    if est_lines_by_height >= 2:
        return True

    # Only use width-pressure-based wrapping when the bbox is not line-like.
    # For near-single-line boxes, it's more robust to keep one line and let
    # font fitting shrink the size a bit, rather than forcing a wrap that may
    # not match the original slide.
    if h >= (1.35 * baseline):
        if _contains_cjk(text):
            if compact_len >= 18 and width_pressure >= 0.090:
                return True
            if compact_len >= 28 and width_pressure >= 0.075:
                return True
        else:
            if compact_len >= 22 and width_pressure >= 0.080:
                return True
            if compact_len >= 36 and width_pressure >= 0.065:
                return True

    return False


def _fit_ocr_text_style(
    *,
    text: str,
    bbox_w_pt: float,
    bbox_h_pt: float,
    baseline_ocr_h_pt: float,
    is_heading: bool,
    wrap_override: bool | None = None,
) -> tuple[str, float, bool]:
    """Return (text_to_render, font_size_pt, wrap) for OCR text boxes.

    This mirrors the robust mineru fitting path and avoids fixed single-page
    constants.
    """

    normalized = _normalize_ocr_text_for_render(text)
    if not normalized:
        return ("", 6.0, False)

    # Headings are usually single-line unless explicit line breaks exist.
    if is_heading and ("\n" not in normalized):
        wrap = False
    elif "\n" in normalized:
        wrap = True
    elif wrap_override is not None:
        wrap = bool(wrap_override)
    else:
        wrap = _prefer_wrap_for_ocr_text(
            text=normalized,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            baseline_ocr_h_pt=baseline_ocr_h_pt,
        )

    min_pt = max(5.0, min(8.0, 0.52 * float(baseline_ocr_h_pt)))
    max_pt = min(
        84.0 if is_heading else 54.0,
        max(7.0, float(bbox_h_pt) * (0.98 if is_heading else 0.94)),
    )

    font_size_pt = _fit_font_size_pt(
        normalized,
        bbox_w_pt=max(1.0, 1.01 * float(bbox_w_pt)) if wrap else float(bbox_w_pt),
        bbox_h_pt=float(bbox_h_pt),
        wrap=bool(wrap),
        min_pt=float(min_pt),
        max_pt=float(max_pt),
        width_fit_ratio=1.02 if wrap else 1.00,
        height_fit_ratio=0.95 if wrap else 0.995,
    )

    text_to_render = normalized
    if wrap:
        for _ in range(14):
            candidate_text = _wrap_text_to_width(
                normalized,
                max_width_pt=max(1.0, 1.01 * float(bbox_w_pt)),
                font_size_pt=float(font_size_pt),
            )
            candidate_lines = [line for line in candidate_text.splitlines() if line.strip()]
            if not candidate_lines:
                candidate_lines = [normalized]
                candidate_text = normalized
            line_height = 1.18 if _contains_cjk(normalized) else 1.15
            total_h = float(len(candidate_lines)) * float(font_size_pt) * line_height
            if total_h <= (0.985 * float(bbox_h_pt)):
                text_to_render = candidate_text
                break
            font_size_pt = max(float(min_pt), float(font_size_pt) - 0.32)
        else:
            text_to_render = candidate_text if candidate_text else normalized

    return (text_to_render, float(font_size_pt), bool(wrap))


def _try_make_crop_background_transparent(crop_path: Path) -> bool:
    """Best-effort background removal for icon-like crops.

    We estimate the dominant border color, then flood-fill similar colors from
    image edges as background and convert them to transparent alpha.
    """

    try:
        from PIL import Image, ImageFilter
    except Exception:
        return False

    try:
        img = Image.open(crop_path).convert("RGBA")
    except Exception:
        return False

    w, h = img.size
    if w < 18 or h < 18:
        return False

    band = max(1, min(6, int(round(0.045 * float(min(w, h))))))
    pix = img.load()
    if pix is None:
        return False

    border_rgb: list[tuple[int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if x < band or x >= (w - band) or y < band or y >= (h - band):
                r, g, b, _ = pix[x, y]
                border_rgb.append((int(r), int(g), int(b)))
    if len(border_rgb) < 12:
        return False

    def _median(vals: list[int]) -> int:
        if not vals:
            return 0
        s = sorted(vals)
        return int(s[len(s) // 2])

    med_r = _median([c[0] for c in border_rgb])
    med_g = _median([c[1] for c in border_rgb])
    med_b = _median([c[2] for c in border_rgb])

    def _dist_l1(rgb: tuple[int, int, int]) -> int:
        return (
            abs(int(rgb[0]) - med_r)
            + abs(int(rgb[1]) - med_g)
            + abs(int(rgb[2]) - med_b)
        )

    border_d = sorted(_dist_l1(c) for c in border_rgb)
    p90_idx = max(0, min(len(border_d) - 1, int(round(0.90 * (len(border_d) - 1)))))
    p90 = int(border_d[p90_idx])
    # Adaptive threshold; avoid aggressive removal on textured/screenshot-like crops.
    dist_thresh = max(14, min(72, int(round(1.35 * float(p90) + 8.0))))

    bg_candidate = [[False] * w for _ in range(h)]
    for y in range(h):
        row = bg_candidate[y]
        for x in range(w):
            r, g, b, _ = pix[x, y]
            row[x] = _dist_l1((int(r), int(g), int(b))) <= dist_thresh

    from collections import deque

    bg_mask = [[False] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()

    def _enqueue_if_bg(x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        if bg_mask[y][x] or (not bg_candidate[y][x]):
            return
        bg_mask[y][x] = True
        q.append((x, y))

    for x in range(w):
        _enqueue_if_bg(x, 0)
        _enqueue_if_bg(x, h - 1)
    for y in range(h):
        _enqueue_if_bg(0, y)
        _enqueue_if_bg(w - 1, y)

    while q:
        x, y = q.popleft()
        _enqueue_if_bg(x - 1, y)
        _enqueue_if_bg(x + 1, y)
        _enqueue_if_bg(x, y - 1)
        _enqueue_if_bg(x, y + 1)

    total = max(1, w * h)
    bg_pixels = sum(1 for y in range(h) for x in range(w) if bg_mask[y][x])
    bg_ratio = float(bg_pixels) / float(total)
    # Too little/too much background means this likely isn't an icon foreground crop.
    if bg_ratio < 0.15 or bg_ratio > 0.93:
        return False

    alpha_bytes = bytearray(total)
    idx = 0
    for y in range(h):
        for x in range(w):
            alpha_bytes[idx] = 0 if bg_mask[y][x] else 255
            idx += 1

    alpha = Image.frombytes("L", (w, h), bytes(alpha_bytes)).filter(
        ImageFilter.GaussianBlur(radius=0.7)
    )
    img.putalpha(alpha)

    try:
        img.save(crop_path)
    except Exception:
        return False
    return True


def _clear_regions_for_transparent_crops(
    *,
    cleaned_render_path: Path,
    out_path: Path,
    regions_pt: list[list[float]],
    pix: Any,
    page_height_pt: float,
    dpi: int,
) -> Path:
    if not regions_pt:
        return cleaned_render_path

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return cleaned_render_path

    try:
        img = Image.open(cleaned_render_path).convert("RGB")
    except Exception:
        return cleaned_render_path

    draw = ImageDraw.Draw(img)
    for bb in regions_pt:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue

        # Use local surrounding color so erase remains visually consistent.
        fill_rgb = _sample_bbox_background_rgb(
            pix,
            bbox_pt=[x0, y0, x1, y1],
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        x0p, y0p = _pdf_pt_to_pix_px(
            x0,
            y0,
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1,
            y1,
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        x0p = max(0, min(int(img.width - 1), int(x0p)))
        y0p = max(0, min(int(img.height - 1), int(y0p)))
        x1p = max(0, min(int(img.width), int(x1p)))
        y1p = max(0, min(int(img.height), int(y1p)))
        if x1p <= x0p or y1p <= y0p:
            continue
        draw.rectangle([x0p, y0p, x1p, y1p], fill=fill_rgb)

    try:
        _ensure_parent_dir(out_path)
        img.save(out_path)
        return out_path
    except Exception:
        return cleaned_render_path


def _compute_text_erase_padding_pt(
    *,
    bbox_h_pt: float,
    text_erase_mode: str,
) -> tuple[float, float]:
    """Compute erase padding (in pt) for OCR text cleanup.

    Use a shared strategy for scanned OCR and MinerU text cleanup so the
    rendered erase behavior stays consistent across parse backends.
    """

    h_pt = max(1.0, float(bbox_h_pt))
    mode = str(text_erase_mode or "smart").strip().lower()

    if mode == "fill":
        # Fill mode should stay local, but still cover anti-aliased glyph halos.
        # Slightly stronger padding reduces residual ghosting on OCR-heavy slides.
        pad_x_pt = max(1.3, min(6.6, 0.30 * h_pt))
        pad_y_pt = max(1.0, min(4.4, 0.23 * h_pt))
    else:
        # Smart mode supports wider context because replacement is pixel-adaptive.
        pad_x_pt = max(1.0, min(8.0, 0.35 * h_pt))
        pad_y_pt = max(0.8, min(4.0, 0.20 * h_pt))

    return (float(pad_x_pt), float(pad_y_pt))


def _normalize_text_for_bbox_dedupe(text: str) -> str:
    return "".join(
        ch.lower()
        for ch in str(text or "")
        if ch.isalnum() or _is_cjk_char(ch)
    )


def _texts_similar_for_bbox_dedupe(a: str, b: str) -> bool:
    na = _normalize_text_for_bbox_dedupe(a)
    nb = _normalize_text_for_bbox_dedupe(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        short = min(len(na), len(nb))
        long = max(len(na), len(nb))
        return short >= 3 and (float(short) / float(long)) >= 0.66
    return False


def _dedupe_scanned_ocr_text_elements(
    *,
    ocr_text_elements: list[dict[str, Any]],
    baseline_ocr_h_pt: float,
) -> list[dict[str, Any]]:
    """Drop near-duplicate OCR text bboxes on scanned pages.

    Some OCR backends (or their post-processors) can output the same visual line
    twice with tiny bbox jitter. In PPT output this shows up as "double text"
    with a slight offset. We keep the most confident/tight bbox per line.
    """

    if len(ocr_text_elements) <= 1:
        return list(ocr_text_elements)

    candidates: list[dict[str, Any]] = []
    for el in ocr_text_elements:
        if not isinstance(el, dict):
            continue
        bbox_pt = el.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        text = str(el.get("text") or "").strip()
        if not text:
            continue
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        area = float((x1 - x0) * (y1 - y0))
        conf = float(el.get("confidence") or 0.0)
        candidates.append(
            {
                **el,
                "bbox_pt": [float(x0), float(y0), float(x1), float(y1)],
                "_bbox": [float(x0), float(y0), float(x1), float(y1)],
                "_area": float(area),
                "_conf": float(conf),
                "_text": text,
            }
        )

    if len(candidates) <= 1:
        return [dict(el) for el in ocr_text_elements if isinstance(el, dict)]

    # Prefer higher confidence, then smaller/tighter bboxes.
    candidates.sort(key=lambda it: (-float(it.get("_conf") or 0.0), float(it.get("_area") or 0.0)))

    baseline = max(4.0, float(baseline_ocr_h_pt))
    kept: list[dict[str, Any]] = []
    for cur in candidates:
        cur_bbox = cur.get("_bbox")
        if not isinstance(cur_bbox, list) or len(cur_bbox) != 4:
            continue
        cur_area = float(cur.get("_area") or 1.0)
        cur_text = str(cur.get("_text") or "")
        cur_cy = float(cur_bbox[1] + cur_bbox[3]) / 2.0

        duplicate = False
        for prev in kept:
            prev_bbox = prev.get("_bbox")
            if not isinstance(prev_bbox, list) or len(prev_bbox) != 4:
                continue
            prev_area = float(prev.get("_area") or 1.0)
            prev_cy = float(prev_bbox[1] + prev_bbox[3]) / 2.0
            inter = _bbox_intersection_area_pt(cur_bbox, prev_bbox)
            if inter <= 0.0:
                continue

            overlap_small = float(inter) / max(1.0, float(min(cur_area, prev_area)))
            iou = _bbox_iou_pt(cur_bbox, prev_bbox)
            dy = abs(float(cur_cy) - float(prev_cy))

            # Strong geometry duplicates (same line, jitter).
            if overlap_small >= 0.965 and iou >= 0.85:
                duplicate = True
                break

            # Same text, reasonably overlapping bboxes.
            if overlap_small >= 0.86 and _texts_similar_for_bbox_dedupe(
                cur_text, str(prev.get("_text") or "")
            ):
                duplicate = True
                break

            # Some AI OCR engines (notably DeepSeek grounding outputs on gateways)
            # can emit the *same* visual line twice with a moderate bbox jitter
            # (overlap ~0.70-0.85). Use a vertical-center guard so we don't
            # accidentally delete distinct adjacent lines.
            if dy <= (0.55 * baseline) and _texts_similar_for_bbox_dedupe(
                cur_text, str(prev.get("_text") or "")
            ):
                if overlap_small >= 0.70 or iou >= 0.55:
                    duplicate = True
                    break

            # Defensive: when two boxes are nearly on the same baseline and
            # overlap heavily, keep only one even if text differs (malformed OCR
            # can map different strings onto the same ink).
            if dy <= (0.35 * baseline) and (overlap_small >= 0.80 or iou >= 0.60):
                duplicate = True
                break

            # When line height is near baseline, even slightly smaller overlaps
            # are suspicious duplicates (word vs line boxing). Keep only one.
            try:
                _, y0, _, y1 = _coerce_bbox_pt(cur_bbox)
                cur_h = float(y1 - y0)
            except Exception:
                cur_h = baseline
            if cur_h <= (1.35 * baseline) and overlap_small >= 0.78 and _texts_similar_for_bbox_dedupe(
                cur_text, str(prev.get("_text") or "")
            ):
                duplicate = True
                break

        if duplicate:
            continue
        kept.append(cur)

    def _reading_key(it: dict[str, Any]) -> tuple[float, float]:
        bb = it.get("_bbox")
        if not isinstance(bb, list) or len(bb) != 4:
            return (0.0, 0.0)
        x0, y0, x1, y1 = bb
        return ((float(y0) + float(y1)) / 2.0, float(x0))

    kept.sort(key=_reading_key)
    out: list[dict[str, Any]] = []
    for it in kept:
        cp = dict(it)
        cp.pop("_bbox", None)
        cp.pop("_area", None)
        cp.pop("_conf", None)
        cp.pop("_text", None)
        out.append(cp)
    return out


def _merge_neighbor_boxes_pt(
    boxes: list[list[float]],
    *,
    page_w_pt: float,
    page_h_pt: float,
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
) -> list[list[float]]:
    if len(boxes) <= 1:
        return [list(_coerce_bbox_pt(bb)) for bb in boxes if isinstance(bb, list)]

    merged = [list(_coerce_bbox_pt(bb)) for bb in boxes if isinstance(bb, list)]
    if len(merged) <= 1:
        return merged

    gap_x_pt = max(16.0, 0.04 * float(page_w_pt))
    gap_y_pt = max(12.0, 0.03 * float(page_h_pt))
    for _ in range(2):
        out: list[list[float]] = []
        for bb in merged:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
            did_merge = False
            for i, ub in enumerate(out):
                ux0, uy0, ux1, uy1 = _coerce_bbox_pt(ub)
                # Two merge modes:
                # - horizontal adjacency (left/right fragments): require strong Y overlap
                # - vertical adjacency (top/bottom fragments): require strong X overlap
                y_overlap = float(min(y1, uy1) - max(y0, uy0))
                x_overlap = float(min(x1, ux1) - max(x0, ux0))
                min_h = max(1.0, float(min(y1 - y0, uy1 - uy0)))
                min_w = max(1.0, float(min(x1 - x0, ux1 - ux0)))

                # Horizontal merge (existing behavior).
                horizontal_ok = False
                if y_overlap > 0.0 and y_overlap >= (0.62 * min_h):
                    if x0 > ux1:
                        x_gap = float(x0 - ux1)
                    elif ux0 > x1:
                        x_gap = float(ux0 - x1)
                    else:
                        x_gap = 0.0
                    horizontal_ok = x_gap <= gap_x_pt

                # Vertical merge (new): needed for screenshots that are detected as
                # separate top/bottom strips when OCR masking removes some edges.
                vertical_ok = False
                if x_overlap > 0.0 and x_overlap >= (0.62 * min_w):
                    if y0 > uy1:
                        y_gap = float(y0 - uy1)
                    elif uy0 > y1:
                        y_gap = float(uy0 - y1)
                    else:
                        y_gap = 0.0
                    vertical_ok = y_gap <= gap_y_pt

                if not (horizontal_ok or vertical_ok):
                    continue

                candidate = [
                    min(x0, ux0),
                    min(y0, uy0),
                    max(x1, ux1),
                    max(y1, uy1),
                ]
                cw = float(candidate[2] - candidate[0])
                ch = float(candidate[3] - candidate[1])
                page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
                area_ratio = max(0.0, cw * ch) / page_area
                width_ratio = cw / max(1.0, float(page_w_pt))
                cov, n = text_coverage_ratio_fn(candidate)

                # Avoid cross-card and mixed text+image mega merges that swallow paragraphs.
                if (
                    (width_ratio >= 0.56 and (n >= 2 or cov >= 0.08))
                    or (area_ratio >= 0.16 and (n >= 3 or cov >= 0.12))
                    or (width_ratio >= 0.34 and n >= 2 and cov >= 0.05)
                    or (width_ratio >= 0.26 and n >= 3 and cov >= 0.04)
                    or (area_ratio >= 0.08 and n >= 2 and cov >= 0.07)
                ):
                    continue

                out[i] = candidate
                did_merge = True
                break

            if not did_merge:
                out.append([x0, y0, x1, y1])
        merged = out

    return merged


def _collect_scanned_image_region_candidates(
    *,
    page: dict[str, Any],
    render_path: Path,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    ocr_text_elements: list[dict[str, Any]],
    has_full_page_bg_image: bool,
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
) -> list[list[float]]:
    baseline_ocr_h_pt = (
        _estimate_baseline_ocr_line_height_pt(
            ocr_text_elements=ocr_text_elements,
            page_w_pt=float(page_w_pt),
        )
        if ocr_text_elements
        else 12.0
    )

    regions_pt_from_ai: list[list[float]] = []
    regions = page.get("image_regions")
    if isinstance(regions, list) and regions:
        for bbox in regions:
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
            except Exception:
                continue
            # Ignore card-like mixed content panels suggested by AI.
            area = max(0.0, float(x1 - x0) * float(y1 - y0))
            # For scanned pages with OCR text, AI-suggested image regions are too
            # error-prone (often card/text panels). Prefer render-based detection only.
            if ocr_text_elements:
                continue
            page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
            area_ratio = area / page_area
            if area_ratio < 0.0020 or area_ratio > 0.75:
                continue
            cov, n = text_coverage_ratio_fn([x0, y0, x1, y1])
            width_ratio = float(x1 - x0) / max(1.0, float(page_w_pt))
            height_ratio = float(y1 - y0) / max(1.0, float(page_h_pt))
            # AI layout suggestions may occasionally return whole card/text panels
            # as image regions. Keep only candidates that are not text-heavy.
            if (n >= 8 and cov >= 0.14) or (n >= 3 and cov >= 0.30):
                continue
            if area_ratio >= 0.12 and n >= 4 and cov >= 0.08:
                continue
            if (width_ratio >= 0.26 and n >= 2 and cov >= 0.05) or (
                area_ratio >= 0.06 and n >= 2 and cov >= 0.07
            ):
                continue
            if height_ratio >= 0.42 and n >= 2 and cov >= 0.06:
                continue
            regions_pt_from_ai.append([x0, y0, x1, y1])

    if has_full_page_bg_image and len(ocr_text_elements) <= 4 and not regions_pt_from_ai:
        return []

    regions_pt_masked = _detect_image_regions_from_render(
        render_path,
        page_width_pt=page_w_pt,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
        ocr_text_elements=ocr_text_elements,
        max_regions=24,
    )
    regions_pt_unmasked: list[list[float]] = []
    try:
        regions_pt_unmasked = _detect_image_regions_from_render(
            render_path,
            page_width_pt=page_w_pt,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
            ocr_text_elements=None,
            max_regions=6,
            merge_gap_scale=0.06,
        )
    except Exception:
        regions_pt_unmasked = []

    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))

    filtered_masked: list[list[float]] = []
    for bb in regions_pt_masked:
        try:
            mx0, my0, mx1, my1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        area = max(0.0, float(mx1 - mx0) * float(my1 - my0))
        area_ratio = float(area) / float(page_area)
        if area_ratio < 0.0022:
            continue

        cov, n = text_coverage_ratio_fn([mx0, my0, mx1, my1])
        width_ratio = float(mx1 - mx0) / max(1.0, float(page_w_pt))
        height_ratio = float(my1 - my0) / max(1.0, float(page_h_pt))
        if (n >= 4 and cov >= 0.08) or (area_ratio >= 0.12 and n >= 4):
            continue
        if n >= 2 and cov >= 0.52:
            continue
        if (width_ratio >= 0.28 and n >= 2 and cov >= 0.05) or (
            area_ratio >= 0.05 and n >= 2 and cov >= 0.07
        ):
            continue
        if height_ratio >= 0.42 and n >= 2 and cov >= 0.06:
            continue

        filtered_masked.append([mx0, my0, mx1, my1])

    filtered_unmasked: list[list[float]] = []
    for bb in regions_pt_unmasked:
        try:
            ux0, uy0, ux1, uy1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        area = max(0.0, float(ux1 - ux0) * float(uy1 - uy0))
        area_ratio = float(area) / float(page_area)
        if area_ratio < 0.025:
            continue

        cov, n = text_coverage_ratio_fn([ux0, uy0, ux1, uy1])
        width_ratio = float(ux1 - ux0) / max(1.0, float(page_w_pt))
        height_ratio = float(uy1 - uy0) / max(1.0, float(page_h_pt))
        # Unmasked detection is high-recall but noisy.
        #
        # Historically we required `n == 0` (no OCR items inside), but this
        # breaks screenshots: better OCR models detect lots of small UI text
        # inside screenshots/diagrams, causing us to discard the *union* box that
        # is needed to merge fragmented masked detections.
        #
        # Instead, allow some text overlap as long as it looks "small" relative
        # to the page baseline and coverage stays low.
        if cov >= 0.14:
            continue
        if area_ratio >= 0.62:
            continue
        if width_ratio >= 0.78 or height_ratio >= 0.78:
            continue

        large_line_inside = 0
        large_cjk_inside = 0
        wide_large_line_inside = 0
        large_line_h_threshold = max(4.0, 0.62 * float(baseline_ocr_h_pt))
        for tel in ocr_text_elements:
            bbox_pt = tel.get("bbox_pt")
            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                continue
            try:
                tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue
            tcx = (tx0 + tx1) / 2.0
            tcy = (ty0 + ty1) / 2.0
            if tcx < ux0 or tcx > ux1 or tcy < uy0 or tcy > uy1:
                continue

            tw = max(1.0, float(tx1 - tx0))
            th = max(1.0, float(ty1 - ty0))
            if th < large_line_h_threshold:
                continue

            text_value = str(tel.get("text") or "")
            if _is_inline_short_token(text_value):
                continue
            if _compact_text_length(text_value) < 4:
                continue

            large_line_inside += 1
            if _contains_cjk(text_value):
                large_cjk_inside += 1
            if tw >= 0.22 * float(ux1 - ux0):
                wide_large_line_inside += 1

        # Reject text-panel/card false positives.
        if large_line_inside >= 2 and cov >= 0.10:
            continue
        if large_cjk_inside >= 1 and cov >= 0.08:
            continue
        if wide_large_line_inside >= 2 and cov >= 0.06:
            continue

        filtered_unmasked.append([ux0, uy0, ux1, uy1])

    def _bbox_area_pt(bb: list[float]) -> float:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            return 0.0
        return max(0.0, float(x1 - x0) * float(y1 - y0))

    # Prefer masked candidates (OCR-aware), but keep unmasked candidates that
    # can *merge* fragmented masked detections (common for screenshots where OCR
    # masking removes key edges and splits a single image into multiple strips).
    promoted_unmasked: list[list[float]] = []
    for ub in filtered_unmasked:
        u_area = _bbox_area_pt(ub)
        if u_area <= 0.0:
            continue
        overlap_hits = 0
        best_containment = 0.0
        best_m_area = 0.0
        for mb in filtered_masked:
            m_area = _bbox_area_pt(mb)
            if m_area <= 0.0:
                continue
            inter = _bbox_intersection_area_pt(ub, mb)
            if inter <= 0.0:
                continue
            containment = float(inter) / float(m_area)
            best_containment = max(best_containment, containment)
            best_m_area = max(best_m_area, m_area)
            # Count as a "piece" when ub largely contains mb (or overlaps
            # meaningfully), indicating ub is a plausible union box.
            if containment >= 0.55 or _bbox_iou_pt(ub, mb) >= 0.12:
                overlap_hits += 1

        if overlap_hits >= 2:
            promoted_unmasked.append(ub)
            continue
        # If masking yields just one small fragment, allow a larger unmasked box
        # to replace it when it contains the fragment well.
        if overlap_hits == 1 and best_containment >= 0.65 and best_m_area > 0.0:
            if u_area >= (1.8 * float(best_m_area)):
                promoted_unmasked.append(ub)

    if promoted_unmasked:
        try:
            promoted_unmasked.sort(key=_bbox_area_pt, reverse=True)
        except Exception:
            pass
        promoted_unmasked = promoted_unmasked[:2]

    # Keep a small unmasked supplement. When there are many masked candidates,
    # only keep promoted unmasked boxes (merge hints) to avoid reintroducing
    # text-panel false positives when OCR misses some body text.
    if len(filtered_masked) >= 4:
        filtered_unmasked = list(promoted_unmasked)
    else:
        budget = max(0, 6 - len(filtered_masked))
        budget = max(budget, len(promoted_unmasked))
        keep: list[list[float]] = []
        for ub in promoted_unmasked:
            keep.append(ub)
        for ub in filtered_unmasked:
            if len(keep) >= budget:
                break
            duplicated = False
            for kb in keep:
                try:
                    if _bbox_iou_pt(ub, kb) >= 0.85:
                        duplicated = True
                        break
                except Exception:
                    continue
            if not duplicated:
                keep.append(ub)
        filtered_unmasked = keep[:budget]

    combined = []
    for bb in list(regions_pt_from_ai or []) + filtered_masked + filtered_unmasked:
        if not isinstance(bb, (list, tuple)) or len(bb) != 4:
            continue
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        combined.append([x0, y0, x1, y1])

    if not combined:
        return []

    combined = _merge_neighbor_boxes_pt(
        combined,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        text_coverage_ratio_fn=text_coverage_ratio_fn,
    )

    combined.sort(
        key=lambda b: float((b[2] - b[0]) * (b[3] - b[1])),
        reverse=True,
    )

    uniq: list[list[float]] = []
    for bb in combined:
        cand_area = max(1.0, float((bb[2] - bb[0]) * (bb[3] - bb[1])))
        keep = True
        for ub in uniq:
            if (
                abs(bb[0] - ub[0]) <= 2.0
                and abs(bb[1] - ub[1]) <= 2.0
                and abs(bb[2] - ub[2]) <= 2.0
                and abs(bb[3] - ub[3]) <= 2.0
            ):
                keep = False
                break

            inter = _bbox_intersection_area_pt(bb, ub)
            if inter <= 0.0:
                continue
            if _bbox_iou_pt(bb, ub) >= 0.68:
                keep = False
                break
            if (inter / cand_area) >= 0.90:
                keep = False
                break

        if keep:
            uniq.append(bb)
        if len(uniq) >= 24:
            break

    try:
        uniq.sort(
            key=lambda b: (
                -float((b[2] - b[0]) * (b[3] - b[1])),
                float(text_coverage_ratio_fn(b)[0]),
            )
        )
    except Exception:
        pass
    return uniq




def _is_card_like_region(
    bbox: list[float],
    *,
    page_w_pt: float,
    page_h_pt: float,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
) -> bool:
    """Detect card-like mixed content region on scanned slides.

    These regions usually contain: an icon + title + paragraph + embedded figure,
    and should *not* be treated as a single image crop.
    """

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return False
    w = float(x1 - x0)
    h = float(y1 - y0)
    if w <= 0.0 or h <= 0.0:
        return False

    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    area_ratio = (w * h) / page_area
    width_ratio = w / max(1.0, float(page_w_pt))
    height_ratio = h / max(1.0, float(page_h_pt))

    # Cards are usually medium-to-large panels.
    if area_ratio < 0.10:
        return False
    if width_ratio < 0.22 or height_ratio < 0.18:
        return False
    if width_ratio > 0.78 or height_ratio > 0.78:
        return False

    line_h_threshold = max(4.0, 0.60 * float(baseline_ocr_h_pt))
    text_lines = 0
    cjk_lines = 0
    area_overlap = 0.0

    for tel in ocr_text_elements:
        bbox_pt = tel.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue

        cx = (tx0 + tx1) / 2.0
        cy = (ty0 + ty1) / 2.0
        if cx < x0 or cx > x1 or cy < y0 or cy > y1:
            continue

        text_value = str(tel.get("text") or "")
        if _is_inline_short_token(text_value):
            continue

        tw = max(1.0, float(tx1 - tx0))
        th = max(1.0, float(ty1 - ty0))
        if th < line_h_threshold:
            continue

        text_lines += 1
        if _contains_cjk(text_value):
            cjk_lines += 1
        area_overlap += _bbox_intersection_area_pt([x0, y0, x1, y1], [tx0, ty0, tx1, ty1])

    cov = min(1.0, area_overlap / max(1.0, w * h))
    if text_lines >= 4:
        return True
    if cjk_lines >= 2 and text_lines >= 3:
        return True
    if text_lines >= 2 and cov >= 0.05 and area_ratio >= 0.14:
        return True
    return False

def _save_scanned_regions_debug_overlay(
    *,
    render_path: Path,
    regions_pt: list[list[float]],
    artifacts_dir: Path,
    page_index: int,
    page_h_pt: float,
    scanned_render_dpi: int,
) -> None:
    if not regions_pt:
        return
    try:
        import json
        from PIL import Image, ImageDraw

        ov = Image.open(render_path).convert("RGB")
        d = ImageDraw.Draw(ov)
        for i, bb in enumerate(regions_pt[:24]):
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
            x0p, y0p = _pdf_pt_to_pix_px(
                x0,
                y0,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
            )
            x1p, y1p = _pdf_pt_to_pix_px(
                x1,
                y1,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
            )
            d.rectangle([x0p, y0p, x1p, y1p], outline=(0, 200, 0), width=3)
            d.text((x0p + 4, y0p + 4), str(i), fill=(0, 120, 0))

        dbg_dir = artifacts_dir / "image_regions"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        dbg_path = dbg_dir / f"page-{page_index:04d}.regions.png"
        ov.save(dbg_path)
        try:
            json_path = dbg_dir / f"page-{page_index:04d}.regions.json"
            payload = {
                "page_index": int(page_index),
                "regions_pt": [list(_coerce_bbox_pt(bb)) for bb in regions_pt],
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    except Exception:
        pass


def _try_merge_fragmented_scanned_image_regions(
    *,
    infos: list[_ScannedImageRegionInfo],
    img: Any,
    crops_dir: Path,
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
) -> list[_ScannedImageRegionInfo]:
    """Try to merge split screenshot/diagram regions on scanned pages.

    When OCR masking removes key edges, the render-based detector may find
    multiple fragments (top strip + bottom strip, etc.). Before we commit the
    crops into the PPT we do a small greedy merge pass:
    - only merge close/adjacent regions
    - require the *union crop* to look more like a real image (shape-confirmed)
    - keep conservative text-coverage guards to avoid swallowing paragraphs

    This is intentionally heuristic; it's meant to improve broad reliability
    across OCR models (including ones that output lots of tiny UI text boxes).
    """

    if len(infos) <= 1:
        return infos
    if page_w_pt <= 0 or page_h_pt <= 0:
        return infos

    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    merge_counter = 0

    def _bbox_area(bb: list[float]) -> float:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            return 0.0
        return max(0.0, float(x1 - x0) * float(y1 - y0))

    def _bbox_union(a: list[float], b: list[float]) -> list[float]:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)
        return [
            float(min(ax0, bx0)),
            float(min(ay0, by0)),
            float(max(ax1, bx1)),
            float(max(ay1, by1)),
        ]

    def _gap_and_overlap_ratios(
        a: list[float], b: list[float]
    ) -> tuple[float, float, float, float]:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)

        x_overlap = float(min(ax1, bx1) - max(ax0, bx0))
        y_overlap = float(min(ay1, by1) - max(ay0, by0))
        min_w = max(1.0, float(min(ax1 - ax0, bx1 - bx0)))
        min_h = max(1.0, float(min(ay1 - ay0, by1 - by0)))
        x_overlap_ratio = (x_overlap / min_w) if x_overlap > 0.0 else 0.0
        y_overlap_ratio = (y_overlap / min_h) if y_overlap > 0.0 else 0.0

        x_gap = 0.0
        if ax0 > bx1:
            x_gap = float(ax0 - bx1)
        elif bx0 > ax1:
            x_gap = float(bx0 - ax1)

        y_gap = 0.0
        if ay0 > by1:
            y_gap = float(ay0 - by1)
        elif by0 > ay1:
            y_gap = float(by0 - ay1)

        return (x_gap, y_gap, x_overlap_ratio, y_overlap_ratio)

    def _crop_bbox_to_path(bbox_pt: list[float], out_path: Path) -> bool:
        try:
            from PIL import Image
        except Exception:
            return False

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            return False

        x0p, y0p = _pdf_pt_to_pix_px(
            x0,
            y0,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1,
            y1,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x0p = max(0, min(int(img.width - 1), int(x0p)))
        y0p = max(0, min(int(img.height - 1), int(y0p)))
        x1p = max(0, min(int(img.width), int(x1p)))
        y1p = max(0, min(int(img.height), int(y1p)))
        if x1p <= x0p or y1p <= y0p:
            return False

        try:
            crop = img.crop((x0p, y0p, x1p, y1p))
            _ensure_parent_dir(out_path)
            crop.save(out_path)
            return True
        except Exception:
            return False

    def _build_union_info(
        bbox_pt: list[float], *, crop_path: Path, shape_confirmed: bool
    ) -> _ScannedImageRegionInfo:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        w_pt = float(x1 - x0)
        h_pt = float(y1 - y0)
        if shape_confirmed:
            pad_x = max(1.5, min(8.0, 0.05 * w_pt))
            pad_y = max(1.0, min(6.0, 0.07 * h_pt))
        else:
            pad_x = max(0.8, min(3.5, 0.02 * w_pt))
            pad_y = max(0.8, min(3.0, 0.03 * h_pt))
        suppress_bbox = [
            max(0.0, float(x0) - pad_x),
            max(0.0, float(y0) - pad_y),
            min(float(page_w_pt), float(x1) + pad_x),
            min(float(page_h_pt), float(y1) + pad_y),
        ]
        return _ScannedImageRegionInfo(
            bbox_pt=[float(x0), float(y0), float(x1), float(y1)],
            suppress_bbox_pt=[float(v) for v in _coerce_bbox_pt(suppress_bbox)],
            crop_path=crop_path,
            shape_confirmed=bool(shape_confirmed),
            background_removed=False,
        )

    merged = list(infos)
    for _ in range(3):
        changed = False
        merged.sort(key=lambda info: _bbox_area(info.bbox_pt), reverse=True)

        for i in range(len(merged)):
            a = merged[i]
            a_area = _bbox_area(a.bbox_pt)
            if a_area <= 0.0:
                continue
            for j in range(i + 1, len(merged)):
                b = merged[j]
                b_area = _bbox_area(b.bbox_pt)
                if b_area <= 0.0:
                    continue
                # Don't merge transparent/icon crops; those should remain editable.
                if a.background_removed or b.background_removed:
                    continue

                ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a.bbox_pt)
                bx0, by0, bx1, by1 = _coerce_bbox_pt(b.bbox_pt)
                aw = max(1.0, float(ax1 - ax0))
                ah = max(1.0, float(ay1 - ay0))
                bw = max(1.0, float(bx1 - bx0))
                bh = max(1.0, float(by1 - by0))

                x_gap, y_gap, x_ov, y_ov = _gap_and_overlap_ratios(a.bbox_pt, b.bbox_pt)
                # Only consider adjacent fragments.
                gap_x_limit = max(6.0, min(0.04 * float(page_w_pt), 40.0))
                gap_y_limit = max(6.0, min(0.03 * float(page_h_pt), 32.0))

                horizontal_adjacent = y_ov >= 0.70 and x_gap <= gap_x_limit
                vertical_adjacent = x_ov >= 0.70 and y_gap <= gap_y_limit
                if not (horizontal_adjacent or vertical_adjacent):
                    continue

                # Alignment check: fragmented screenshot detections typically share
                # the same left/right (or top/bottom) edges. Avoid merging two
                # unrelated nearby images in a grid.
                tol_x = max(8.0, min(0.05 * float(page_w_pt), 48.0))
                tol_y = max(8.0, min(0.05 * float(page_h_pt), 48.0))
                width_sim = abs(aw - bw) <= (0.25 * max(aw, bw))
                height_sim = abs(ah - bh) <= (0.25 * max(ah, bh))

                aligned = False
                if vertical_adjacent:
                    aligned = (abs(ax0 - bx0) <= tol_x and abs(ax1 - bx1) <= tol_x) or (
                        width_sim and x_ov >= 0.85
                    )
                elif horizontal_adjacent:
                    aligned = (abs(ay0 - by0) <= tol_y and abs(ay1 - by1) <= tol_y) or (
                        height_sim and y_ov >= 0.85
                    )
                if not aligned:
                    continue

                union_bbox = _bbox_union(a.bbox_pt, b.bbox_pt)
                union_area = _bbox_area(union_bbox)
                if union_area <= 0.0:
                    continue

                # Avoid massive unions (two separate images far apart).
                if union_area > (1.45 * float(a_area + b_area)):
                    continue

                union_area_ratio = float(union_area) / float(page_area)
                if union_area_ratio < 0.020:
                    continue
                if union_area_ratio > 0.72:
                    continue

                cov, n = text_coverage_ratio_fn(union_bbox)
                # Keep conservative: merged screenshot regions should not be text-heavy.
                if cov >= 0.18 or n >= 16:
                    continue

                if _is_card_like_region(
                    union_bbox,
                    page_w_pt=page_w_pt,
                    page_h_pt=page_h_pt,
                    baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                    ocr_text_elements=ocr_text_elements,
                ):
                    continue

                merge_counter += 1
                union_crop_path = (
                    crops_dir / f"page-{page_index:04d}-crop-merge-{merge_counter:02d}.png"
                )
                if not _crop_bbox_to_path(union_bbox, union_crop_path):
                    continue

                union_stats = _analyze_shape_crop(union_crop_path)
                if not union_stats.get("confirmed"):
                    continue

                union_info = _build_union_info(
                    union_bbox,
                    crop_path=union_crop_path,
                    shape_confirmed=bool(union_stats.get("confirmed")),
                )

                # Replace (a,b) with their union.
                keep: list[_ScannedImageRegionInfo] = []
                for k, info in enumerate(merged):
                    if k in (i, j):
                        continue
                    keep.append(info)
                keep.append(union_info)
                merged = keep
                changed = True
                break

            if changed:
                break

        if not changed:
            break

    return merged


def _build_scanned_image_region_infos(
    *,
    page: dict[str, Any],
    render_path: Path,
    artifacts_dir: Path,
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
    has_full_page_bg_image: bool,
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
    text_inside_counts_fn: Callable[[list[float]], tuple[int, int]],
) -> list[_ScannedImageRegionInfo]:
    regions_pt = _collect_scanned_image_region_candidates(
        page=page,
        render_path=render_path,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
        ocr_text_elements=ocr_text_elements,
        has_full_page_bg_image=has_full_page_bg_image,
        text_coverage_ratio_fn=text_coverage_ratio_fn,
    )
    _save_scanned_regions_debug_overlay(
        render_path=render_path,
        regions_pt=regions_pt,
        artifacts_dir=artifacts_dir,
        page_index=page_index,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
    )
    if not regions_pt:
        return []

    try:
        from PIL import Image
    except Exception:
        return []

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return []

    crops_dir = artifacts_dir / "image_crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    infos: list[_ScannedImageRegionInfo] = []

    for ri, bbox in enumerate(regions_pt):
        if len(infos) >= 12:
            break

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
        except Exception:
            continue
        w_pt = float(x1 - x0)
        h_pt = float(y1 - y0)
        if w_pt <= 0.0 or h_pt <= 0.0:
            continue

        if _is_card_like_region(
            [x0, y0, x1, y1],
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            ocr_text_elements=ocr_text_elements,
        ):
            continue

        area_pt = max(0.0, w_pt * h_pt)
        area_ratio = area_pt / page_area
        if area_ratio < 0.0025 or area_ratio > 0.72:
            continue
        if min(w_pt, h_pt) < 12.0:
            continue

        aspect = max(w_pt / max(1.0, h_pt), h_pt / max(1.0, w_pt))
        if aspect >= 4.8 and area_ratio < 0.08:
            continue

        min_dim_pt = max(18.0, 1.8 * float(baseline_ocr_h_pt))
        min_dim_pt = min(72.0, float(min_dim_pt))
        min_area_pt = 0.65 * float(min_dim_pt) * float(min_dim_pt)
        if area_pt < min_area_pt:
            continue

        cov, n = text_coverage_ratio_fn([x0, y0, x1, y1])
        n_inside, n_cjk_inside = text_inside_counts_fn([x0, y0, x1, y1])

        large_line_inside = 0
        wide_large_line_inside = 0
        large_line_overlap = 0.0
        large_line_h_threshold = max(4.0, 0.72 * float(baseline_ocr_h_pt))
        for tel in ocr_text_elements:
            bbox_pt = tel.get("bbox_pt")
            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                continue
            try:
                tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue
            tcx = (tx0 + tx1) / 2.0
            tcy = (ty0 + ty1) / 2.0
            if tcx < x0 or tcx > x1 or tcy < y0 or tcy > y1:
                continue

            tw = max(1.0, float(tx1 - tx0))
            th = max(1.0, float(ty1 - ty0))
            text_value = str(tel.get("text") or "")
            compact_len = _compact_text_length(text_value)
            if compact_len < 4:
                continue
            if th < large_line_h_threshold:
                continue
            if _is_inline_short_token(text_value):
                continue

            large_line_inside += 1
            if tw >= 0.22 * w_pt:
                wide_large_line_inside += 1
            large_line_overlap += _bbox_intersection_area_pt(
                [tx0, ty0, tx1, ty1], [x0, y0, x1, y1]
            )

        large_line_cov = min(1.0, large_line_overlap / max(1.0, area_pt))

        # Strong text-block candidates should not become image crops.
        if (n >= 4 and cov >= 0.10) or (n >= 3 and cov >= 0.16) or (n >= 2 and cov >= 0.24):
            continue
        # Single OCR block with high coverage is often a false-positive card crop
        # (e.g. CJK title/body region) rather than a real screenshot/diagram.
        if n_inside >= 1 and cov >= 0.42 and area_ratio >= 0.012:
            continue
        if n_cjk_inside >= 1 and cov >= 0.30 and area_ratio >= 0.020:
            continue
        # Large text overlap can indicate mixed text panels, but screenshots may
        # legitimately contain some embedded text. Keep this gate conservative.
        if area_ratio >= 0.020 and large_line_inside >= 2 and large_line_cov >= 0.10:
            continue
        if large_line_inside >= 4 and (cov >= 0.08 or large_line_cov >= 0.10):
            continue
        if wide_large_line_inside >= 2 and large_line_cov >= 0.08 and area_ratio >= 0.030:
            continue

        x0p, y0p = _pdf_pt_to_pix_px(
            x0,
            y0,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1,
            y1,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x0p = max(0, min(int(img.width - 1), int(x0p)))
        y0p = max(0, min(int(img.height - 1), int(y0p)))
        x1p = max(0, min(int(img.width), int(x1p)))
        y1p = max(0, min(int(img.height), int(y1p)))
        if x1p <= x0p or y1p <= y0p:
            continue

        crop = img.crop((x0p, y0p, x1p, y1p))
        crop_out_path = crops_dir / f"page-{page_index:04d}-crop-{ri:02d}.png"
        crop.save(crop_out_path)
        shape_confirmed = _is_shape_confirmed_crop(crop_out_path)
        background_removed = False

        # Keep small icon-like regions as independent picture crops so users can
        # edit/move them in PPT (instead of baking them into a single background).

        # For compact/icon-like crops, remove flat background to avoid card-color
        # patches when re-pasting into PPT.
        if shape_confirmed:
            try:
                # Background removal is intended for small icons/logos. Applying
                # it to screenshots can incorrectly make large white areas
                # transparent, causing "see-through" artifacts.
                if (
                    area_ratio <= 0.020
                    and aspect <= 2.4
                    and cov <= 0.06
                    and n_inside <= 1
                    and max(w_pt, h_pt) <= (7.0 * float(baseline_ocr_h_pt))
                ):
                    background_removed = _try_make_crop_background_transparent(
                        crop_out_path
                    )
            except Exception:
                background_removed = False

        cjk_text_heavy = (
            n_cjk_inside >= 2 and n_inside >= 3 and cov >= 0.08 and area_ratio >= 0.03
        )
        if shape_confirmed:
            if area_ratio >= 0.40 and (cov >= 0.20 or n_inside >= 10):
                continue
            if cjk_text_heavy and area_ratio >= 0.07:
                continue
            if area_ratio >= 0.030 and large_line_inside >= 3 and large_line_cov >= 0.10:
                continue
            if large_line_inside >= 5 and (cov >= 0.08 or large_line_cov >= 0.10):
                continue
            if wide_large_line_inside >= 2 and large_line_cov >= 0.08 and area_ratio >= 0.030:
                continue
        else:
            if cov >= 0.16 or n_inside >= 5 or large_line_inside >= 3:
                continue
            if area_ratio >= 0.24:
                continue
            if cjk_text_heavy and area_ratio >= 0.06:
                continue

        cand_bbox = [float(x0), float(y0), float(x1), float(y1)]
        cand_area = max(1.0, area_pt)
        duplicated = False
        for info in infos:
            inter = _bbox_intersection_area_pt(cand_bbox, info.bbox_pt)
            if inter <= 0.0:
                continue
            if _bbox_iou_pt(cand_bbox, info.bbox_pt) >= 0.66:
                duplicated = True
                break
            ex0, ey0, ex1, ey1 = _coerce_bbox_pt(info.bbox_pt)
            ex_area = max(1.0, float((ex1 - ex0) * (ey1 - ey0)))
            if (inter / cand_area) >= 0.88:
                duplicated = True
                break
            if (inter / ex_area) >= 0.88 and (cand_area / ex_area) >= 1.6 and cov >= 0.08:
                duplicated = True
                break
        if duplicated:
            continue

        if shape_confirmed:
            pad_x = max(1.5, min(8.0, 0.05 * w_pt))
            pad_y = max(1.0, min(6.0, 0.07 * h_pt))
        else:
            pad_x = max(0.8, min(3.5, 0.02 * w_pt))
            pad_y = max(0.8, min(3.0, 0.03 * h_pt))

        suppress_bbox = [
            max(0.0, float(x0) - pad_x),
            max(0.0, float(y0) - pad_y),
            min(float(page_w_pt), float(x1) + pad_x),
            min(float(page_h_pt), float(y1) + pad_y),
        ]
        infos.append(
            _ScannedImageRegionInfo(
                bbox_pt=cand_bbox,
                suppress_bbox_pt=[float(v) for v in _coerce_bbox_pt(suppress_bbox)],
                crop_path=crop_out_path,
                shape_confirmed=bool(shape_confirmed),
                background_removed=bool(background_removed),
            )
        )

    infos = _try_merge_fragmented_scanned_image_regions(
        infos=infos,
        img=img,
        crops_dir=crops_dir,
        page_index=page_index,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
        baseline_ocr_h_pt=baseline_ocr_h_pt,
        ocr_text_elements=ocr_text_elements,
        text_coverage_ratio_fn=text_coverage_ratio_fn,
    )

    # Debug/self-check: persist final crop bboxes used for PPT composition.
    try:
        import json

        dbg_dir = artifacts_dir / "image_regions"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        json_path = dbg_dir / f"page-{page_index:04d}.crops.json"
        payload = {
            "page_index": int(page_index),
            "crops": [
                {
                    "bbox_pt": list(_coerce_bbox_pt(info.bbox_pt)),
                    "suppress_bbox_pt": list(_coerce_bbox_pt(info.suppress_bbox_pt)),
                    "crop_path": str(info.crop_path),
                    "shape_confirmed": bool(info.shape_confirmed),
                    "background_removed": bool(info.background_removed),
                }
                for info in infos
            ],
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return infos


def _filter_scanned_ocr_text_elements(
    *,
    ocr_text_elements: list[dict[str, Any]],
    image_region_infos: list[_ScannedImageRegionInfo],
    baseline_ocr_h_pt: float,
) -> list[dict[str, Any]]:
    if not ocr_text_elements or not image_region_infos:
        return list(ocr_text_elements)

    filtered: list[dict[str, Any]] = []
    for el in ocr_text_elements:
        bb = el.get("bbox_pt") if isinstance(el, dict) else None
        if not isinstance(bb, list) or len(bb) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        tw = float(tx1 - tx0)
        th = float(ty1 - ty0)
        if tw <= 0.0 or th <= 0.0:
            continue

        text_value = str(el.get("text") or "").strip()
        compact_len = _compact_text_length(text_value)
        is_cjk_line = _contains_cjk(text_value)
        keep_as_text_preferred = (
            is_cjk_line and compact_len >= 4 and th >= (0.65 * float(baseline_ocr_h_pt))
        )

        t_area = max(1.0, tw * th)
        tcx = (tx0 + tx1) / 2.0
        tcy = (ty0 + ty1) / 2.0
        inside_image = False
        for info in image_region_infos:
            try:
                ix0, iy0, ix1, iy1 = _coerce_bbox_pt(info.suppress_bbox_pt)
            except Exception:
                continue

            inter = _bbox_intersection_area_pt([tx0, ty0, tx1, ty1], [ix0, iy0, ix1, iy1])
            if inter <= 0.0:
                continue
            overlap_ratio = float(inter) / t_area
            center_inside = tcx >= ix0 and tcx <= ix1 and tcy >= iy0 and tcy <= iy1

            if keep_as_text_preferred and not info.shape_confirmed:
                # Prefer keeping CJK/body text editable when the "image region"
                # is ambiguous (not shape-confirmed). Only suppress tiny labels
                # that are almost fully inside an image region.
                if center_inside and compact_len <= 3 and overlap_ratio >= 0.97:
                    inside_image = True
                    break
                continue

            if overlap_ratio >= 0.72:
                inside_image = True
                break
            if info.shape_confirmed and center_inside and overlap_ratio >= 0.25:
                inside_image = True
                break
            if (not info.shape_confirmed) and center_inside and overlap_ratio >= 0.82:
                inside_image = True
                break
            if center_inside and compact_len <= 3 and overlap_ratio >= 0.22:
                inside_image = True
                break

        if not inside_image:
            filtered.append(el)

    return filtered


def generate_pptx_from_ir(
    ir: dict[str, Any],
    output_pptx_path: str | Path,
    *,
    artifacts_dir: str | Path | None = None,
    force_16x9: bool = False,
    scanned_render_dpi: int = 200,
    scanned_page_mode: str = "segmented",
    text_erase_mode: str = "fill",
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Generate a PPTX from the provided IR.

    Args:
        ir: The intermediate representation dict.
        output_pptx_path: Where to write the PPTX file.
        artifacts_dir: Directory for any intermediate artifacts (e.g. scanned page renders).
        force_16x9: If True, use a 16:9 slide size and letterbox PDF content.
        scanned_render_dpi: DPI used when rendering scanned pages to images.
        text_erase_mode: Erase strategy for background cleanup (smart, fill).
        progress_callback: Optional callback(done_pages, total_pages), called
            after each IR page is written.

    Returns:
        The output PPTX path.
    """

    try:
        pptx = importlib.import_module("pptx")
        Presentation = getattr(pptx, "Presentation")

        RGBColor = getattr(importlib.import_module("pptx.dml.color"), "RGBColor")
        text_enums = importlib.import_module("pptx.enum.text")
        MSO_AUTO_SIZE = getattr(text_enums, "MSO_AUTO_SIZE")
        MSO_ANCHOR = getattr(text_enums, "MSO_ANCHOR")
        PP_ALIGN = getattr(text_enums, "PP_ALIGN")
        util = importlib.import_module("pptx.util")
        Emu = getattr(util, "Emu")
        Pt = getattr(util, "Pt")
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="python-pptx is required to generate PPTX output",
            details={"error": str(e)},
        )

    pages = ir.get("pages")
    if not isinstance(pages, list) or not pages:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR is missing pages[]",
        )

    first_page = pages[0] if isinstance(pages[0], dict) else None
    if not first_page:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR pages[0] is invalid",
        )

    text_erase_mode_id = str(text_erase_mode or "fill").strip().lower()
    if text_erase_mode_id not in {"smart", "fill"}:
        text_erase_mode_id = "fill"

    scanned_page_mode_id = str(scanned_page_mode or "segmented").strip().lower()
    if scanned_page_mode_id in {"chunk", "chunked", "split", "blocks"}:
        scanned_page_mode_id = "segmented"
    if scanned_page_mode_id in {"page", "full", "full_page"}:
        scanned_page_mode_id = "fullpage"
    if scanned_page_mode_id not in {"segmented", "fullpage"}:
        scanned_page_mode_id = "segmented"

    try:
        first_w_pt = float(first_page.get("page_width_pt") or 0.0)
        first_h_pt = float(first_page.get("page_height_pt") or 0.0)
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR page dimensions are invalid",
            details={"error": str(e)},
        )

    if first_w_pt <= 0 or first_h_pt <= 0:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="IR page dimensions are missing",
            details={"page_width_pt": first_w_pt, "page_height_pt": first_h_pt},
        )

    out_path = _as_path(output_pptx_path)
    _ensure_parent_dir(out_path)

    artifacts = (
        _as_path(artifacts_dir)
        if artifacts_dir is not None
        else (out_path.parent / "artifacts")
    )
    artifacts.mkdir(parents=True, exist_ok=True)

    prs = Presentation()

    if force_16x9:
        # 13.333" x 7.5" is the common widescreen (16:9) size.
        slide_w_emu = int(round(13.333 * _EMU_PER_INCH))
        slide_h_emu = int(round(7.5 * _EMU_PER_INCH))
    else:
        # Default: 1:1 mapping with PDF points (8.5x11 for letter, etc.).
        slide_w_emu = int(round(first_w_pt * _EMU_PER_PT))
        slide_h_emu = int(round(first_h_pt * _EMU_PER_PT))

    prs.slide_width = Emu(slide_w_emu)
    prs.slide_height = Emu(slide_h_emu)
    _set_slide_size_type(prs, slide_w_emu=slide_w_emu, slide_h_emu=slide_h_emu)

    blank_layout = prs.slide_layouts[6]
    source_pdf = _as_path(str(ir.get("source_pdf") or ""))
    total_pages = sum(1 for page in pages if isinstance(page, dict))
    done_pages = 0

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("page_index") or 0)
        page_w_pt = float(page.get("page_width_pt") or first_w_pt)
        page_h_pt = float(page.get("page_height_pt") or first_h_pt)

        transform = _build_transform(
            page_width_pt=page_w_pt,
            page_height_pt=page_h_pt,
            slide_width_emu=slide_w_emu,
            slide_height_emu=slide_h_emu,
        )

        slide = prs.slides.add_slide(blank_layout)
        has_text_layer = bool(page.get("has_text_layer"))
        page_elements = [el for el in (page.get("elements") or []) if isinstance(el, dict)]
        has_mineru_elements = any(
            str(el.get("source") or "").strip().lower() == "mineru"
            for el in page_elements
        )

        if not has_text_layer:
            overlay_scanned_image_crops = scanned_page_mode_id != "fullpage"
            # Scanned page strategy: render page image, erase OCR/image areas
            # in the render, then overlay cropped images + editable text.
            render_path = artifacts / "page_renders" / f"page-{page_index:04d}.png"
            pix = _render_pdf_page_png(
                source_pdf,
                page_index=page_index,
                dpi=int(scanned_render_dpi),
                out_path=render_path,
            )

            bg_left = int(round(transform.offset_x_emu))
            bg_top = int(round(transform.offset_y_emu))
            bg_w = int(round(page_w_pt * _EMU_PER_PT * transform.scale))
            bg_h = int(round(page_h_pt * _EMU_PER_PT * transform.scale))

            # Collect OCR text blocks + stats for heuristics.
            ocr_text_elements = [
                el
                for el in _iter_page_elements(page, type_name="text")
                if str(el.get("source") or "") == "ocr"
            ]
            baseline_ocr_h_pt = _estimate_baseline_ocr_line_height_pt(
                ocr_text_elements=ocr_text_elements,
                page_w_pt=float(page_w_pt),
            )

            def _text_coverage_ratio(bb: list[float]) -> tuple[float, int]:
                """Return (overlap_area_ratio, ocr_items_inside_count) for a bbox.

                Used to reject image-region candidates that are actually paragraph
                text blocks or card backgrounds. Coverage is computed against OCR
                text boxes in PDF point coordinates.
                """

                if not ocr_text_elements:
                    return (0.0, 0)
                try:
                    x0, y0, x1, y1 = _coerce_bbox_pt(bb)
                except Exception:
                    return (0.0, 0)
                area = float(max(1.0, (x1 - x0) * (y1 - y0)))
                # Expand OCR bboxes a bit to account for line spacing gaps,
                # which otherwise underestimates text coverage.
                pad = max(1.0, min(6.0, 0.18 * float(baseline_ocr_h_pt)))
                overlap = 0.0
                count = 0
                for tel in ocr_text_elements:
                    bbox_pt = tel.get("bbox_pt")
                    if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                        continue
                    try:
                        tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
                    except Exception:
                        continue
                    text_value = str(tel.get("text") or "")
                    if _is_inline_short_token(text_value):
                        continue

                    text_area = max(1.0, float((tx1 - tx0) * (ty1 - ty0)))
                    cx = (tx0 + tx1) / 2.0
                    cy = (ty0 + ty1) / 2.0

                    tx0 -= pad
                    ty0 -= pad
                    tx1 += pad
                    ty1 += pad
                    ix0 = max(x0, tx0)
                    iy0 = max(y0, ty0)
                    ix1 = min(x1, tx1)
                    iy1 = min(y1, ty1)
                    if ix1 <= ix0 or iy1 <= iy0:
                        continue
                    inter = float((ix1 - ix0) * (iy1 - iy0))
                    overlap += inter

                    center_inside = cx >= x0 and cx <= x1 and cy >= y0 and cy <= y1
                    if center_inside or (inter / text_area) >= 0.18:
                        count += 1
                overlap = min(overlap, area)
                return (float(overlap) / area, int(count))

            def _text_inside_counts(bb: list[float]) -> tuple[int, int]:
                """Return (items_inside_count, cjk_items_inside_count) for a bbox.

                This complements area-based coverage with linguistic hints so we can
                reject large mixed regions that accidentally swallow CJK body text.
                """

                if not ocr_text_elements:
                    return (0, 0)
                try:
                    x0, y0, x1, y1 = _coerce_bbox_pt(bb)
                except Exception:
                    return (0, 0)
                inside = 0
                cjk_inside = 0
                for tel in ocr_text_elements:
                    bbox_pt = tel.get("bbox_pt")
                    if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                        continue
                    try:
                        tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
                    except Exception:
                        continue
                    cx = (tx0 + tx1) / 2.0
                    cy = (ty0 + ty1) / 2.0
                    if cx < x0 or cx > x1 or cy < y0 or cy > y1:
                        continue

                    text_value = str(tel.get("text") or "")
                    if _is_inline_short_token(text_value):
                        continue

                    inside += 1
                    if _contains_cjk(text_value):
                        cjk_inside += 1
                return (int(inside), int(cjk_inside))

            has_full_page_bg_image = any(
                _is_near_full_page_bbox_pt(
                    el.get("bbox_pt"), page_w_pt=page_w_pt, page_h_pt=page_h_pt
                )
                for el in _iter_page_elements(page, type_name="image")
            )

            image_region_infos = _build_scanned_image_region_infos(
                page=page,
                render_path=render_path,
                artifacts_dir=artifacts,
                page_index=page_index,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
                scanned_render_dpi=int(scanned_render_dpi),
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                ocr_text_elements=ocr_text_elements,
                has_full_page_bg_image=has_full_page_bg_image,
                text_coverage_ratio_fn=_text_coverage_ratio,
                text_inside_counts_fn=_text_inside_counts,
            )
            ocr_text_elements = _filter_scanned_ocr_text_elements(
                ocr_text_elements=ocr_text_elements,
                image_region_infos=image_region_infos,
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            )
            ocr_text_elements = _dedupe_scanned_ocr_text_elements(
                ocr_text_elements=ocr_text_elements,
                baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            )

            # Build editable text items for scanned-page overlay. We first erase
            # OCR text in the rendered background image, then place cropped images
            # and editable text above it.

            text_erase_bboxes_pt: list[list[float]] = []
            text_items: list[tuple[dict[str, Any], list[float], str, tuple[int, int, int]]] = []
            is_fill_mode = text_erase_mode_id == "fill"

            for el in ocr_text_elements:
                bbox_pt = el.get("bbox_pt")
                try:
                    x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
                except Exception:
                    continue

                raw_text = str(el.get("text") or "")
                text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
                text = "\n".join([line.strip() for line in text.split("\n") if line.strip()]).strip()
                if not text:
                    continue

                bbox_w_pt = max(1.0, x1 - x0)
                bbox_h_pt = max(1.0, y1 - y0)

                # Sample the local background for masking.
                bg_rgb = _sample_bbox_background_rgb(
                    pix,
                    bbox_pt=[x0, y0, x1, y1],
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                )

                # Expand erase region to remove anti-aliased glyph halos.
                # Use anisotropic padding so line tails don't leave gray remnants.
                pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
                    bbox_h_pt=bbox_h_pt,
                    text_erase_mode=text_erase_mode_id,
                )
                text_erase_bboxes_pt.append(
                    [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
                )

                text_items.append((el, [x0, y0, x1, y1], text, bg_rgb))

            def _merge_text_erase_bboxes(
                boxes: list[list[float]], *, gap_pt: float
            ) -> list[list[float]]:
                """Merge nearby same-line erase boxes to improve wipe completeness."""

                merged = [list(_coerce_bbox_pt(bb)) for bb in boxes if isinstance(bb, list) and len(bb) == 4]
                if len(merged) <= 1:
                    return merged

                gap_pt = max(0.0, float(gap_pt))
                changed = True
                while changed:
                    changed = False
                    merged.sort(key=lambda b: (b[1], b[0]))
                    out: list[list[float]] = []
                    for bb in merged:
                        x0, y0, x1, y1 = _coerce_bbox_pt(bb)
                        did_merge = False
                        for i, ub in enumerate(out):
                            ux0, uy0, ux1, uy1 = _coerce_bbox_pt(ub)
                            y_overlap = min(y1, uy1) - max(y0, uy0)
                            min_h = max(1.0, min(y1 - y0, uy1 - uy0))
                            if y_overlap < (0.40 * min_h):
                                continue
                            if x0 > ux1:
                                x_gap = float(x0 - ux1)
                            elif ux0 > x1:
                                x_gap = float(ux0 - x1)
                            else:
                                x_gap = 0.0
                            if x_gap > gap_pt:
                                continue
                            out[i] = [
                                min(x0, ux0),
                                min(y0, uy0),
                                max(x1, ux1),
                                max(y1, uy1),
                            ]
                            did_merge = True
                            changed = True
                            break
                        if not did_merge:
                            out.append([x0, y0, x1, y1])
                    merged = out

                return merged

            if is_fill_mode:
                # For fill mode, prefer local boxes so color fill remains local,
                # but if OCR output is extremely fragmented (word-level boxes)
                # also add a mild merge pass to avoid "text ghosts" between
                # adjacent bboxes.
                erase_bboxes_for_background = list(text_erase_bboxes_pt)
                # AI OCR outputs can also leave small gaps between line boxes,
                # causing visible "double text" (residual background glyphs
                # + editable overlay). Apply a conservative merge for medium-
                # sized pages as well, but keep geometry guards so we don't
                # wipe across columns.
                if len(text_erase_bboxes_pt) >= 60:
                    merged_fill_bboxes_pt = _merge_text_erase_bboxes(
                        text_erase_bboxes_pt,
                        gap_pt=max(1.5, 0.42 * float(baseline_ocr_h_pt)),
                    )
                    for bb in merged_fill_bboxes_pt:
                        try:
                            mx0, my0, mx1, my1 = _coerce_bbox_pt(bb)
                        except Exception:
                            continue
                        if (mx1 - mx0) >= 0.92 * float(page_w_pt):
                            continue
                        if (my1 - my0) >= 3.8 * float(baseline_ocr_h_pt):
                            continue
                        erase_bboxes_for_background.append([mx0, my0, mx1, my1])
            else:
                merged_text_erase_bboxes_pt = _merge_text_erase_bboxes(
                    text_erase_bboxes_pt,
                    gap_pt=max(2.0, 0.75 * float(baseline_ocr_h_pt)),
                )
                # Keep both merged and original line boxes. Merged boxes improve wipe
                # continuity, while raw line boxes help detect and force-clean local
                # leftovers that can still cause visible text overlap.
                erase_bboxes_for_background = (
                    list(merged_text_erase_bboxes_pt) + list(text_erase_bboxes_pt)
                )

            # 1) Background image (after erase)
            protect_bboxes_for_erase: list[list[float]] = []
            for info in image_region_infos:
                if not info.shape_confirmed:
                    continue
                try:
                    ix0, iy0, ix1, iy1 = _coerce_bbox_pt(info.bbox_pt)
                except Exception:
                    continue
                iw = float(ix1 - ix0)
                ih = float(iy1 - iy0)
                area_ratio = max(0.0, iw * ih) / max(1.0, float(page_w_pt) * float(page_h_pt))
                # Only protect clearly image-dominant regions. Small icon-like crops
                # often overlap heading/text bboxes and can block text cleanup.
                if area_ratio < 0.030:
                    continue
                protect_bboxes_for_erase.append([ix0, iy0, ix1, iy1])

            cleaned_render_path = _erase_regions_in_render_image(
                render_path,
                out_path=artifacts / "page_renders" / f"page-{page_index:04d}.clean.png",
                # Erase OCR text only. Do NOT erase image regions in the background:
                # image crops are overlaid later, and region erase can introduce
                # large inpaint artifacts on complex templates.
                erase_bboxes_pt=erase_bboxes_for_background,
                # Never modify pixels inside confirmed *large* image crops.
                protect_bboxes_pt=protect_bboxes_for_erase,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
                text_erase_mode=text_erase_mode_id,
            )

            if overlay_scanned_image_crops:
                # If icon-like crops use transparent background, clear their original
                # background area from the base render first to avoid double-background.
                transparent_bg_regions = [
                    info.bbox_pt for info in image_region_infos if info.background_removed
                ]
                if transparent_bg_regions:
                    cleaned_render_path = _clear_regions_for_transparent_crops(
                        cleaned_render_path=cleaned_render_path,
                        out_path=artifacts
                        / "page_renders"
                        / f"page-{page_index:04d}.clean.icons-bg-cleared.png",
                        regions_pt=transparent_bg_regions,
                        pix=pix,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                    )

            slide.shapes.add_picture(
                str(cleaned_render_path), Emu(bg_left), Emu(bg_top), Emu(bg_w), Emu(bg_h)
            )

            # 2) Cropped images
            if overlay_scanned_image_crops:
                for info in image_region_infos:
                    try:
                        left, top, width, height = _bbox_pt_to_slide_emu(
                            info.bbox_pt, transform=transform
                        )
                    except Exception:
                        continue
                    if width <= 0 or height <= 0:
                        continue
                    slide.shapes.add_picture(
                        str(info.crop_path), Emu(left), Emu(top), Emu(width), Emu(height)
                    )

            # 3) Editable text boxes.
            for el, bbox_pt, text, (r, g, b) in text_items:
                try:
                    left, top, width, height = _bbox_pt_to_slide_emu(
                        bbox_pt, transform=transform
                    )
                except Exception:
                    continue
                if width <= 0 or height <= 0:
                    continue

                x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
                bbox_w_pt = max(1.0, x1 - x0)
                bbox_h_pt = max(1.0, y1 - y0)

                # Heading detection: big text near the top.
                is_heading = (
                    y0 <= 0.22 * float(page_h_pt)
                    and bbox_h_pt >= 1.6 * float(baseline_ocr_h_pt)
                    and len(text) <= 40
                )

                # We'll nudge OCR text boxes slightly upward and extend their
                # height by a tiny amount (see below). Feed that slack into the
                # font-fitting step so we don't pick an overly small font.
                fit_bbox_h_pt = float(bbox_h_pt) + float(min(1.2, 0.06 * float(bbox_h_pt)))

                # IMPORTANT: decide wrapping based on the *original* OCR bbox.
                # The extra fit slack is only for font fitting; using it for the
                # wrap decision can cause spurious breaks (e.g. putting "：" on
                # its own line) on slightly padded single-line headings.
                wrap_hint = _prefer_wrap_for_ocr_text(
                    text=text,
                    bbox_w_pt=bbox_w_pt,
                    bbox_h_pt=bbox_h_pt,
                    baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                )

                text_to_render, font_size_pt, wrap = _fit_ocr_text_style(
                    text=text,
                    bbox_w_pt=bbox_w_pt,
                    bbox_h_pt=fit_bbox_h_pt,
                    baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                    is_heading=bool(is_heading),
                    wrap_override=wrap_hint,
                )
                if not text_to_render.strip():
                    continue

                # OCR text in Office/WPS usually appears slightly lower than image-rendered
                # glyphs due to font ascent metrics. Nudge up a tiny amount.
                nudge_up_pt = min(
                    2.2,
                    max(
                        0.6,
                        0.08 * float(bbox_h_pt),
                        0.10 * float(font_size_pt),
                    ),
                )
                nudge_emu = int(round(float(nudge_up_pt) * _EMU_PER_PT * transform.scale))
                textbox_top = max(0, int(top) - nudge_emu)
                textbox_height = int(height) + nudge_emu

                # Add right-side tolerance to avoid last-char unexpected wraps
                # caused by viewer/font metric differences.
                if wrap:
                    nudge_right_pt = min(3.2, max(1.2, 0.07 * float(bbox_h_pt)))
                else:
                    # Single-line text is where Office/WPS most often re-wraps one
                    # trailing character. Keep a larger right guard in this case.
                    nudge_right_pt = min(
                        8.0,
                        max(
                            3.0,
                            0.16 * float(bbox_h_pt),
                            0.50 * float(font_size_pt),
                        ),
                    )
                nudge_right_emu = int(round(float(nudge_right_pt) * _EMU_PER_PT * transform.scale))
                textbox_left = int(left)
                textbox_width = int(width) + nudge_right_emu
                max_box_w = max(1, int(slide_w_emu) - textbox_left)
                textbox_width = max(1, min(textbox_width, max_box_w))

                tx = slide.shapes.add_textbox(
                    Emu(textbox_left), Emu(textbox_top), Emu(textbox_width), Emu(textbox_height)
                )
                tx.fill.background()
                tx.line.fill.background()
                tf = tx.text_frame
                # Keep top alignment so OCR bboxes map visually (WPS/Office differ
                # on default vertical anchoring).
                try:
                    tf.vertical_anchor = MSO_ANCHOR.TOP
                except Exception:
                    pass
                # We insert explicit line breaks when wrapping is needed. Keeping
                # `word_wrap=True` lets Office/WPS reflow text differently across
                # platforms/fonts (often moving a trailing punctuation like "："
                # onto its own line). Disable auto wrapping for more stable
                # scan-to-PPT visual fidelity.
                tf.word_wrap = False
                # Disable viewer auto-size to reduce text-box drift between Office/WPS.
                tf.auto_size = MSO_AUTO_SIZE.NONE
                tf.margin_left = 0
                tf.margin_right = 0
                tf.margin_top = 0
                tf.margin_bottom = 0
                tf.text = text_to_render

                for p in tf.paragraphs:
                    try:
                        if is_heading:
                            p.alignment = PP_ALIGN.CENTER
                    except Exception:
                        pass
                    # Reduce unexpected spacing differences across viewers.
                    try:
                        p.space_before = Pt(0)
                        p.space_after = Pt(0)
                    except Exception:
                        pass
                    try:
                        p.line_spacing = 1.0
                    except Exception:
                        pass

                    for run in p.runs:
                        font = run.font
                        font.size = Pt(float(font_size_pt))
                        if _contains_cjk(text):
                            font.name = "Microsoft YaHei"
                        else:
                            font.name = _map_font_name(el.get("font_name")) or "Arial"
                        font.bold = True if is_heading else (bool(el.get("bold")) if "bold" in el else None)
                        font.italic = bool(el.get("italic")) if "italic" in el else None

                        rgb = _hex_to_rgb(el.get("color"))
                        if rgb is None:
                            rgb = (
                                (0, 0, 0)
                                if (0.2126 * r + 0.7152 * g + 0.0722 * b) >= 128
                                else (255, 255, 255)
                            )
                        else:
                            dr = int(rgb[0]) - int(r)
                            dg = int(rgb[1]) - int(g)
                            db = int(rgb[2]) - int(b)
                            if (dr * dr + dg * dg + db * db) < (35 * 35):
                                rgb = (
                                    (0, 0, 0)
                                    if (0.2126 * r + 0.7152 * g + 0.0722 * b) >= 128
                                    else (255, 255, 255)
                                )
                        font.color.rgb = RGBColor(*rgb)

            _export_final_preview_page_image(
                page=page,
                page_index=page_index,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
                source_pdf=source_pdf,
                artifacts_dir=artifacts,
                dpi=int(scanned_render_dpi),
                scanned_image_region_crops=[
                    (list(info.bbox_pt), info.crop_path) for info in image_region_infos
                ]
                if overlay_scanned_image_crops
                else [],
            )
            continue

        # Text-based page: place elements directly.
        mineru_background_placed = False
        mineru_render_pix: Any | None = None
        if has_mineru_elements and source_pdf.exists():
            try:
                render_path = artifacts / "page_renders" / f"page-{page_index:04d}.mineru.png"
                mineru_render_pix = _render_pdf_page_png(
                    source_pdf,
                    page_index=page_index,
                    dpi=int(scanned_render_dpi),
                    out_path=render_path,
                )

                text_erase_bboxes_pt: list[list[float]] = []
                protect_bboxes_pt: list[list[float]] = []

                for el in _iter_page_elements(page, type_name="text"):
                    if str(el.get("source") or "").strip().lower() != "mineru":
                        continue
                    try:
                        x0, y0, x1, y1 = _coerce_bbox_pt(el.get("bbox_pt"))
                    except Exception:
                        continue
                    bbox_h_pt = max(1.0, y1 - y0)
                    pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
                        bbox_h_pt=bbox_h_pt,
                        text_erase_mode=text_erase_mode_id,
                    )
                    text_erase_bboxes_pt.append(
                        [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt]
                    )

                for el in _iter_page_elements(page, type_name="image"):
                    if str(el.get("source") or "").strip().lower() != "mineru":
                        continue
                    try:
                        ix0, iy0, ix1, iy1 = _coerce_bbox_pt(el.get("bbox_pt"))
                    except Exception:
                        continue
                    protect_bboxes_pt.append([ix0, iy0, ix1, iy1])

                cleaned_render_path = _erase_regions_in_render_image(
                    render_path,
                    out_path=artifacts / "page_renders" / f"page-{page_index:04d}.mineru.clean.png",
                    erase_bboxes_pt=text_erase_bboxes_pt,
                    protect_bboxes_pt=protect_bboxes_pt,
                    page_height_pt=page_h_pt,
                    dpi=int(scanned_render_dpi),
                    text_erase_mode=text_erase_mode_id,
                )

                bg_left = int(round(transform.offset_x_emu))
                bg_top = int(round(transform.offset_y_emu))
                bg_w = int(round(page_w_pt * _EMU_PER_PT * transform.scale))
                bg_h = int(round(page_h_pt * _EMU_PER_PT * transform.scale))
                slide.shapes.add_picture(
                    str(cleaned_render_path), Emu(bg_left), Emu(bg_top), Emu(bg_w), Emu(bg_h)
                )
                mineru_background_placed = True
            except Exception:
                mineru_background_placed = False
                mineru_render_pix = None

        for el in _iter_page_elements(page, type_name="image"):
            bbox_pt = el.get("bbox_pt")
            image_path = el.get("image_path")
            if not image_path:
                continue
            img_path = _as_path(str(image_path))
            if not img_path.is_absolute():
                candidate = artifacts / img_path
                if candidate.exists():
                    img_path = candidate
            if not img_path.exists():
                continue
            try:
                left, top, width, height = _bbox_pt_to_slide_emu(
                    bbox_pt, transform=transform
                )
            except Exception:
                continue
            slide.shapes.add_picture(
                str(img_path), Emu(left), Emu(top), Emu(width), Emu(height)
            )

        for el in _iter_page_elements(page, type_name="table"):
            bbox_pt = el.get("bbox_pt")
            try:
                rows = int(el.get("rows") or 0)
                cols = int(el.get("cols") or 0)
            except Exception:
                rows, cols = 0, 0
            if rows <= 0 or cols <= 0:
                continue
            try:
                left, top, width, height = _bbox_pt_to_slide_emu(
                    bbox_pt, transform=transform
                )
            except Exception:
                continue

            table_shape = slide.shapes.add_table(
                rows, cols, Emu(left), Emu(top), Emu(width), Emu(height)
            )
            table = table_shape.table

            # Best-effort column/row sizing from cell bboxes if available.
            cells = el.get("cells") or []
            if isinstance(cells, list) and cells:
                col_widths_pt = [0.0 for _ in range(cols)]
                row_heights_pt = [0.0 for _ in range(rows)]
                for cell in cells:
                    if not isinstance(cell, dict):
                        continue
                    r = int(cell.get("r") or 0)
                    c = int(cell.get("c") or 0)
                    if r < 0 or r >= rows or c < 0 or c >= cols:
                        continue
                    try:
                        x0, y0, x1, y1 = _coerce_bbox_pt(cell.get("bbox_pt"))
                    except Exception:
                        continue
                    col_widths_pt[c] = max(col_widths_pt[c], x1 - x0)
                    row_heights_pt[r] = max(row_heights_pt[r], y1 - y0)

                # Fall back to uniform sizing when bbox data is missing/degenerate.
                if sum(col_widths_pt) <= 0:
                    col_widths_pt = [page_w_pt / cols for _ in range(cols)]
                if sum(row_heights_pt) <= 0:
                    row_heights_pt = [page_h_pt / rows for _ in range(rows)]

                col_widths_emu = [
                    int(round(w * _EMU_PER_PT * transform.scale)) for w in col_widths_pt
                ]
                row_heights_emu = [
                    int(round(h * _EMU_PER_PT * transform.scale))
                    for h in row_heights_pt
                ]

                # Adjust last row/col to account for rounding so totals match table bbox.
                if col_widths_emu:
                    col_widths_emu[-1] += int(width - sum(col_widths_emu))
                if row_heights_emu:
                    row_heights_emu[-1] += int(height - sum(row_heights_emu))

                for c, w in enumerate(col_widths_emu):
                    table.columns[c].width = Emu(max(0, w))
                for r, h in enumerate(row_heights_emu):
                    table.rows[r].height = Emu(max(0, h))

                for cell in cells:
                    if not isinstance(cell, dict):
                        continue
                    r = int(cell.get("r") or 0)
                    c = int(cell.get("c") or 0)
                    if r < 0 or r >= rows or c < 0 or c >= cols:
                        continue
                    text = str(cell.get("text") or "")
                    table.cell(r, c).text = text
            else:
                # No structured cells; leave empty for now.
                pass

        for el in _iter_page_elements(page, type_name="text"):
            bbox_pt = el.get("bbox_pt")
            try:
                left, top, width, height = _bbox_pt_to_slide_emu(
                    bbox_pt, transform=transform
                )
            except Exception:
                continue

            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
            source_id = str(el.get("source") or "").strip().lower()
            is_mineru_text = source_id == "mineru"
            is_ocr_text = source_id == "ocr"
            raw_text = str(el.get("text") or "")
            text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            if is_mineru_text:
                text = "\n".join([line.strip() for line in text.split("\n") if line.strip()]).strip()
            elif is_ocr_text:
                text = _normalize_ocr_text_for_render(text)
            else:
                text = text.replace("\n", " ").strip()
            if not text:
                continue

            tx = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
            tf = tx.text_frame
            bbox_w_pt = max(1.0, x1 - x0)
            bbox_h_pt = max(1.0, y1 - y0)
            text_to_render = text
            sampled_bg_rgb: tuple[int, int, int] | None = None
            sampled_text_rgb: tuple[int, int, int] | None = None
            if is_mineru_text:
                mineru_block_type = str(el.get("mineru_block_type") or "").strip().lower()
                is_bullet_like = text.lstrip().startswith(("-", "•", "·", "●"))
                plain_len = len(text.replace("\n", ""))
                text_level_raw = el.get("mineru_text_level")
                try:
                    text_level = int(text_level_raw)
                except Exception:
                    text_level = None
                is_heading = bool(
                    mineru_block_type in {"title", "heading", "header", "h1", "h2"}
                ) or (
                    (
                        text_level is not None
                        and text_level <= 2
                        and plain_len <= 60
                    )
                    or (
                        y0 <= 0.22 * float(page_h_pt)
                        and bbox_h_pt >= 18.0
                        and plain_len <= 56
                        and not is_bullet_like
                    )
                )
                # Distinguish page hero title vs card/section titles by geometry.
                is_primary_heading = bool(
                    is_heading
                    and y0 <= 0.16 * float(page_h_pt)
                    and bbox_w_pt >= 0.34 * float(page_w_pt)
                )

                # For non-heading text, always fit with wrapping. For heading text,
                # allow wrapping when it materially improves usable size.
                wrap_for_fit = bool(not is_heading)
                max_body_pt = min(
                    96.0 if is_primary_heading else 72.0,
                    max(7.0, (0.98 if is_heading else 0.94) * float(bbox_h_pt)),
                )
                min_body_pt = 6.0
                prefit_font_size_pt: float | None = None

                if is_heading and (not is_primary_heading) and plain_len >= 14:
                    single_line_pt = _fit_font_size_pt(
                        text,
                        bbox_w_pt=bbox_w_pt,
                        bbox_h_pt=bbox_h_pt,
                        wrap=False,
                        min_pt=min_body_pt,
                        max_pt=max_body_pt,
                        width_fit_ratio=1.00,
                        height_fit_ratio=0.995,
                    )
                    wrapped_pt = _fit_font_size_pt(
                        text,
                        bbox_w_pt=bbox_w_pt,
                        bbox_h_pt=bbox_h_pt,
                        wrap=True,
                        min_pt=min_body_pt,
                        max_pt=max_body_pt,
                        width_fit_ratio=1.01,
                        height_fit_ratio=0.96,
                    )
                    wrapped_lines, _ = _measure_text_lines(
                        text,
                        max_width_pt=max(1.0, 0.99 * bbox_w_pt),
                        font_size_pt=float(wrapped_pt),
                        wrap=True,
                    )
                    if (
                        wrapped_lines >= 2
                        and wrapped_lines <= 3
                        and wrapped_pt >= max(single_line_pt + 1.2, 1.18 * single_line_pt)
                    ):
                        wrap_for_fit = True
                        prefit_font_size_pt = float(wrapped_pt)
                    else:
                        wrap_for_fit = False
                        prefit_font_size_pt = float(single_line_pt)

                if prefit_font_size_pt is not None:
                    font_size_pt = float(prefit_font_size_pt)
                else:
                    font_size_pt = _fit_font_size_pt(
                        text,
                        bbox_w_pt=bbox_w_pt,
                        bbox_h_pt=bbox_h_pt,
                        wrap=wrap_for_fit,
                        min_pt=min_body_pt,
                        max_pt=max_body_pt,
                        width_fit_ratio=1.01 if wrap_for_fit else 1.00,
                        height_fit_ratio=0.96 if wrap_for_fit else 0.995,
                    )
                if wrap_for_fit:
                    # Lock explicit line breaks so Office/WPS viewers don't
                    # reflow CJK text differently and cause overlap/shift.
                    for _ in range(12):
                        candidate_text = _wrap_text_to_width(
                            text,
                            max_width_pt=max(1.0, 1.01 * bbox_w_pt),
                            font_size_pt=float(font_size_pt),
                        )
                        candidate_lines = [
                            line
                            for line in candidate_text.splitlines()
                            if line.strip()
                        ]
                        if not candidate_lines:
                            candidate_lines = [text]
                            candidate_text = text
                        line_height = 1.18 if _contains_cjk(text) else 1.15
                        total_h = float(len(candidate_lines)) * float(font_size_pt) * line_height
                        if total_h <= (0.985 * bbox_h_pt):
                            text_to_render = candidate_text
                            break
                        font_size_pt = max(float(min_body_pt), float(font_size_pt) - 0.35)
                    else:
                        text_to_render = candidate_text if candidate_text else text
                wrap = bool(wrap_for_fit)
            elif is_ocr_text:
                compact_len = _compact_text_length(text)
                is_heading = bool(
                    y0 <= 0.20 * float(page_h_pt)
                    and bbox_h_pt >= 1.45 * float(baseline_ocr_h_pt)
                    and compact_len <= 56
                )
                text_to_render, font_size_pt, wrap = _fit_ocr_text_style(
                    text=text,
                    bbox_w_pt=bbox_w_pt,
                    bbox_h_pt=bbox_h_pt,
                    baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                    is_heading=is_heading,
                )

                if has_text_layer and source_pdf.exists() and (mineru_render_pix is not None):
                    try:
                        sampled_bg_rgb = _sample_bbox_background_rgb(
                            mineru_render_pix,
                            bbox_pt=bbox_pt,
                            page_height_pt=page_h_pt,
                            dpi=int(scanned_render_dpi),
                        )
                        sampled_text_rgb = _sample_bbox_text_rgb(
                            mineru_render_pix,
                            bbox_pt=bbox_pt,
                            page_height_pt=page_h_pt,
                            dpi=int(scanned_render_dpi),
                            bg_rgb=sampled_bg_rgb,
                        )
                    except Exception:
                        sampled_bg_rgb = None
                        sampled_text_rgb = None
            else:
                wrap = False
                font_size_pt = _infer_font_size_pt(el, bbox_h_pt=bbox_h_pt)
                is_heading = False

            tf.word_wrap = bool(wrap)
            if is_mineru_text:
                tf.auto_size = MSO_AUTO_SIZE.NONE
                try:
                    tf.vertical_anchor = MSO_ANCHOR.TOP
                except Exception:
                    pass
            else:
                tf.auto_size = MSO_AUTO_SIZE.NONE
            tf.margin_left = 0
            tf.margin_right = 0
            tf.margin_top = 0
            tf.margin_bottom = 0
            tf.text = text_to_render

            if is_mineru_text:
                for p in tf.paragraphs:
                    try:
                        if is_primary_heading:
                            p.alignment = PP_ALIGN.CENTER
                    except Exception:
                        pass
                    try:
                        p.line_spacing = 1.0
                        p.space_before = Pt(0)
                        p.space_after = Pt(0)
                    except Exception:
                        pass

            mapped_font = _map_font_name(el.get("font_name"))
            rgb = _hex_to_rgb(el.get("color"))
            if is_mineru_text and mineru_render_pix is not None:
                try:
                    sampled_bg_rgb = _sample_bbox_background_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                    )
                    sampled_text_rgb = _sample_bbox_text_rgb(
                        mineru_render_pix,
                        bbox_pt=bbox_pt,
                        page_height_pt=page_h_pt,
                        dpi=int(scanned_render_dpi),
                        bg_rgb=sampled_bg_rgb,
                    )
                except Exception:
                    sampled_bg_rgb = None
                    sampled_text_rgb = None
            elif is_ocr_text and sampled_bg_rgb is None and has_text_layer and source_pdf.exists():
                # Best-effort local color sampling for OCR elements on text-layer pages.
                # Reuse mineru render when available (already aligned to source PDF).
                if mineru_render_pix is not None:
                    try:
                        sampled_bg_rgb = _sample_bbox_background_rgb(
                            mineru_render_pix,
                            bbox_pt=bbox_pt,
                            page_height_pt=page_h_pt,
                            dpi=int(scanned_render_dpi),
                        )
                        sampled_text_rgb = _sample_bbox_text_rgb(
                            mineru_render_pix,
                            bbox_pt=bbox_pt,
                            page_height_pt=page_h_pt,
                            dpi=int(scanned_render_dpi),
                            bg_rgb=sampled_bg_rgb,
                        )
                    except Exception:
                        sampled_bg_rgb = None
                        sampled_text_rgb = None
            if rgb is None and sampled_bg_rgb is not None:
                if sampled_text_rgb is not None:
                    rgb = sampled_text_rgb
                else:
                    rgb = _pick_contrasting_text_rgb(sampled_bg_rgb)
            elif rgb is not None and sampled_bg_rgb is not None:
                # If upstream color is too close to local background, prioritize
                # readability in the exported PPT.
                if _rgb_sq_distance(rgb, sampled_bg_rgb) < (32 * 32):
                    if sampled_text_rgb is not None:
                        rgb = sampled_text_rgb
                    else:
                        rgb = _pick_contrasting_text_rgb(sampled_bg_rgb)
            applied = False
            for p in tf.paragraphs:
                for run in p.runs:
                    font = run.font
                    font.size = Pt(float(font_size_pt))
                    if mapped_font:
                        font.name = mapped_font
                    elif is_mineru_text:
                        font.name = "Microsoft YaHei" if _contains_cjk(text_to_render) else "Arial"
                    elif is_ocr_text:
                        font.name = "Microsoft YaHei" if _contains_cjk(text_to_render) else "Arial"
                    font.bold = bool(el.get("bold")) if "bold" in el else None
                    font.italic = bool(el.get("italic")) if "italic" in el else None
                    if rgb:
                        font.color.rgb = RGBColor(*rgb)
                    applied = True

            if not applied:
                continue

        _export_final_preview_page_image(
            page=page,
            page_index=page_index,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            source_pdf=source_pdf,
            artifacts_dir=artifacts,
            dpi=int(scanned_render_dpi),
        )
        done_pages += 1
        if progress_callback:
            try:
                progress_callback(done_pages, max(1, total_pages))
            except Exception:
                pass

    prs.save(str(out_path))
    return out_path
