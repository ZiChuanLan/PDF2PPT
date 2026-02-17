from __future__ import annotations

from app.convert.pptx.font_utils import (
    _fit_mineru_text_style,
    _split_heading_text_after_colon,
)


def test_split_heading_text_after_colon_for_bilingual_title() -> None:
    text = "能力（The Abilities）：插件/工具（Plugins/Tools）"
    split = _split_heading_text_after_colon(text)
    assert split == "能力（The Abilities）：\n插件/工具（Plugins/Tools）"


def test_fit_mineru_text_style_keeps_rag_token_intact() -> None:
    text_to_render, _font_size_pt, wrap, is_heading, _is_primary_heading = (
        _fit_mineru_text_style(
            text="记忆 (The Memory) : RAG & Embedding",
            bbox_w_pt=242.0,
            bbox_h_pt=61.0,
            page_w_pt=1210.0,
            page_h_pt=681.0,
            y0_pt=546.0,
            mineru_block_type="title",
            mineru_text_level=None,
        )
    )

    assert is_heading
    assert not wrap
    assert text_to_render.splitlines() == ["记忆 (The Memory) :", "RAG & Embedding"]
    assert "R\nAG" not in text_to_render


def test_fit_mineru_text_style_splits_after_colon_for_plugins_title() -> None:
    text_to_render, _font_size_pt, wrap, is_heading, _is_primary_heading = (
        _fit_mineru_text_style(
            text="能力（The Abilities）：插件/工具（Plugins/Tools）",
            bbox_w_pt=292.0,
            bbox_h_pt=60.0,
            page_w_pt=1210.0,
            page_h_pt=681.0,
            y0_pt=546.0,
            mineru_block_type="title",
            mineru_text_level=None,
        )
    )

    assert is_heading
    assert not wrap
    assert text_to_render.splitlines() == [
        "能力（The Abilities）：",
        "插件/工具（Plugins/Tools）",
    ]

