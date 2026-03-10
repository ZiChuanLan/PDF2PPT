from __future__ import annotations

import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.routers import models


def test_model_list_provider_normalizes_openai_compatible_gateways() -> None:
    assert models._normalize_provider("openai") == "openai"
    assert models._normalize_provider("siliconflow") == "siliconflow"
    assert models._normalize_provider("ppio") == "ppio"
    assert models._normalize_provider("novita") == "novita"
    assert models._normalize_provider("deepseek") == "deepseek"
    assert models._normalize_provider("anthropic") == "claude"


def test_model_list_provider_can_infer_claude_from_base_url() -> None:
    assert models._infer_provider_from_base_url("https://api.anthropic.com") == "claude"
    assert models._infer_provider_from_base_url("https://api.deepseek.com/v1") == "deepseek"


def test_vision_capability_includes_visual_ocr_and_claude_models() -> None:
    assert (
        models._model_matches_capability(
            model_id="deepseek-ai/DeepSeek-OCR",
            item={},
            capability="vision",
        )
        is True
    )
    assert (
        models._model_matches_capability(
            model_id="gpt-5-mini",
            item={},
            capability="vision",
        )
        is True
    )
    assert (
        models._model_matches_capability(
            model_id="gemini-2.5-pro",
            item={},
            capability="vision",
        )
        is True
    )
    assert (
        models._model_matches_capability(
            model_id="zai-org/GLM-4.6V",
            item={},
            capability="vision",
        )
        is True
    )
    assert (
        models._model_matches_capability(
            model_id="claude-3-5-sonnet-20241022",
            item={},
            capability="vision",
        )
        is True
    )


def test_vision_capability_prefers_structured_modalities_over_name_guess() -> None:
    assert (
        models._model_matches_capability(
            model_id="custom-model-without-v-token",
            item={
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
            capability="vision",
        )
        is True
    )
    assert (
        models._model_matches_capability(
            model_id="custom-image-generator",
            item={
                "input_modalities": ["text", "image"],
                "output_modalities": ["image"],
            },
            capability="vision",
        )
        is False
    )


def test_vision_capability_excludes_audio_and_generation_only_models() -> None:
    assert (
        models._model_matches_capability(
            model_id="gpt-4o-mini-transcribe",
            item={},
            capability="vision",
        )
        is False
    )
    assert (
        models._model_matches_capability(
            model_id="gemini-2.5-flash-preview-tts",
            item={},
            capability="vision",
        )
        is False
    )
    assert (
        models._model_matches_capability(
            model_id="gpt-5-codex",
            item={},
            capability="vision",
        )
        is False
    )
    assert (
        models._model_matches_capability(
            model_id="gpt-image-1",
            item={},
            capability="vision",
        )
        is False
    )
    assert (
        models._model_matches_capability(
            model_id="claude-2.1",
            item={},
            capability="vision",
        )
        is False
    )


def test_ocr_capability_keeps_generic_vl_models_out() -> None:
    assert (
        models._model_matches_capability(
            model_id="Qwen/Qwen2.5-VL-72B-Instruct",
            item={},
            capability="ocr",
        )
        is False
    )
