"""MinerU text style fitting (split from font_utils.py).

Contains _fit_mineru_text_style() which determines text_to_render, font_size_pt,
wrap, is_heading, and is_primary_heading for MinerU-parsed text blocks.
"""

from __future__ import annotations

from ..ocr.utils import _contains_cjk


def _fit_mineru_text_style(
    *,
    text: str,
    bbox_w_pt: float,
    bbox_h_pt: float,
    page_w_pt: float,
    page_h_pt: float,
    y0_pt: float,
    mineru_block_type: str | None,
    mineru_text_level: int | None,
) -> tuple[str, float, bool, bool, bool]:
    """Return (text_to_render, font_size_pt, wrap, is_heading, is_primary_heading)."""
    # Deferred imports to avoid circular dependency.
    from ._font_wrap import _wrap_text_to_width

    from ._font_wrap import (
        _compact_text_length,
        _fit_font_size_pt,
        _normalize_ocr_text_for_render,
        _split_heading_text_after_colon,
    )

    normalized = _normalize_ocr_text_for_render(text)
    if not normalized:
        return ("", 6.0, False, False, False)

    bbox_w_pt = max(1.0, float(bbox_w_pt))
    bbox_h_pt = max(1.0, float(bbox_h_pt))
    page_w_pt = max(1.0, float(page_w_pt))
    page_h_pt = max(1.0, float(page_h_pt))
    y0_pt = max(0.0, float(y0_pt))

    text_to_fit = normalized
    is_bullet_like = text_to_fit.lstrip().startswith(("-", "\u2022", "\u00b7", "\u25cf"))
    plain_len = len(text_to_fit.replace("\n", ""))

    block_type = str(mineru_block_type or "").strip().lower()
    text_level: int | None = None
    if mineru_text_level is not None:
        try:
            text_level = int(mineru_text_level)
        except Exception:
            text_level = None

    semantic_heading_tokens = {
        "title",
        "heading",
        "header",
        "h1",
        "h2",
        "subtitle",
        "subheading",
        "section_title",
        "paragraph_title",
        "title_1",
        "title_2",
        "title_3",
    }
    is_semantic_heading = bool(
        block_type in semantic_heading_tokens
        or any(
            token in block_type for token in ("title", "heading", "header", "subtitle")
        )
    )

    is_heading = bool(is_semantic_heading) or (
        (text_level is not None and text_level <= 2 and plain_len <= 60)
        or (
            y0_pt <= 0.22 * page_h_pt
            and bbox_h_pt >= 18.0
            and plain_len <= 56
            and (not is_bullet_like)
        )
    )
    is_primary_heading = bool(
        is_heading and y0_pt <= 0.16 * page_h_pt and bbox_w_pt >= 0.34 * page_w_pt
    )

    source_heading_text = text_to_fit
    if is_heading:
        text_to_fit = " ".join(
            [
                line.strip()
                for line in str(text_to_fit or "").split("\n")
                if line.strip()
            ]
        ).strip()

    wrap_for_fit = bool(not is_heading)
    max_body_pt = min(
        96.0 if is_primary_heading else 72.0,
        max(7.0, (0.98 if is_heading else 0.94) * float(bbox_h_pt)),
    )
    min_body_pt = 6.0
    line_height = 1.18 if _contains_cjk(text_to_fit or normalized) else 1.15
    prefit_font_size_pt: float | None = None

    if is_heading:
        wrap_for_fit = False
        prefit_font_size_pt = _fit_font_size_pt(
            text_to_fit,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            wrap=False,
            min_pt=min_body_pt,
            max_pt=max_body_pt,
            width_fit_ratio=1.00,
            height_fit_ratio=0.995,
        )

    if prefit_font_size_pt is not None:
        font_size_pt = float(prefit_font_size_pt)
    else:
        font_size_pt = _fit_font_size_pt(
            text_to_fit,
            bbox_w_pt=bbox_w_pt,
            bbox_h_pt=bbox_h_pt,
            wrap=wrap_for_fit,
            min_pt=min_body_pt,
            max_pt=max_body_pt,
            width_fit_ratio=1.03 if wrap_for_fit else 1.00,
            height_fit_ratio=0.96 if wrap_for_fit else 0.995,
        )

    text_to_render = text_to_fit
    if is_heading:
        single_line_font_size_pt = float(font_size_pt)
        single_line_fill_ratio = (
            float(single_line_font_size_pt) * float(line_height)
        ) / max(1.0, float(bbox_h_pt))
        multiline_candidates: list[str] = []
        seen_multiline_candidates: set[str] = set()
        for candidate in (
            _normalize_ocr_text_for_render(source_heading_text),
            _split_heading_text_after_colon(text_to_fit),
        ):
            cleaned_candidate = _normalize_ocr_text_for_render(candidate)
            if (
                not cleaned_candidate
                or "\n" not in cleaned_candidate
                or cleaned_candidate == text_to_fit
                or cleaned_candidate in seen_multiline_candidates
            ):
                continue
            seen_multiline_candidates.add(cleaned_candidate)
            multiline_candidates.append(cleaned_candidate)

        best_multiline_text: str | None = None
        best_multiline_font_pt = float(single_line_font_size_pt)
        best_multiline_fill_ratio = float(single_line_fill_ratio)

        for candidate_text in multiline_candidates:
            candidate_lines = [
                line for line in candidate_text.splitlines() if line.strip()
            ]
            if len(candidate_lines) < 2:
                continue
            candidate_font_pt = _fit_font_size_pt(
                candidate_text,
                bbox_w_pt=bbox_w_pt,
                bbox_h_pt=bbox_h_pt,
                wrap=True,
                min_pt=min_body_pt,
                max_pt=max_body_pt,
                width_fit_ratio=1.02,
                height_fit_ratio=0.985,
            )
            candidate_fill_ratio = (
                float(len(candidate_lines))
                * float(candidate_font_pt)
                * float(line_height)
            ) / max(1.0, float(bbox_h_pt))
            if candidate_fill_ratio > 0.995:
                continue
            if candidate_font_pt <= (single_line_font_size_pt + 0.6):
                continue
            if candidate_fill_ratio <= (single_line_fill_ratio + 0.18):
                continue
            if candidate_font_pt <= best_multiline_font_pt:
                continue
            best_multiline_text = candidate_text
            best_multiline_font_pt = float(candidate_font_pt)
            best_multiline_fill_ratio = float(candidate_fill_ratio)

        if best_multiline_text is not None and (
            best_multiline_font_pt >= (single_line_font_size_pt * 1.12)
            or best_multiline_fill_ratio >= (single_line_fill_ratio + 0.24)
        ):
            text_to_render = best_multiline_text
            font_size_pt = float(best_multiline_font_pt)
            wrap_for_fit = True

    if wrap_for_fit and not (is_heading and "\n" in text_to_render):
        candidate_text = text_to_fit
        for _ in range(12):
            wrap_width_pt = max(
                1.0,
                float(bbox_w_pt)
                + max(
                    2.4,
                    0.20 * float(bbox_h_pt),
                    0.42 * float(font_size_pt),
                ),
            )
            candidate_text = _wrap_text_to_width(
                text_to_fit,
                max_width_pt=wrap_width_pt,
                font_size_pt=float(font_size_pt),
            )
            candidate_lines = [
                line for line in candidate_text.splitlines() if line.strip()
            ]
            if not candidate_lines:
                candidate_lines = [text_to_fit]
                candidate_text = text_to_fit
            line_height = 1.18 if _contains_cjk(text_to_fit) else 1.15
            total_h = float(len(candidate_lines)) * float(font_size_pt) * line_height
            if total_h <= (0.985 * bbox_h_pt):
                text_to_render = candidate_text
                break
            font_size_pt = max(float(min_body_pt), float(font_size_pt) - 0.35)
        else:
            text_to_render = candidate_text if candidate_text else text_to_fit

    return (
        text_to_render,
        float(font_size_pt),
        bool(wrap_for_fit),
        bool(is_heading),
        bool(is_primary_heading),
    )
