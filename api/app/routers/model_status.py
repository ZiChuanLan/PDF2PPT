"""Model status and download endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.convert.ocr.layout_models import (
    LAYOUT_MODELS,
    download_model as download_layout_model,
    is_model_downloaded,
)
from app.convert.ocr.runtime_probe import (
    probe_local_paddleocr,
    probe_local_tesseract,
)
from app.database import get_db
from app.dependencies import require_admin
from app.models.error import AppException, ErrorCode
from app.models.user import SiteSettingsORM, UserORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


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


class ModelDownloadRequest(BaseModel):
    """Request to download a local model."""

    model: str = Field(..., description="Model identifier: pp_doclayout, paddleocr")


class ModelDownloadResponse(BaseModel):
    """Download result."""

    ok: bool
    model: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
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
        probe = probe_local_paddleocr(language="ch")
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

    # Per-model layout model status — report each model individually
    for model_id, model_info in LAYOUT_MODELS.items():
        model_issues: list[str] = []
        try:
            downloaded = is_model_downloaded(model_id)
            if not downloaded:
                model_issues.append("not_downloaded")
        except Exception as e:
            downloaded = False
            model_issues.append(f"check_failed:{e}")

        providers[model_id] = ModelProviderStatus(
            ready=downloaded,
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


def _download_paddleocr_models() -> bool:
    """Trigger PaddleOCR model download by probing the runtime."""
    try:
        from app.convert.ocr.local_providers import PaddleOcrClient

        logger.info("Starting PaddleOCR model download")
        # Constructing PaddleOcrClient triggers model download via _ensure_engine
        client = PaddleOcrClient(language="ch")
        client._ensure_engine()
        logger.info("PaddleOCR model download complete")
        return True
    except ImportError:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="paddleocr package is not installed",
            status_code=400,
        )
    except Exception as e:
        logger.exception("PaddleOCR model download failed: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"PaddleOCR model download failed: {e}",
            status_code=500,
        )


@router.post("/download", response_model=ModelDownloadResponse)
async def download_model(
    payload: ModelDownloadRequest,
    admin: UserORM = Depends(require_admin),
):
    """Trigger local model download (admin only).

    Supported models:
    - pp_doclayout: PP-DocLayout layout detection model (legacy alias → pp_doclayout_v3)
    - pp_doclayout_s / pp_doclayout_m / pp_doclayout_l / pp_doclayout_v3: specific variants
    - doclayout_yolo: DocLayout-YOLO model
    - paddleocr: PaddleOCR det/rec/cls models
    """
    model = payload.model.strip().lower()

    # Map legacy aliases to canonical IDs
    layout_model_aliases = {
        "pp_doclayout": "pp_doclayout_v3",
        "pp-doclayout": "pp_doclayout_v3",
        "layout": "pp_doclayout_v3",
        "pp-doclayoutv3": "pp_doclayout_v3",
        "pp_doclayoutv3": "pp_doclayout_v3",
        "pp-doclayout-v3": "pp_doclayout_v3",
        "pp-doclayout-s": "pp_doclayout_s",
        "pp_doclayouts": "pp_doclayout_s",
        "pp-doclayout-m": "pp_doclayout_m",
        "pp_doclayoutm": "pp_doclayout_m",
        "pp-doclayout-l": "pp_doclayout_l",
        "pp_doclayoutl": "pp_doclayout_l",
        "doclayout-yolo": "doclayout_yolo",
        "doclayoutyolo": "doclayout_yolo",
    }

    canonical_id = layout_model_aliases.get(model)

    # Check if it's a known layout model
    if canonical_id or model in LAYOUT_MODELS:
        target_id = canonical_id or model
        if target_id not in LAYOUT_MODELS:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Unknown layout model: {payload.model}",
                details={"model": payload.model},
                status_code=400,
            )
        try:
            await asyncio.to_thread(download_layout_model, target_id)
        except RuntimeError as e:
            raise AppException(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                status_code=500,
            )
        model_info = LAYOUT_MODELS[target_id]
        return ModelDownloadResponse(
            ok=True,
            model=target_id,
            message=f"{model_info.display_name} downloaded successfully",
        )

    if model in {"paddleocr", "paddle", "paddle_ocr"}:
        await asyncio.to_thread(_download_paddleocr_models)
        return ModelDownloadResponse(
            ok=True,
            model="paddleocr",
            message="PaddleOCR models downloaded successfully",
        )
    else:
        supported = ", ".join(sorted(LAYOUT_MODELS.keys())) + ", paddleocr"
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported model for download: {payload.model}. Supported: {supported}",
            details={"model": payload.model},
            status_code=400,
        )
