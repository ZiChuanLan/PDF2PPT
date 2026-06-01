# pyright: reportMissingImports=false

"""Model listing and status endpoints."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.convert.ocr.layout_models import (
    LAYOUT_MODELS,
    LayoutModelInfo,
    is_model_downloaded,
)
from app.convert.ocr.runtime_probe import (
    probe_local_paddle_models,
    probe_local_tesseract,
)
from app.database import get_db
from app.models.error import AppException, ErrorCode
from app.models.user import SiteSettingsORM

router = APIRouter(prefix="/api/v1/models", tags=["models"])
from ._model_filtering import (
    _SUPPORTED_CAPABILITIES,
    infer_provider_from_base_url as _infer_provider_from_base_url,
    model_matches_capability as _model_matches_capability,
    normalize_provider as _normalize_provider,
)

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


# =============================================================================
# Model status endpoint (download endpoints moved to _download_manager.py)
# =============================================================================

logger = logging.getLogger(__name__)


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class ModelProviderStatus(BaseModel):
    """Readiness status for a single model/API provider."""

    ready: bool
    issues: list[str] = []
    provider: Optional[str] = None
    configured: bool = True


class ModelStatusResponse(BaseModel):
    """Unified model readiness status across all providers."""

    local: dict[str, ModelProviderStatus]
    remote: dict[str, ModelProviderStatus]


# Re-export download response models for backward compatibility
from ._download_manager import (  # noqa: E402, F401
    DownloadStatusItem,
    DownloadStatusResponse,
    ModelDownloadRequest,
    ModelDownloadResponse,
    DownloadCancelRequest,
    DownloadCancelResponse,
    ModelDeleteRequest,
    ModelDeleteResponse,
    resolve_layout_model_alias as _resolve_layout_model_alias,
)
# Include download router under the models prefix
from ._download_manager import download_router as _download_router  # noqa: E402
router.include_router(_download_router)


# ---------------------------------------------------------------------------
# Model status helpers
# ---------------------------------------------------------------------------


def _get_setting(db: Session, key: str) -> str | None:
    """Get a setting value from DB (site_settings), return None if missing."""
    row = db.query(SiteSettingsORM).filter(SiteSettingsORM.key == key).first()
    if row and row.value is not None:
        val = str(row.value).strip()
        return val if val else None
    return None


def _check_local_providers() -> dict[str, ModelProviderStatus]:
    """Check local OCR model readiness using existing probe functions."""
    providers: dict[str, ModelProviderStatus] = {}

    # Tesseract
    try:
        probe = probe_local_tesseract(language="chi_sim+eng")
        providers["tesseract"] = ModelProviderStatus(
            ready=bool(probe.get("ready")),
            issues=[
                str(i) for i in (probe.get("issues") or []) if str(i).strip()
            ],
        )
    except Exception as e:
        providers["tesseract"] = ModelProviderStatus(
            ready=False, issues=[f"probe_failed:{e}"]
        )

    # PaddleOCR
    try:
        probe = probe_local_paddle_models(language="ch")
        providers["paddleocr"] = ModelProviderStatus(
            ready=bool(probe.get("ready")),
            issues=[
                str(i) for i in (probe.get("issues") or []) if str(i).strip()
            ],
        )
    except Exception as e:
        providers["paddleocr"] = ModelProviderStatus(
            ready=False, issues=[f"probe_failed:{e}"]
        )

    # SAM (Segment Anything Model) for polygon refinement
    try:
        from app.convert.ocr._sam_provider import (
            get_sam_runtime_issues,
            is_sam_checkpoint_downloaded,
        )

        sam_runtime_issues = get_sam_runtime_issues()
        sam_checkpoint_downloaded = is_sam_checkpoint_downloaded()
        sam_issues = list(sam_runtime_issues)
        if not sam_checkpoint_downloaded:
            sam_issues.append("not_downloaded")
        providers["sam"] = ModelProviderStatus(
            ready=not sam_issues,
            issues=sam_issues,
            provider="mobilesam",
        )
    except Exception as e:
        providers["sam"] = ModelProviderStatus(
            ready=False,
            issues=[f"probe_failed:{e}"],
            provider="mobilesam",
        )

    # Per-model layout model status — report each model individually
    for model_id, model_info in LAYOUT_MODELS.items():
        model_issues: list[str] = []
        runtime_available = True
        try:
            downloaded = is_model_downloaded(model_id)
            if not downloaded:
                model_issues.append("not_downloaded")
            if model_info.provider == "doclayout_yolo":
                if not _module_available("doclayout_yolo"):
                    model_issues.append("doclayout_yolo_not_installed")
                    runtime_available = False
                if not downloaded and not _module_available("huggingface_hub"):
                    model_issues.append("huggingface_hub_not_installed")
        except Exception as e:
            downloaded = False
            model_issues.append(f"check_failed:{e}")

        providers[model_id] = ModelProviderStatus(
            ready=downloaded and runtime_available,
            issues=model_issues,
            provider=model_info.provider,
        )

    return providers


def _check_remote_providers(
    db: Session,
) -> dict[str, ModelProviderStatus]:
    """Check remote API provider readiness (credential presence in site_settings DB).

    Note: these keys are stored in the site_settings table by the admin settings
    page.  The Settings (env-var) object does NOT carry per-provider OCR keys, so
    there is no env-var fallback here — by design.
    """
    providers: dict[str, ModelProviderStatus] = {}

    # AIOCR — needs OCR API key
    ocr_ai_api_key = _get_setting(db, "ocr_ai_api_key")
    ocr_ai_configured = bool(ocr_ai_api_key)
    aiocr_issues: list[str] = []
    if not ocr_ai_configured:
        aiocr_issues.append("api_key_missing")
    providers["aiocr"] = ModelProviderStatus(
        ready=ocr_ai_configured,
        issues=aiocr_issues,
        configured=ocr_ai_configured,
    )

    # Baidu Doc — needs API key + secret key
    baidu_api_key = _get_setting(db, "ocr_baidu_api_key")
    baidu_secret_key = _get_setting(db, "ocr_baidu_secret_key")
    baidu_configured = bool(baidu_api_key and baidu_secret_key)
    baidu_issues: list[str] = []
    if not baidu_api_key:
        baidu_issues.append("api_key_missing")
    if not baidu_secret_key:
        baidu_issues.append("secret_key_missing")
    providers["baidu_doc"] = ModelProviderStatus(
        ready=baidu_configured,
        issues=baidu_issues,
        configured=baidu_configured,
    )

    # MinerU — needs API token
    mineru_token = _get_setting(db, "mineru_api_token")
    mineru_configured = bool(mineru_token)
    mineru_issues: list[str] = []
    if not mineru_configured:
        mineru_issues.append("api_token_missing")
    providers["mineru"] = ModelProviderStatus(
        ready=mineru_configured,
        issues=mineru_issues,
        configured=mineru_configured,
    )

    return providers


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status(db: Session = Depends(get_db)):
    """Get unified model readiness status.

    Returns readiness for both local OCR engines and remote API providers.
    Unauthenticated — any user can check model status before submitting jobs.
    """
    try:
        local = await asyncio.to_thread(_check_local_providers)
    except Exception as e:
        logger.warning("Local model status check failed: %s", e)
        local = {
            "tesseract": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
            "paddleocr": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
        }
        # Add per-model layout status with error
        for model_id in LAYOUT_MODELS:
            local[model_id] = ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"])

    try:
        remote = await asyncio.to_thread(_check_remote_providers, db)
    except Exception as e:
        logger.warning("Remote model status check failed: %s", e)
        remote = {
            "aiocr": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
            "baidu_doc": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
            "mineru": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
        }

    return ModelStatusResponse(local=local, remote=remote)


# G3b-G3: Download management (download / cancel / delete / status) moved to
# _download_manager.py. The router is included above and response models are
# re-exported for backward compatibility.
#
# Remaining in models.py:
#   - Model listing (/api/v1/models POST)
#   - Model status (/api/v1/models/status GET)
