# pyright: reportMissingImports=false

"""Model filtering and capability detection utilities."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..models.error import AppException, ErrorCode

_SUPPORTED_CAPABILITIES = {"all", "vision", "ocr"}
_SUPPORTED_PROVIDERS = {
    "auto",
    "openai",
    "siliconflow",
    "deepseek",
    "ppio",
    "novita",
    "claude",
}
_PROVIDER_ALIASES = {
    "": "auto",
    "auto": "auto",
    "openai": "openai",
    "openai_compatible": "openai",
    "openai-compatible": "openai",
    "domestic": "siliconflow",
    "siliconflow": "siliconflow",
    "silicon_flow": "siliconflow",
    "sf": "siliconflow",
    "deepseek": "deepseek",
    "deep_seek": "deepseek",
    "ppio": "ppio",
    "ppinfra": "ppio",
    "novita": "novita",
    "claude": "claude",
    "anthropic": "claude",
}
_OCR_NAME_PATTERNS = (
    r"\bocr\b",
    r"paddleocr",
    r"mineru",
)
_INPUT_MODALITY_FIELDS = (
    "modalities",
    "input_modalities",
    "capabilities",
    "supported_modalities",
    "supported_input_modalities",
    "input_types",
    "input",
)
_OUTPUT_MODALITY_FIELDS = (
    "output_modalities",
    "supported_output_modalities",
    "output_types",
    "output",
)
_IMAGE_INPUT_HINTS = {
    "image",
    "images",
    "vision",
    "visual",
    "multimodal",
    "input-image",
    "input_image",
}
_TEXT_OUTPUT_HINTS = {
    "text",
    "json",
    "structured",
    "structured-output",
    "structured_output",
}
_NON_VISION_NAME_PATTERNS = (
    r"codex",
    r"\btts\b",
    r"transcrib",
    r"\basr\b",
    r"\bspeech\b",
    r"\bvoice\b",
    r"\baudio\b",
    r"whisper",
    r"embedding",
    r"embed",
    r"rerank",
    r"re-rank",
    r"moderation",
    r"safety",
    r"realtime",
)
_GENERATION_ONLY_NAME_PATTERNS = (
    r"\bdall-e\b",
    r"\bsora\b",
    r"gpt-image",
    r"glm-image",
    r"qwen-image",
    r"image-generation",
    r"image-edit",
)
_OCR_ONLY_VISION_NAME_PATTERNS = (
    r"deepseek[-_]?ocr",
    r"paddleocr[-_]?vl",
    r"glm[-_]?ocr",
    r"olmocr",
    r"mineru",
)
_OTHER_VISION_FAMILY_PATTERNS = (
    r"internvl",
    r"pixtral",
    r"llava",
    r"minicpm[-_]?v",
    r"kimi.*vl",
    r"doubao.*(?:vision|vl)",
    r"seed.*(?:vision|vl)",
    r"step.*(?:vision|vl)",
    r"hunyuan.*(?:vision|vl)",
)


def coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, bool):
                if item:
                    out.append(str(key))
                continue
            out.append(str(key))
            out.extend(coerce_str_list(item))
        return out
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def normalize_signal_token(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"[\s/]+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9.+_-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def extract_field_tokens(item: Any, field_names: tuple[str, ...]) -> list[str]:
    candidates: list[str] = []
    for field_name in field_names:
        candidates.extend(coerce_str_list(getattr(item, field_name, None)))
    if isinstance(item, dict):
        for field_name in field_names:
            candidates.extend(coerce_str_list(item.get(field_name)))
        architecture = item.get("architecture")
        if isinstance(architecture, dict):
            for field_name in field_names:
                candidates.extend(coerce_str_list(architecture.get(field_name)))
    normalized: list[str] = []
    for raw in candidates:
        lowered = normalize_signal_token(raw)
        if lowered:
            normalized.append(lowered)
    return normalized


def extract_modalities(item: Any) -> list[str]:
    return extract_field_tokens(item, _INPUT_MODALITY_FIELDS)


def extract_output_modalities(item: Any) -> list[str]:
    return extract_field_tokens(item, _OUTPUT_MODALITY_FIELDS)


def has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            return True
    return False


def normalize_provider(value: str | None) -> str:
    cleaned = str(value or "").strip().lower()
    provider = _PROVIDER_ALIASES.get(cleaned, cleaned or "auto")
    if provider not in _SUPPORTED_PROVIDERS:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Unsupported provider for model listing",
            details={"provider": value},
            status_code=400,
        )
    return provider


def infer_provider_from_base_url(base_url: str | None) -> str:
    cleaned = str(base_url or "").strip().lower()
    if not cleaned:
        return "openai"
    try:
        host = (urlparse(cleaned).hostname or "").strip().lower()
    except Exception:
        host = ""
    if "anthropic.com" in host:
        return "claude"
    if "siliconflow" in host:
        return "siliconflow"
    if "ppio.com" in host or "ppinfra.com" in host:
        return "ppio"
    if "novita.ai" in host:
        return "novita"
    if "deepseek.com" in host:
        return "deepseek"
    return "openai"


def normalize_model_id(model_id: str) -> str:
    lowered = str(model_id or "").strip().lower()
    lowered = lowered.replace("/", "-").replace(":", "-").replace("_", "-")
    lowered = re.sub(r"[^a-z0-9.+-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def structured_vision_signal(item: Any) -> bool | None:
    modalities = extract_modalities(item)
    output_modalities = extract_output_modalities(item)
    has_image_input = any(token in _IMAGE_INPUT_HINTS for token in modalities)
    if not has_image_input:
        return None
    if output_modalities and not any(
        token in _TEXT_OUTPUT_HINTS for token in output_modalities
    ):
        return False
    return True


def looks_like_openai_vision_model(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    if lowered.startswith(("gpt-4o", "gpt-4.1", "gpt-5")):
        return True
    return bool(re.match(r"^o[134](?:[-.].*)?$", lowered))


def looks_like_claude_vision_model(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    return (
        lowered.startswith("claude-3")
        or lowered.startswith("claude-opus-4")
        or lowered.startswith("claude-sonnet-4")
        or lowered.startswith("claude-haiku-4")
    )


def looks_like_gemini_vision_model(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    return lowered.startswith("gemini")


def looks_like_qwen_vision_model(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    return (
        lowered.startswith("qvq-")
        or "qwen-vl" in lowered
        or "qwen2-vl" in lowered
        or "qwen2.5-vl" in lowered
        or "qwen3-vl" in lowered
        or "qwen-vlo" in lowered
    )


def looks_like_glm_vision_model(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    return bool(re.search(r"\bglm-\d+(?:\.\d+)?v(?:[-.].*)?$", lowered))


def looks_like_known_vision_family(model_id: str) -> bool:
    lowered = normalize_model_id(model_id)
    if looks_like_openai_vision_model(lowered):
        return True
    if looks_like_claude_vision_model(lowered):
        return True
    if looks_like_gemini_vision_model(lowered):
        return True
    if looks_like_qwen_vision_model(lowered):
        return True
    if looks_like_glm_vision_model(lowered):
        return True
    if has_any_pattern(lowered, _OCR_ONLY_VISION_NAME_PATTERNS):
        return True
    return has_any_pattern(lowered, _OTHER_VISION_FAMILY_PATTERNS)


def is_vision_model(model_id: str, item: Any) -> bool:
    structured = structured_vision_signal(item)
    if structured is not None:
        return structured

    lowered = normalize_model_id(model_id)
    if has_any_pattern(lowered, _NON_VISION_NAME_PATTERNS):
        return False
    if has_any_pattern(lowered, _GENERATION_ONLY_NAME_PATTERNS):
        return False
    return looks_like_known_vision_family(lowered)


def is_explicit_ocr_model(model_id: str, item: Any) -> bool:
    return has_any_pattern(model_id, _OCR_NAME_PATTERNS)


def is_ocr_model(model_id: str, item: Any) -> bool:
    return is_explicit_ocr_model(model_id, item)


def model_matches_capability(*, model_id: str, item: Any, capability: str) -> bool:
    if capability == "all":
        return True
    if capability == "vision":
        return is_vision_model(model_id, item)
    if capability == "ocr":
        return is_ocr_model(model_id, item)
    return True
