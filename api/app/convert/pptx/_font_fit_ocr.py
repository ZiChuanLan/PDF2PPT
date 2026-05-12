"""OCR text style fitting (split from font_utils.py).

Contains _prefer_wrap_for_ocr_text(), _resolve_visual_wrap_override_for_ocr_text(),
and _fit_ocr_text_style() for scanned-page OCR text boxes.
"""

from __future__ import annotations

from ..ocr.utils import _contains_cjk


def _prefer_wrap_for_ocr_text(
    *,
    text: str,
    bbox_w_pt: float,
    bbox_h_pt: float,
    baseline_ocr_h_pt: float,
) -> bool:
    """Heuristic wrap decision for scanned OCR text."""
    # Deferred imports to avoid circular dependency.
    from .font_utils import _compact_text_length

    compact_len = _compact_text_length(text)
    if compact_len <= 0:
        return False
    if "\n" in text:
        return True

    w = max(1.0, float(bbox_w_pt))
    h = max(1.0, float(bbox_h_pt))
    baseline = max(4.0, float(baseline_ocr_h_pt))

    if h <= max(1.45 * baseline, 10.5) and compact_len <= 120:
        return False

    width_pressure = float(compact_len) / max(1.0, w)
    est_lines_by_height = max(1, int(round(h / max(8.0, 1.10 * baseline))))

    if est_lines_by_height >= 2:
        return True

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


