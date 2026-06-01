"""Tests for JobConfig.to_worker_kwargs() propagation.

Verifies that structured JobConfig fields are correctly propagated
to the flat kwargs dict consumed by the worker.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.schemas.job_config import JobConfig, OcrAiConfig, OcrConfig, PptConfig


def _default_config() -> JobConfig:
    """Create a default JobConfig with minimal changes from default."""
    return JobConfig()


def test_to_worker_kwargs_defaults() -> None:
    """Default config produces expected default values in kwargs."""
    config = _default_config()
    kwargs = config.to_worker_kwargs()
    assert kwargs["enable_ocr"] is False
    assert kwargs["retain_process_artifacts"] is False
    assert kwargs["remove_footer_notebooklm"] is False
    assert kwargs["enable_layout"] is True


def test_to_worker_kwargs_does_not_affect_other_fields() -> None:
    """Setting one flag should not unexpectedly alter other kwargs."""
    config = JobConfig(
        enable_ocr=True,
        remove_footer_notebooklm=True,
    )
    kwargs = config.to_worker_kwargs()

    # Core flags should reflect the config
    assert kwargs["enable_ocr"] is True
    assert kwargs["remove_footer_notebooklm"] is True
    assert kwargs["retain_process_artifacts"] is False

    # Parse provider should still be 'local' by default
    assert kwargs["parse_provider"] == "local"

    # OCR provider should be 'auto' by default
    assert kwargs["ocr_provider"] == "auto"

    # PPT mode should be 'standard' by default
    assert kwargs["ppt_generation_mode"] == "standard"


def test_to_worker_kwargs_ocr_independent() -> None:
    """OCR enablement should be independent of other flags."""
    config_ocr = JobConfig(enable_ocr=True)
    config_no_ocr = JobConfig(enable_ocr=False)

    kwargs_ocr = config_ocr.to_worker_kwargs()
    kwargs_no_ocr = config_no_ocr.to_worker_kwargs()

    assert kwargs_ocr["enable_ocr"] is True
    assert kwargs_no_ocr["enable_ocr"] is False


def test_to_worker_kwargs_preserves_advanced_ocr_controls(monkeypatch) -> None:
    """Advanced OCR controls should survive the structured config boundary."""
    monkeypatch.setattr(
        "app.convert.ocr.layout_models.is_model_downloaded",
        lambda _: True,
    )

    config = JobConfig(
        enable_ocr=True,
        ocr=OcrConfig(
            provider="aiocr",
            render_dpi=240,
            strict_mode=False,
            enable_layout=False,
            enable_sam=None,
            ai=OcrAiConfig(
                provider="siliconflow",
                api_key="ocr-key",
                base_url="https://api.siliconflow.cn/v1",
                model="Qwen/Qwen2.5-VL-72B-Instruct",
                chain_mode="layout_block",
                layout_model="pp_doclayout_v3",
                prompt_preset="qwen_vl",
                direct_prompt_override="direct prompt",
                layout_block_prompt_override="layout prompt",
                image_region_prompt_override="image prompt",
                paddle_vl_docparser_max_side_px=0,
                page_concurrency=3,
                block_concurrency=2,
                requests_per_minute=90,
                tokens_per_minute=180000,
                max_retries=2,
                linebreak_assist=True,
            ),
        ),
        ppt=PptConfig(
            generation_mode="turbo",
            text_erase_mode="smart",
            scanned_page_mode="fullpage",
        ),
    )

    kwargs = config.to_worker_kwargs()

    assert kwargs["enable_ocr"] is True
    assert kwargs["ocr_provider"] == "aiocr"
    assert kwargs["ocr_render_dpi"] == 240
    assert kwargs["ocr_strict_mode"] is False
    assert kwargs["enable_layout"] is False
    assert kwargs["enable_sam"] is None
    assert kwargs["ocr_ai_provider"] == "siliconflow"
    assert kwargs["ocr_ai_api_key"] == "ocr-key"
    assert kwargs["ocr_ai_base_url"] == "https://api.siliconflow.cn/v1"
    assert kwargs["ocr_ai_model"] == "Qwen/Qwen2.5-VL-72B-Instruct"
    assert kwargs["ocr_ai_chain_mode"] == "layout_block"
    assert kwargs["ocr_ai_layout_model"] == "pp_doclayout_v3"
    assert kwargs["ocr_ai_prompt_preset"] == "qwen_vl"
    assert kwargs["ocr_ai_direct_prompt_override"] == "direct prompt"
    assert kwargs["ocr_ai_layout_block_prompt_override"] == "layout prompt"
    assert kwargs["ocr_ai_image_region_prompt_override"] == "image prompt"
    assert kwargs["ocr_paddle_vl_docparser_max_side_px"] == 0
    assert kwargs["ocr_ai_page_concurrency"] == 3
    assert kwargs["ocr_ai_block_concurrency"] == 2
    assert kwargs["ocr_ai_requests_per_minute"] == 90
    assert kwargs["ocr_ai_tokens_per_minute"] == 180000
    assert kwargs["ocr_ai_max_retries"] == 2
    assert kwargs["ocr_ai_linebreak_assist"] is True
    assert kwargs["ppt_generation_mode"] == "turbo"
    assert kwargs["text_erase_mode"] == "smart"
    assert kwargs["scanned_page_mode"] == "fullpage"
