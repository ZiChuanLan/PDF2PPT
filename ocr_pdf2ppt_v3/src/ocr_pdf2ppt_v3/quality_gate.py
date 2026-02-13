from __future__ import annotations

import re

from .models import OcrLine, OcrQualityStats


_NOISE_CHARS = set("`~|_=<>[]{}\\/^")


def contains_cjk(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0xF900 <= code <= 0xFAFF
        ):
            return True
    return False


def text_noise_ratio(text: str) -> float:
    compact = [ch for ch in str(text or "") if not ch.isspace()]
    if not compact:
        return 1.0
    noisy_count = sum(1 for ch in compact if ch in _NOISE_CHARS)
    return float(noisy_count) / float(len(compact))


def sanitize_lines(
    *,
    lines: list[OcrLine],
    width: int,
    height: int,
    source: str,
) -> list[OcrLine]:
    page_area = float(max(1, width * height))
    cleaned: list[OcrLine] = []
    dedup: set[tuple[str, int, int, int, int]] = set()

    for line in lines:
        text = str(line.text or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = [float(v) for v in line.bbox]
        box_w = max(1.0, x1 - x0)
        box_h = max(1.0, y1 - y0)

        area_ratio = (box_w * box_h) / page_area
        width_ratio = box_w / max(1.0, float(width))
        height_ratio = box_h / max(1.0, float(height))
        noise_ratio = text_noise_ratio(text)

        has_cjk = contains_cjk(text)
        has_long_lowercase = re.search(r"[a-z]{4,}", text) is not None
        has_suspicious_ascii_mix = bool(
            re.search(r"[A-Za-z]{2,}[^A-Za-z0-9\s]+[A-Za-z]{2,}", text)
            or re.search(r"[A-Za-z0-9][|_=]{1,}[A-Za-z0-9]", text)
        )

        confidence = line.confidence
        if confidence is not None:
            confidence = max(0.0, min(1.0, float(confidence)))

        compact_chars = [ch for ch in text if not ch.isspace()]
        ascii_chars = sum(1 for ch in compact_chars if ord(ch) < 128)
        ascii_ratio = float(ascii_chars) / float(max(1, len(compact_chars)))

        if confidence is not None and confidence < 0.08:
            continue
        if len(compact_chars) >= 8 and ascii_ratio > 0.85 and (confidence is None or confidence < 0.72):
            continue
        if has_cjk and ascii_ratio >= 0.62 and len(compact_chars) >= 10:
            continue
        if has_suspicious_ascii_mix and (confidence is None or confidence < 0.94):
            continue
        if len(text) <= 1 and (confidence is None or confidence < 0.72):
            continue
        if noise_ratio > 0.26 and (confidence is None or confidence < 0.90):
            continue
        if has_cjk and has_long_lowercase and (confidence is None or confidence < 0.88):
            continue
        if area_ratio > 0.18 and len(text) >= 10 and (confidence is None or confidence < 0.92):
            continue
        if width_ratio > 0.72 and len(text) >= 16 and (confidence is None or confidence < 0.95):
            continue
        if height_ratio > 0.16 and len(text) >= 8 and (confidence is None or confidence < 0.95):
            continue

        key = (
            text,
            int(round(x0)),
            int(round(y0)),
            int(round(x1)),
            int(round(y1)),
        )
        if key in dedup:
            continue
        dedup.add(key)
        cleaned.append(
            OcrLine(
                text=text,
                bbox=[x0, y0, x1, y1],
                confidence=confidence,
                source=line.source,
                group_id=line.group_id,
                group_bbox=line.group_bbox,
            )
        )

    cleaned.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
    return cleaned


def assess_quality(
    *,
    lines: list[OcrLine],
    width: int,
    height: int,
) -> tuple[bool, str, OcrQualityStats]:
    total = len(lines)
    if total <= 0:
        return True, "empty", OcrQualityStats(total=0)

    page_area = float(max(1, width * height))
    low_conf = 0
    noisy = 0
    too_wide = 0
    too_tall = 0
    coverage = 0.0

    for line in lines:
        text = str(line.text or "").strip()
        x0, y0, x1, y1 = [float(v) for v in line.bbox]
        box_w = max(1.0, x1 - x0)
        box_h = max(1.0, y1 - y0)

        coverage += (box_w * box_h) / page_area
        if line.confidence is not None and float(line.confidence) < 0.55:
            low_conf += 1
        if text_noise_ratio(text) > 0.26:
            noisy += 1
        if box_w / max(1.0, float(width)) > 0.72:
            too_wide += 1
        if box_h / max(1.0, float(height)) > 0.16:
            too_tall += 1

    stats = OcrQualityStats(
        total=total,
        low_conf=low_conf,
        noisy=noisy,
        too_wide=too_wide,
        too_tall=too_tall,
        coverage=round(coverage, 4),
    )

    if total >= 6 and noisy / float(total) >= 0.45:
        return True, "noisy_text", stats
    if too_wide >= max(2, total // 4):
        return True, "too_wide_boxes", stats
    if too_tall >= max(2, total // 4):
        return True, "too_tall_boxes", stats
    if total >= 6 and low_conf / float(total) >= 0.65:
        return True, "low_confidence", stats
    if coverage > 0.42:
        return True, "over_coverage", stats
    return False, "ok", stats
