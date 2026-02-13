# pyright: reportMissingImports=false

"""Model listing endpoints."""

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.error import AppException, ErrorCode

router = APIRouter(prefix="/api/v1/models", tags=["models"])


_SUPPORTED_CAPABILITIES = {"all", "vision", "ocr"}
_VISION_NAME_PATTERNS = (
    r"\bvl\b",
    r"vision",
    r"multimodal",
    r"omni",
    r"gpt-4o",
    r"gemini",
    r"claude-3",
)
_OCR_NAME_PATTERNS = (
    r"\bocr\b",
    r"paddleocr",
    r"mineru",
)


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
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


def _extract_modalities(item: Any) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_coerce_str_list(getattr(item, "modalities", None)))
    candidates.extend(_coerce_str_list(getattr(item, "input_modalities", None)))
    candidates.extend(_coerce_str_list(getattr(item, "capabilities", None)))
    if isinstance(item, dict):
        candidates.extend(_coerce_str_list(item.get("modalities")))
        candidates.extend(_coerce_str_list(item.get("input_modalities")))
        candidates.extend(_coerce_str_list(item.get("capabilities")))
    normalized = []
    for raw in candidates:
        lowered = raw.strip().lower()
        if lowered:
            normalized.append(lowered)
    return normalized


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            return True
    return False


def _is_vision_model(model_id: str, item: Any) -> bool:
    modalities = _extract_modalities(item)
    if any(m in {"image", "vision", "multimodal", "input_image"} for m in modalities):
        return True
    return _has_any_pattern(model_id, _VISION_NAME_PATTERNS)


def _is_ocr_model(model_id: str, item: Any) -> bool:
    if _has_any_pattern(model_id, _OCR_NAME_PATTERNS):
        return True
    modalities = _extract_modalities(item)
    if "ocr" in modalities:
        return True
    # Many vision/VL models can be used for OCR via prompting. Treat them as
    # OCR-capable so the frontend can pick models like Qwen-VL / GPT-4o for OCR.
    return _is_vision_model(model_id, item)


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
        "openai", description="LLM provider identifier (openai, domestic)"
    )
    api_key: str = Field(..., description="API key for the provider")
    base_url: str | None = Field(None, description="Optional OpenAI-compatible base URL")
    capability: str = Field(
        "all", description="Filter models by capability (all, vision, ocr)"
    )


class ModelListResponse(BaseModel):
    models: list[str]


@router.post("", response_model=ModelListResponse)
async def list_models(payload: ModelListRequest):
    provider = payload.provider.strip().lower()
    if provider == "claude":
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Model listing is not supported for Claude",
            status_code=400,
        )
    if provider not in {"openai", "domestic"}:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Unsupported provider for model listing",
            details={"provider": payload.provider},
            status_code=400,
        )

    api_key = payload.api_key.strip()
    if not api_key:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="API key is required to list models",
            status_code=400,
        )

    base_url = payload.base_url.strip() if payload.base_url else None
    capability = payload.capability.strip().lower()
    if capability not in _SUPPORTED_CAPABILITIES:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Unsupported model capability filter",
            details={"capability": payload.capability},
            status_code=400,
        )

    try:
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