def _resolve_visual_wrap_override_for_ocr_text(
    *,
    visual_line_count: int | None,
    compact_len: int,
    bbox_h_pt: float,
    baseline_ocr_h_pt: float,
    is_heading: bool,
) -> bool | None:
    """Resolve whether source-pixel line counting should override OCR wrap."""
    if not isinstance(visual_line_count, int) or visual_line_count < 1:
        return None

    if visual_line_count >= 2:
        return True if int(compact_len) >= 12 else None

    if is_heading:
        return False

    compact_len = max(0, int(compact_len))
    bbox_h_pt = max(0.0, float(bbox_h_pt))
    baseline = max(4.0, float(baseline_ocr_h_pt))

    if compact_len >= 28:
        return None
    if compact_len >= 18 and bbox_h_pt >= max(1.10 * baseline, 10.0):
        return None
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
    """Return (text_to_render, font_size_pt, wrap) for OCR text boxes."""
    # Deferred imports to avoid circular dependency.
    from ._font_wrap import _wrap_text_to_width

    from .font_utils import (
        _compact_text_length,
        _fit_font_size_pt,
        _normalize_ocr_text_for_render,
    )

    normalized = _normalize_ocr_text_for_render(text)
    if not normalized:
        return ("", 6.0, False)

    compact_len = _compact_text_length(normalized)
    line_height = 1.18 if _contains_cjk(normalized) else 1.15

    bbox_w_pt = max(1.0, float(bbox_w_pt))
    bbox_h_pt = max(1.0, float(bbox_h_pt))
    baseline_ocr_h_pt = max(4.0, float(baseline_ocr_h_pt))

    min_pt = max(5.0, min(8.0, 0.52 * float(baseline_ocr_h_pt)))
    max_pt = min(
        84.0 if is_heading else 54.0,
        max(7.0, float(bbox_h_pt) * (0.98 if is_heading else 0.94)),
    )

    def _fit_single_candidate(
        *,
        max_pt_override: float | None = None,
        height_fit_ratio: float = 0.995,
    ) -> tuple[str, float, int, float]:
        resolved_max_pt = (
            float(max_pt)
            if max_pt_override is None
            else max(float(min_pt), float(max_pt_override))
        )
        font_size_pt = _fit_font_size_pt(
            normalized,
            bbox_w_pt=float(bbox_w_pt),
            bbox_h_pt=float(bbox_h_pt),
            wrap=False,
            min_pt=float(min_pt),
            max_pt=float(resolved_max_pt),
            width_fit_ratio=1.00,
            height_fit_ratio=float(height_fit_ratio),
        )
        fill_ratio = (float(font_size_pt) * float(line_height)) / max(
            1.0, float(bbox_h_pt)
        )
        return (normalized, float(font_size_pt), 1, float(fill_ratio))

    def _fit_wrapped_text(
        *,
        seed_font_pt: float,
        min_pt: float,
        bbox_w_pt: float,
        bbox_h_pt: float,
    ) -> tuple[str, float, int, float]:
        wrapped_font_pt = float(seed_font_pt)
        wrapped_text = normalized
        wrapped_lines_count = 1
        for _ in range(14):
            candidate_text = _wrap_text_to_width(
                normalized,
                max_width_pt=max(1.0, 1.01 * float(bbox_w_pt)),
                font_size_pt=float(wrapped_font_pt),
            )
            candidate_lines = [
                line for line in candidate_text.splitlines() if line.strip()
            ]
            if not candidate_lines:
                candidate_lines = [normalized]
                candidate_text = normalized
            total_h = (
                float(len(candidate_lines))
                * float(wrapped_font_pt)
                * float(line_height)
            )
            wrapped_text = candidate_text
            wrapped_lines_count = len(candidate_lines)
            if total_h <= (0.985 * float(bbox_h_pt)):
                break
            wrapped_font_pt = max(float(min_pt), float(wrapped_font_pt) - 0.32)

        fill_ratio = (
            float(wrapped_lines_count) * float(wrapped_font_pt) * float(line_height)
        ) / max(1.0, float(bbox_h_pt))
        return (
            wrapped_text,
            float(wrapped_font_pt),
            int(wrapped_lines_count),
            float(fill_ratio),
        )

    explicit_multiline = "\n" in normalized
    single_text, single_font_pt, _single_lines, single_fill = _fit_single_candidate()

    if is_heading and not explicit_multiline:
        return (single_text, float(single_font_pt), False)

    wrapped_seed = _fit_font_size_pt(
        normalized,
        bbox_w_pt=max(1.0, 1.01 * float(bbox_w_pt)),
        bbox_h_pt=float(bbox_h_pt),
        wrap=True,
        min_pt=float(min_pt),
        max_pt=float(max_pt),
        width_fit_ratio=1.02,
        height_fit_ratio=0.95,
    )
    wrapped_text, wrapped_font_pt, wrapped_lines, wrapped_fill = _fit_wrapped_text(
        seed_font_pt=float(wrapped_seed),
        min_pt=float(min_pt),
        bbox_w_pt=float(bbox_w_pt),
        bbox_h_pt=float(bbox_h_pt),
    )

    if explicit_multiline and wrapped_lines >= 2:
        return (wrapped_text, float(wrapped_font_pt), True)

    min_readable_pt = max(7.0, min(11.0, 0.62 * float(baseline_ocr_h_pt)))
    choose_wrap = False

    if wrap_override is True:
        choose_wrap = wrapped_lines >= 2
    elif wrap_override is False:
        choose_wrap = (
            (not is_heading)
            and wrapped_lines >= 2
            and (
                compact_len >= 72
                or float(single_font_pt) < float(min_readable_pt)
                or float(wrapped_font_pt) >= (float(single_font_pt) * 1.12)
            )
        )
    elif wrapped_lines >= 2:
        single_is_tiny = float(single_font_pt) < float(min_readable_pt)
        wrapped_is_clearly_better = float(wrapped_font_pt) >= (
            float(single_font_pt) * 1.10
        )
        wrapped_fills_box_better = float(wrapped_fill) >= (
            float(single_fill) + 0.16
        ) and float(wrapped_font_pt) >= (float(single_font_pt) * 1.02)
        choose_wrap = bool(
            single_is_tiny or wrapped_is_clearly_better or wrapped_fills_box_better
        )

    if choose_wrap and wrapped_lines >= 2:
        return (wrapped_text, float(wrapped_font_pt), True)

    if not explicit_multiline:
        allow_single_line_fill_expand = bool(
            is_heading
            or wrap_override is False
            or compact_len <= 56
            or bbox_h_pt >= (1.12 * float(baseline_ocr_h_pt))
        )
        if allow_single_line_fill_expand:
            expanded_max_pt = min(96.0, max(float(max_pt), 0.995 * float(bbox_h_pt)))
            if expanded_max_pt > (float(single_font_pt) + 0.8):
                _, expanded_font_pt, _expanded_lines, expanded_fill = (
                    _fit_single_candidate(
                        max_pt_override=float(expanded_max_pt),
                        height_fit_ratio=0.999,
                    )
                )
                if (
                    expanded_font_pt >= max(
                        float(single_font_pt) + 0.8,
                        float(single_font_pt) * 1.08,
                    )
                    and expanded_fill >= min(0.995, float(single_fill) + 0.10)
                ):
                    return (single_text, float(expanded_font_pt), False)
    return (single_text, float(single_font_pt), False)
