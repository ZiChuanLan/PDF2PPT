# pyright: reportMissingImports=false

"""Model listing endpoints."""

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.error import AppException, ErrorCode

router = APIRouter(prefix="/api/v1/models", tags=["models"])


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


def _coerce_str_list(value: Any) -> list[str]:
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
            out.extend(_coerce_str_list(item))
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


def _normalize_signal_token(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"[\s/]+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9.+_-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def _extract_field_tokens(item: Any, field_names: tuple[str, ...]) -> list[str]:
    candidates: list[str] = []
    for field_name in field_names:
        candidates.extend(_coerce_str_list(getattr(item, field_name, None)))
    if isinstance(item, dict):
        for field_name in field_names:
            candidates.extend(_coerce_str_list(item.get(field_name)))
        architecture = item.get("architecture")
        if isinstance(architecture, dict):
            for field_name in field_names:
                candidates.extend(_coerce_str_list(architecture.get(field_name)))
    normalized: list[str] = []
    for raw in candidates:
        lowered = _normalize_signal_token(raw)
        if lowered:
            normalized.append(lowered)
    return normalized


def _extract_modalities(item: Any) -> list[str]:
    return _extract_field_tokens(item, _INPUT_MODALITY_FIELDS)


def _extract_output_modalities(item: Any) -> list[str]:
    return _extract_field_tokens(item, _OUTPUT_MODALITY_FIELDS)


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            return True
    return False


def _normalize_provider(value: str | None) -> str:
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


def _infer_provider_from_base_url(base_url: str | None) -> str:
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


def _normalize_model_id(model_id: str) -> str:
    lowered = str(model_id or "").strip().lower()
    lowered = lowered.replace("/", "-").replace(":", "-").replace("_", "-")
    lowered = re.sub(r"[^a-z0-9.+-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def _structured_vision_signal(item: Any) -> bool | None:
    modalities = _extract_modalities(item)
    output_modalities = _extract_output_modalities(item)
    has_image_input = any(token in _IMAGE_INPUT_HINTS for token in modalities)
    if not has_image_input:
        return None
    if output_modalities and not any(
        token in _TEXT_OUTPUT_HINTS for token in output_modalities
    ):
        return False
    return True


def _looks_like_openai_vision_model(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    if lowered.startswith(("gpt-4o", "gpt-4.1", "gpt-5")):
        return True
    return bool(re.match(r"^o[134](?:[-.].*)?$", lowered))


def _looks_like_claude_vision_model(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    return (
        lowered.startswith("claude-3")
        or lowered.startswith("claude-opus-4")
        or lowered.startswith("claude-sonnet-4")
        or lowered.startswith("claude-haiku-4")
    )


def _looks_like_gemini_vision_model(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    return lowered.startswith("gemini")


def _looks_like_qwen_vision_model(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    return (
        lowered.startswith("qvq-")
        or "qwen-vl" in lowered
        or "qwen2-vl" in lowered
        or "qwen2.5-vl" in lowered
        or "qwen3-vl" in lowered
        or "qwen-vlo" in lowered
    )


def _looks_like_glm_vision_model(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    return bool(re.search(r"\bglm-\d+(?:\.\d+)?v(?:[-.].*)?$", lowered))


def _looks_like_known_vision_family(model_id: str) -> bool:
    lowered = _normalize_model_id(model_id)
    if _looks_like_openai_vision_model(lowered):
        return True
    if _looks_like_claude_vision_model(lowered):
        return True
    if _looks_like_gemini_vision_model(lowered):
        return True
    if _looks_like_qwen_vision_model(lowered):
        return True
    if _looks_like_glm_vision_model(lowered):
        return True
    if _has_any_pattern(lowered, _OCR_ONLY_VISION_NAME_PATTERNS):
        return True
    return _has_any_pattern(lowered, _OTHER_VISION_FAMILY_PATTERNS)


def _is_vision_model(model_id: str, item: Any) -> bool:
    structured = _structured_vision_signal(item)
    if structured is not None:
        return structured

    lowered = _normalize_model_id(model_id)
    if _has_any_pattern(lowered, _NON_VISION_NAME_PATTERNS):
        return False
    if _has_any_pattern(lowered, _GENERATION_ONLY_NAME_PATTERNS):
        return False
    return _looks_like_known_vision_family(lowered)


def _is_explicit_ocr_model(model_id: str, item: Any) -> bool:
    # Product rule: the dedicated OCR model picker should only show models that
    # are *explicitly branded / exposed* as OCR-specialized. Some gateways tag
    # generic VL models (for example Qwen-VL) with an `ocr` capability, but we
    # still want those to live under the vision-model picker instead.
    return _has_any_pattern(model_id, _OCR_NAME_PATTERNS)


def _is_ocr_model(model_id: str, item: Any) -> bool:
    # OCR capability in product settings now means a *dedicated OCR model*.
    # Generic vision/VL models remain available via `capability=vision` for
    # local OCR post-process use, but should not appear in the
    # explicit OCR model picker.
    return _is_explicit_ocr_model(model_id, item)


def _model_matches_capability(*, model_id: str, item: Any, capability: str) -> bool:
    if capability == "all":
        return True
    if capability == "vision":
        return _is_vision_model(model_id, item)
    if capability == "ocr":
        return _is_ocr_model(model_id, item)
    return True


class ModelListRequest(BaseModel):
    provider: str = Field(
        "openai",
        description="LLM provider identifier (openai, siliconflow, claude, domestic)",
    )
    api_key: str = Field(..., description="API key for the provider")
    base_url: str | None = Field(None, description="Optional OpenAI-compatible base URL")
    capability: str = Field(
        "all",
        description=(
            "Filter models by capability "
            "(all, vision, ocr). `ocr` returns dedicated OCR models only; "
            "generic VL/vision models are listed under `vision`."
        ),
    )


class ModelListResponse(BaseModel):
    models: list[str]


@router.post("", response_model=ModelListResponse)
async def list_models(payload: ModelListRequest):
    provider = _normalize_provider(payload.provider)

    api_key = payload.api_key.strip()
    if not api_key:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="API key is required to list models",
            status_code=400,
        )

    base_url = payload.base_url.strip() if payload.base_url else None
    if provider == "auto":
        provider = _infer_provider_from_base_url(base_url)
    capability = payload.capability.strip().lower()
    if capability not in _SUPPORTED_CAPABILITIES:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Unsupported model capability filter",
            details={"capability": payload.capability},
            status_code=400,
        )

    try:
        if provider == "claude":
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.models.list(limit=1000)
        else:
            import openai

            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            response = client.with_options(timeout=10).models.list()
        models: list[str] = []
        for item in getattr(response, "data", []) or []:
            model_id = getattr(item, "id", None)
            if not model_id and isinstance(item, dict):
                model_id = item.get("id")
            if not model_id:
                continue
            model_id_str = str(model_id)
            if _model_matches_capability(
                model_id=model_id_str,
                item=item,
                capability=capability,
            ):
                models.append(model_id_str)

        # Keep a stable order without duplicates.
        seen: set[str] = set()
        ordered: list[str] = []
        for model_id in models:
            if model_id in seen:
                continue
            seen.add(model_id)
            ordered.append(model_id)

        return ModelListResponse(models=ordered)
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to list models",
            details={"error": str(e)},
            status_code=500,
        )
