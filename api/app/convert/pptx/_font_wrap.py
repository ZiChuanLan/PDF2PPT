"""Text wrapping and line measurement helpers (extracted from font_utils.py)."""

from __future__ import annotations

from ..ocr.utils import _contains_cjk
from ._font_measure import _measure_text_width_pt


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
    if not para:
        return []

    if (not _contains_cjk(para)) and (" " in para):
        tokens: list[str] = []
        parts = [p for p in para.split(" ") if p != ""]
        for i, part in enumerate(parts):
            if i > 0:
                tokens.append(" ")
            tokens.append(part)
        return tokens

    def _is_ascii_word_char(ch: str) -> bool:
        return bool(ch) and ch.isascii() and (ch.isalnum() or ch in "_-./:+#%&@")

    out: list[str] = []
    i = 0
    n = len(para)
    while i < n:
        ch = para[i]
        if ch.isspace():
            if not out or out[-1] != " ":
                out.append(" ")
            i += 1
            continue
        if _is_ascii_word_char(ch):
            j = i + 1
            while j < n and _is_ascii_word_char(para[j]):
                j += 1
            out.append(para[i:j])
            i = j
            continue
        out.append(ch)
        i += 1

    return out


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
        token_w = _token_width_pt(
            token, font_size_pt=font_size_pt, prefer_cjk=prefer_cjk
        )
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


def _wrap_text_to_width(text: str, *, max_width_pt: float, font_size_pt: float) -> str:
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


def _split_heading_text_after_colon(text: str) -> str:
    """Split heading text at the first colon when it has a meaningful tail."""
    normalized = _normalize_ocr_text_for_render(text)
    if not normalized or "\n" in normalized:
        return normalized

    def _has_ascii_alpha(s: str) -> bool:
        return any(ch.isascii() and ch.isalpha() for ch in (s or ""))

    for sep in ("：", ":"):
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
            "（" in left_part and "）" in left_part
        )
        right_has_paren = ("(" in right_part and ")" in right_part) or (
            "（" in right_part and "）" in right_part
        )
        right_has_struct_tail = any(
            token in right_part for token in ("/", "&", "+", "、")
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
