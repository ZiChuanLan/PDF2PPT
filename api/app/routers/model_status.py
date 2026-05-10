"""Model status and download endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
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
from app.dependencies import require_admin
from app.models.error import AppException, ErrorCode
from app.models.user import SiteSettingsORM, UserORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


# ---------------------------------------------------------------------------
# Download progress tracking
# ---------------------------------------------------------------------------


@dataclass
class DownloadTask:
    """Tracks the state of a background model download."""

    model_id: str
    status: str = "downloading"  # "downloading", "completed", "failed", "cancelled"
    progress: float | None = None  # 0.0-1.0 for huggingface, None for paddlex
    message: str | None = None
    started_at: float = field(default_factory=time.time)
    cancel_requested: bool = False


# In-memory download task registry
_download_tasks: dict[str, DownloadTask] = {}
_download_tasks_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Download task persistence (3a: survive server restarts)
# ---------------------------------------------------------------------------

_DOWNLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "downloads"
)
_DOWNLOAD_TASKS_FILE = os.path.join(_DOWNLOADS_DIR, "tasks.json")


def _save_download_tasks():
    """Persist current download tasks to disk (thread-safe snapshot)."""
    try:
        os.makedirs(_DOWNLOADS_DIR, exist_ok=True)
        with _download_tasks_lock:
            data = {
                mid: {
                    "model_id": t.model_id,
                    "status": t.status,
                    "progress": t.progress,
                    "message": t.message,
                    "started_at": t.started_at,
                    "cancel_requested": t.cancel_requested,
                }
                for mid, t in _download_tasks.items()
                # Only persist active/significant tasks
                if t.status == "downloading" or t.status == "failed"
            }
        with open(_DOWNLOAD_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.warning("Failed to persist download tasks", exc_info=True)


def _load_download_tasks():
    """Restore download tasks from disk on server startup.

    Only restores tasks that were actively downloading or recently failed.
    Completed/cancelled tasks are not restored.
    """
    try:
        if not os.path.exists(_DOWNLOAD_TASKS_FILE):
            return

        with open(_DOWNLOAD_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        now = time.time()
        restored = 0
        with _download_tasks_lock:
            for mid, raw in data.items():
                status = raw.get("status", "failed")
                started_at = float(raw.get("started_at", now))
                # Don't restore very old tasks (> 1 hour)
                if now - started_at > 3600:
                    continue
                # Active downloads that were interrupted get marked as failed
                if status == "downloading":
                    status = "failed"
                _download_tasks[mid] = DownloadTask(
                    model_id=raw.get("model_id", mid),
                    status=status,
                    progress=raw.get("progress"),
                    message=raw.get("message", "服务器重启，下载已中断"),
                    started_at=started_at,
                    cancel_requested=False,
                )
                restored += 1

        if restored > 0:
            logger.info("Restored %d download task(s) from disk", restored)
    except Exception:
        logger.warning("Failed to load persisted download tasks", exc_info=True)


# Restore tasks on module load (server startup)
_load_download_tasks()


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
    status: str = "downloading"


class DownloadStatusItem(BaseModel):
    """Status of a single download task."""

    model_id: str
    status: str  # "downloading", "completed", "failed", "cancelled"
    progress: float | None = None  # 0.0-1.0 for huggingface, None for paddlex
    message: str | None = None
    started_at: float


class DownloadStatusResponse(BaseModel):
    """Response for download status polling."""

    downloads: dict[str, DownloadStatusItem]


class DownloadCancelRequest(BaseModel):
    """Request to cancel a download."""

    model: str = Field(..., description="Model identifier to cancel")


class DownloadCancelResponse(BaseModel):
    """Cancel result."""

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


def _get_cancel_checker(model_id: str):
    """Return a callable that returns True if cancel was requested for this model."""

    def _check_cancel() -> bool:
        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task and task.cancel_requested:
                return True
        return False

    return _check_cancel


def _update_download_progress(model_id: str, progress: float | None, message: str | None = None):
    """Update the progress of a download task."""
    with _download_tasks_lock:
        task = _download_tasks.get(model_id)
        if task:
            task.progress = progress
            if message:
                task.message = message


def _background_download_layout_model(model_id: str):
    """Background thread function to download a layout model."""
    try:
        cancel_check = _get_cancel_checker(model_id)

        def progress_callback(progress: float | None, message: str | None = None):
            _update_download_progress(model_id, progress, message)

        from app.convert.ocr.layout_models import cancellable_download_layout_model

        success = cancellable_download_layout_model(
            model_id, cancel_check=cancel_check, progress_callback=progress_callback
        )

        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                if task.cancel_requested:
                    task.status = "cancelled"
                    task.message = "下载已取消"
                elif success:
                    task.status = "completed"
                    task.progress = 1.0
                    task.message = "下载完成"
                else:
                    task.status = "failed"
                    task.message = "下载失败"
        _save_download_tasks()
    except Exception as e:
        logger.exception("Background download failed for %s: %s", model_id, e)
        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                task.status = "failed"
                task.message = f"下载失败: {e}"
        _save_download_tasks()


def _background_download_paddleocr(model_id: str = "paddleocr"):
    """Background thread function to download PaddleOCR models."""
    try:
        cancel_check = _get_cancel_checker(model_id)

        # PaddleOCR download can't be easily cancelled mid-flight,
        # but we check before starting
        if cancel_check():
            with _download_tasks_lock:
                task = _download_tasks.get(model_id)
                if task:
                    task.status = "cancelled"
                    task.message = "下载已取消"
            _save_download_tasks()
            return

        _download_paddleocr_models()

        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                if task.cancel_requested:
                    task.status = "cancelled"
                    task.message = "下载已取消"
                else:
                    task.status = "completed"
                    task.progress = 1.0
                    task.message = "下载完成"
        _save_download_tasks()
    except Exception as e:
        logger.exception("Background PaddleOCR download failed: %s", e)
        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                task.status = "failed"
                task.message = f"下载失败: {e}"
        _save_download_tasks()


def _resolve_layout_model_alias(model: str) -> str | None:
    """Resolve a model name/alias to a canonical layout model ID."""
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
    canonical = layout_model_aliases.get(model)
    if canonical:
        return canonical
    if model in LAYOUT_MODELS:
        return model
    return None


@router.post("/download", response_model=ModelDownloadResponse)
async def download_model(
    payload: ModelDownloadRequest,
    admin: UserORM = Depends(require_admin),
):
    """Trigger local model download in background (admin only).

    Returns immediately with download status. Use GET /download/status to poll
    progress and POST /download/cancel to abort.

    Supported models:
    - pp_doclayout: PP-DocLayout layout detection model (legacy alias → pp_doclayout_v3)
    - pp_doclayout_s / pp_doclayout_m / pp_doclayout_l / pp_doclayout_v3: specific variants
    - doclayout_yolo: DocLayout-YOLO model
    - paddleocr: PaddleOCR det/rec/cls models
    """
    model = payload.model.strip().lower()

    # Resolve layout model aliases
    target_id = _resolve_layout_model_alias(model)

    if target_id:
        # Check if already downloading
        with _download_tasks_lock:
            existing = _download_tasks.get(target_id)
            if existing and existing.status == "downloading":
                return ModelDownloadResponse(
                    ok=True,
                    model=target_id,
                    message="下载已在进行中",
                    status="downloading",
                )

        # Start background download
        with _download_tasks_lock:
            _download_tasks[target_id] = DownloadTask(model_id=target_id)

        _save_download_tasks()

        thread = threading.Thread(
            target=_background_download_layout_model,
            args=(target_id,),
            daemon=True,
        )
        thread.start()

        model_info = LAYOUT_MODELS[target_id]
        return ModelDownloadResponse(
            ok=True,
            model=target_id,
            message=f"{model_info.display_name} 开始下载",
            status="downloading",
        )

    if model in {"paddleocr", "paddle", "paddle_ocr"}:
        paddle_id = "paddleocr"
        with _download_tasks_lock:
            existing = _download_tasks.get(paddle_id)
            if existing and existing.status == "downloading":
                return ModelDownloadResponse(
                    ok=True,
                    model=paddle_id,
                    message="下载已在进行中",
                    status="downloading",
                )

        with _download_tasks_lock:
            _download_tasks[paddle_id] = DownloadTask(model_id=paddle_id)

        _save_download_tasks()

        thread = threading.Thread(
            target=_background_download_paddleocr,
            args=(paddle_id,),
            daemon=True,
        )
        thread.start()

        return ModelDownloadResponse(
            ok=True,
            model=paddle_id,
            message="PaddleOCR 开始下载",
            status="downloading",
        )

    supported = ", ".join(sorted(LAYOUT_MODELS.keys())) + ", paddleocr"
    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        message=f"Unsupported model for download: {payload.model}. Supported: {supported}",
        details={"model": payload.model},
        status_code=400,
    )


@router.get("/download/status", response_model=DownloadStatusResponse)
async def get_download_status():
    """Get status of all active/recent downloads.

    Returns download state for each model that is currently downloading or
    recently completed/failed/cancelled. Old entries are cleaned up after 5 minutes.
    """
    now = time.time()
    items: dict[str, DownloadStatusItem] = {}

    with _download_tasks_lock:
        # Clean up old completed/failed/cancelled tasks (older than 5 minutes)
        expired_ids = [
            mid for mid, task in _download_tasks.items()
            if task.status != "downloading" and (now - task.started_at) > 300
        ]
        for mid in expired_ids:
            del _download_tasks[mid]

        if expired_ids:
            _save_download_tasks()

        for mid, task in _download_tasks.items():
            items[mid] = DownloadStatusItem(
                model_id=task.model_id,
                status=task.status,
                progress=task.progress,
                message=task.message,
                started_at=task.started_at,
            )

    return DownloadStatusResponse(downloads=items)


@router.post("/download/cancel", response_model=DownloadCancelResponse)
async def cancel_download(
    payload: DownloadCancelRequest,
    admin: UserORM = Depends(require_admin),
):
    """Request cancellation of an active download (admin only).

    The download thread checks the cancel flag periodically and will stop
    as soon as possible. Already-downloaded partial files may remain.
    """
    model = payload.model.strip().lower()

    # Resolve aliases
    target_id = _resolve_layout_model_alias(model)
    if not target_id and model in {"paddleocr", "paddle", "paddle_ocr"}:
        target_id = "paddleocr"

    if not target_id:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unknown model: {payload.model}",
            status_code=400,
        )

    with _download_tasks_lock:
        task = _download_tasks.get(target_id)
        if not task:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"No active download for model: {target_id}",
                status_code=400,
            )
        if task.status != "downloading":
            return DownloadCancelResponse(
                ok=True,
                model=target_id,
                message=f"下载已处于 {task.status} 状态",
            )
        task.cancel_requested = True

    _save_download_tasks()
    return DownloadCancelResponse(
        ok=True,
        model=target_id,
        message="取消请求已发送",
    )


# ---------------------------------------------------------------------------
# Model deletion
# ---------------------------------------------------------------------------


class ModelDeleteRequest(BaseModel):
    """Request to delete a downloaded model from cache."""

    model: str = Field(..., description="Model identifier to delete")


class ModelDeleteResponse(BaseModel):
    """Delete result."""

    success: bool
    model: str
    message: str


def _delete_paddlex_model(model_id: str, model_info: LayoutModelInfo) -> bool:
    """Delete a PaddleX model from its cache directory.

    PaddleX caches models under ~/.paddlex/official_models/.
    """
    import paddlex  # type: ignore[import-untyped]

    home = Path.home()
    paddlex_cache = home / ".paddlex" / "official_models"
    try:
        from paddlex.utils.cache import CACHE_DIR  # type: ignore[import-untyped]
        paddlex_cache = Path(CACHE_DIR) / "official_models"
    except Exception:
        pass

    if not paddlex_cache.exists():
        return False

    target = (model_info.paddlex_model_name or "").lower().replace("-", "_").replace(" ", "")
    deleted = False
    for d in paddlex_cache.iterdir():
        if not d.is_dir():
            continue
        normalized = d.name.lower().replace("-", "_").replace(" ", "")
        if normalized == target or target in normalized:
            try:
                shutil.rmtree(d)
                logger.info("Deleted PaddleX model cache: %s", d)
                deleted = True
            except Exception as e:
                logger.warning("Failed to delete PaddleX model cache %s: %s", d, e)
                raise AppException(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to delete model cache: {e}",
                    status_code=500,
                )

    return deleted


def _delete_doclayout_yolo_model() -> bool:
    """Delete DocLayout-YOLO model files."""
    cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/app/data/models"))
    model_dir = cache_dir / "doclayout_yolo"

    if not model_dir.exists():
        return False

    try:
        shutil.rmtree(model_dir)
        logger.info("Deleted DocLayout-YOLO model cache: %s", model_dir)
        return True
    except Exception as e:
        logger.warning("Failed to delete DocLayout-YOLO cache %s: %s", model_dir, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"Failed to delete model cache: {e}",
            status_code=500,
        )


@router.post("/delete", response_model=ModelDeleteResponse)
async def delete_model(
    payload: ModelDeleteRequest,
    admin: UserORM = Depends(require_admin),
):
    """Delete a downloaded model from the local cache (admin only).

    Supported models:
    - pp_doclayout_s / pp_doclayout_m / pp_doclayout_l / pp_doclayout_v3
    - doclayout_yolo
    - paddleocr (deletes PaddleOCR det/rec/cls model cache)
    """
    model = payload.model.strip().lower()

    # Resolve layout model aliases
    target_id = _resolve_layout_model_alias(model)
    model_name = payload.model

    if target_id and target_id in LAYOUT_MODELS:
        model_info = LAYOUT_MODELS[target_id]

        # Don't delete while downloading
        with _download_tasks_lock:
            task = _download_tasks.get(target_id)
            if task and task.status == "downloading":
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"模型 {target_id} 正在下载中，无法删除",
                    status_code=400,
                )

        deleted = False
        if model_info.provider == "paddlex":
            deleted = _delete_paddlex_model(target_id, model_info)
        elif model_info.provider == "doclayout_yolo":
            deleted = _delete_doclayout_yolo_model()

        if deleted:
            return ModelDeleteResponse(
                success=True,
                model=model_name,
                message=f"已删除 {model_info.display_name} 缓存",
            )
        else:
            return ModelDeleteResponse(
                success=True,
                model=model_name,
                message=f"{model_info.display_name} 缓存不存在或已删除",
            )

    if model in {"paddleocr", "paddle", "paddle_ocr"}:
        # Delete PaddleOCR model cache (~/.paddleocr/)
        home = Path.home()
        paddleocr_cache = home / ".paddleocr"
        try:
            import paddleocr  # noqa: F401
            # Try to find paddleocr cache at the env or default location
            paddleocr_home = os.getenv("PADDLEOCR_HOME", "")
            if paddleocr_home:
                paddleocr_cache = Path(paddleocr_home).expanduser()
        except ImportError:
            pass

        deleted = False
        if paddleocr_cache.exists():
            try:
                shutil.rmtree(paddleocr_cache)
                logger.info("Deleted PaddleOCR cache: %s", paddleocr_cache)
                deleted = True
            except Exception as e:
                logger.warning("Failed to delete PaddleOCR cache %s: %s", paddleocr_cache, e)
                raise AppException(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to delete PaddleOCR cache: {e}",
                    status_code=500,
                )

        return ModelDeleteResponse(
            success=True,
            model=model_name,
            message="已删除 PaddleOCR 缓存" if deleted else "PaddleOCR 缓存不存在",
        )

    supported = ", ".join(sorted(LAYOUT_MODELS.keys())) + ", paddleocr"
    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        message=f"Unsupported model for deletion: {payload.model}. Supported: {supported}",
        details={"model": payload.model},
        status_code=400,
    )
