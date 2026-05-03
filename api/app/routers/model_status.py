"""Model status and download endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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

    # PP-DocLayout — check if model is downloaded
    # The model is ready if PaddleOCR is ready (auto-downloads on first use)
    # or if OCR_PADDLE_LAYOUT_PREWARM=true was used at startup.
    pp_doclayout_ready = False
    pp_doclayout_issues: list[str] = []
    try:
        import paddlex  # noqa: F401

        # If paddlex is available, the model *can* be downloaded on demand.
        # For status, we check if the paddle runtime is available (which
        # implies the model can be used).
        paddle_probe = probe_local_paddleocr(language="ch")
        if paddle_probe.get("ready"):
            pp_doclayout_ready = True
        else:
            pp_doclayout_issues.append("paddleocr_not_ready")
    except ImportError:
        pp_doclayout_issues.append("paddlex_not_installed")
    except Exception as e:
        pp_doclayout_issues.append(f"check_failed:{e}")

    # Check env flag for explicit prewarm
    from app.convert.ocr.base import _env_flag

    layout_prewarm_enabled = _env_flag("OCR_PADDLE_LAYOUT_PREWARM", default=False)
    if layout_prewarm_enabled and not pp_doclayout_ready:
        pp_doclayout_issues.append("prewarm_enabled_but_not_ready")

    providers["pp_doclayout"] = ModelProviderStatus(
        ready=pp_doclayout_ready, issues=pp_doclayout_issues
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
            "pp_doclayout": ModelProviderStatus(ready=False, issues=[f"check_failed:{e}"]),
        }

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


def _download_pp_doclayout() -> bool:
    """Download PP-DocLayout model weights."""
    try:
        import paddlex

        model_name = "PP-DocLayoutV3"
        # Check env for override
        from app.convert.ocr.base import _clean_str
        import os

        env_model = _clean_str(os.getenv("OCR_PADDLE_LAYOUT_PREWARM_MODEL"))
        if env_model:
            model_name = env_model

        logger.info("Starting PP-DocLayout download: %s", model_name)
        paddlex.create_model(model_name)
        logger.info("PP-DocLayout download complete: %s", model_name)
        return True
    except ImportError:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="paddlex package is not installed. Install it with: pip install paddlex",
            status_code=400,
        )
    except Exception as e:
        logger.exception("PP-DocLayout download failed: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"PP-DocLayout download failed: {e}",
            status_code=500,
        )


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
    - pp_doclayout: PP-DocLayout layout detection model
    - paddleocr: PaddleOCR det/rec/cls models
    """
    model = payload.model.strip().lower()

    if model in {"pp_doclayout", "pp-doclayout", "layout"}:
        await asyncio.to_thread(_download_pp_doclayout)
        return ModelDownloadResponse(
            ok=True,
            model="pp_doclayout",
            message="PP-DocLayout model downloaded successfully",
        )
    elif model in {"paddleocr", "paddle", "paddle_ocr"}:
        await asyncio.to_thread(_download_paddleocr_models)
        return ModelDownloadResponse(
            ok=True,
            model="paddleocr",
            message="PaddleOCR models downloaded successfully",
        )
    else:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported model for download: {payload.model}. Use 'pp_doclayout' or 'paddleocr'.",
            details={"model": payload.model},
            status_code=400,
        )
