from __future__ import annotations


def test_wrap_avoids_leading_punctuation() -> None:
    """Ensure wrap logic doesn't leave '：' on its own line.

    This guards a common scanned-slide regression reported by users when OCR
    returns a 2-line heading but the fitter wraps right before the colon.
    """

    from app.convert import pptx_generator as pg

    font_size = 14.0
    prefix = "大脑 (The Brain)"
    text = f"{prefix}：大语言模型"

    # Compute widths in the same per-token way used by the wrapper so the
    # test is stable even if font metrics differ across environments.
    tokens = list(prefix)
    prefix_w = sum(
        pg._token_width_pt(token, font_size_pt=font_size, prefer_cjk=True)  # type: ignore[attr-defined]
        for token in tokens
    )
    colon_w = pg._token_width_pt("：", font_size_pt=font_size, prefer_cjk=True)  # type: ignore[attr-defined]

    # Force a wrap decision right before the colon.
    max_width = prefix_w + 0.25 * colon_w

    lines = pg._wrap_paragraph_to_lines(  # type: ignore[attr-defined]
        text, max_width_pt=max_width, font_size_pt=font_size
    )

    assert lines, "Expected wrapped lines"
    assert not any(line.startswith("：") for line in lines[1:]), lines
    assert any(line.endswith("：") for line in lines), lines

