# pyright: reportMissingImports=false

"""Model download management — isolated from models.py per R3-G3b."""

from __future__ import annotations

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
)
from app.dependencies import require_admin
from app.models.error import AppException, ErrorCode
from app.models.user import UserORM

logger = logging.getLogger(__name__)

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
# Download task persistence
# ---------------------------------------------------------------------------

def _get_downloads_dir() -> Path:
    """Return the runtime data directory for persisted download tasks."""
    return Path(os.getenv("APP_DATA_DIR", "/app/data")) / "downloads"


def _get_download_tasks_file() -> Path:
    """Return the persisted download task JSON path."""
    return _get_downloads_dir() / "tasks.json"


def _save_download_tasks():
    """Persist current download tasks to disk (thread-safe snapshot)."""
    try:
        downloads_dir = _get_downloads_dir()
        downloads_dir.mkdir(parents=True, exist_ok=True)
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
        with _get_download_tasks_file().open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.exception("Failed to persist download tasks")


def _load_download_tasks():
    """Restore download tasks from disk on server startup."""
    try:
        tasks_file = _get_download_tasks_file()
        if not tasks_file.exists():
            return

        with tasks_file.open("r", encoding="utf-8") as f:
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
        logger.exception("Failed to load persisted download tasks")


# Restore tasks on module load (server startup)
_load_download_tasks()


# ---------------------------------------------------------------------------
# Public API for external modules to query download state
# ---------------------------------------------------------------------------

def get_download_task(model_id: str) -> DownloadTask | None:
    """Thread-safe read of a single download task."""
    with _download_tasks_lock:
        return _download_tasks.get(model_id)


def get_all_download_tasks() -> dict[str, DownloadTask]:
    """Thread-safe snapshot of all active download tasks."""
    with _download_tasks_lock:
        return dict(_download_tasks)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


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
# Model deletion models
# ---------------------------------------------------------------------------


class ModelDeleteRequest(BaseModel):
    """Request to delete a downloaded model from cache."""

    model: str = Field(..., description="Model identifier to delete")


class ModelDeleteResponse(BaseModel):
    """Delete result."""

    success: bool
    model: str
    message: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

download_router = APIRouter(tags=["model-downloads"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _update_download_progress(
    model_id: str, progress: float | None, message: str | None = None
):
    """Update the progress of a download task."""
    with _download_tasks_lock:
        task = _download_tasks.get(model_id)
        if task:
            task.progress = progress
            if message:
                task.message = message


def _format_sam_download_error(exc: BaseException) -> str:
    """Return an actionable user-facing message for MobileSAM download failures."""
    import urllib.error

    reason = getattr(exc, "reason", None)
    error_text = " ".join(
        part for part in (str(exc), str(reason) if reason is not None else "") if part
    )
    normalized = error_text.lower()
    dns_or_proxy_markers = (
        "errno -5",
        "no address associated with hostname",
        "name or service not known",
        "temporary failure in name resolution",
        "nodename nor servname",
        "getaddrinfo failed",
        "proxy",
        "timed out",
        "network is unreachable",
    )
    workaround = (
        "请检查 Docker/系统 DNS 或代理配置；也可以设置 "
        "MOBILE_SAM_CHECKPOINT_URL 或 SAM_CHECKPOINT_URL 为可访问的镜像地址，"
        "或设置 MOBILE_SAM_CHECKPOINT_PATH 或 SAM_CHECKPOINT_PATH 指向已下载的 mobile_sam.pt。"
    )

    if isinstance(exc, urllib.error.URLError) and any(
        marker in normalized for marker in dns_or_proxy_markers
    ):
        return (
            "下载失败: 无法访问 MobileSAM 下载地址（DNS/网络/代理不可用）。"
            f"{workaround} 原始错误: {exc}"
        )

    return f"下载失败: {exc}。{workaround}"


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

        _update_download_progress(model_id, None, "正在下载 PaddleOCR 模型…")
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


def _background_download_sam(model_id: str = "sam"):
    """Background thread function to download SAM (MobileSAM) checkpoint."""
    ckpt_path: Path | None = None
    had_existing_checkpoint = False

    try:
        cancel_check = _get_cancel_checker(model_id)

        from app.convert.ocr._sam_provider import (
            _download_checkpoint,
            _get_checkpoint_path,
            get_sam_checkpoint_source_path,
        )

        ckpt_path = _get_checkpoint_path()
        ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        had_existing_checkpoint = ckpt_path.exists()

        if cancel_check():
            with _download_tasks_lock:
                task = _download_tasks.get(model_id)
                if task:
                    task.status = "cancelled"
                    task.message = "下载已取消"
            _save_download_tasks()
            return

        using_local_checkpoint = get_sam_checkpoint_source_path() is not None
        progress_action = (
            "安装本地 SAM 模型" if using_local_checkpoint else "下载 SAM 模型"
        )
        _update_download_progress(model_id, 0.0, f"正在{progress_action}…")

        last_update = [0.0]

        def reporthook(block_num: int, block_size: int, total_size: int) -> None:
            if cancel_check():
                raise InterruptedError("Download cancelled")
            if total_size > 0:
                progress = min(block_num * block_size / total_size, 1.0)
                now = time.time()
                if now - last_update[0] >= 0.5 or progress >= 1.0:
                    last_update[0] = now
                    pct = int(progress * 100)
                    _update_download_progress(
                        model_id, progress, f"正在{progress_action}… {pct}%"
                    )

        try:
            _download_checkpoint(ckpt_path, reporthook=reporthook)
        except InterruptedError:
            # Cancelled via reporthook
            if not had_existing_checkpoint and ckpt_path.exists():
                ckpt_path.unlink(missing_ok=True)
            with _download_tasks_lock:
                task = _download_tasks.get(model_id)
                if task:
                    task.status = "cancelled"
                    task.message = "下载已取消"
            _save_download_tasks()
            return

        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                task.status = "completed"
                task.progress = 1.0
                task.message = "下载完成"
        _save_download_tasks()
    except Exception as e:
        logger.exception("Background SAM download failed: %s", e)
        try:
            if (
                ckpt_path is not None
                and not had_existing_checkpoint
                and ckpt_path.exists()
            ):
                ckpt_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove partial SAM checkpoint %s", ckpt_path)
        with _download_tasks_lock:
            task = _download_tasks.get(model_id)
            if task:
                task.status = "failed"
                task.message = _format_sam_download_error(e)
        _save_download_tasks()


def resolve_layout_model_alias(model: str) -> str | None:
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


# ---------------------------------------------------------------------------
# Download endpoints
# ---------------------------------------------------------------------------


@download_router.post("/download", response_model=ModelDownloadResponse)
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
    target_id = resolve_layout_model_alias(model)

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

    if model in {"sam", "mobilesam", "mobile_sam"}:
        sam_id = "sam"
        with _download_tasks_lock:
            existing = _download_tasks.get(sam_id)
            if existing and existing.status == "downloading":
                return ModelDownloadResponse(
                    ok=True,
                    model=sam_id,
                    message="下载已在进行中",
                    status="downloading",
                )

        with _download_tasks_lock:
            _download_tasks[sam_id] = DownloadTask(model_id=sam_id)

        _save_download_tasks()

        thread = threading.Thread(
            target=_background_download_sam,
            args=(sam_id,),
            daemon=True,
        )
        thread.start()

        return ModelDownloadResponse(
            ok=True,
            model=sam_id,
            message="SAM 模型开始下载",
            status="downloading",
        )

    supported = ", ".join(sorted(LAYOUT_MODELS.keys())) + ", paddleocr, sam"
    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        message=f"Unsupported model for download: {payload.model}. Supported: {supported}",
        details={"model": payload.model},
        status_code=400,
    )


@download_router.get("/download/status", response_model=DownloadStatusResponse)
async def get_download_status():
    """Get status of all active/recent downloads.

    Returns download state for each model that is currently downloading or
    recently completed/failed/cancelled. Old entries are cleaned up after 5 minutes.
    """
    now = time.time()
    items: dict[str, DownloadStatusItem] = {}
    should_persist_cleanup = False

    with _download_tasks_lock:
        # Clean up old completed/failed/cancelled tasks (older than 5 minutes)
        expired_ids = [
            mid for mid, task in _download_tasks.items()
            if task.status != "downloading" and (now - task.started_at) > 300
        ]
        for mid in expired_ids:
            del _download_tasks[mid]

        if expired_ids:
            should_persist_cleanup = True

        for mid, task in _download_tasks.items():
            items[mid] = DownloadStatusItem(
                model_id=task.model_id,
                status=task.status,
                progress=task.progress,
                message=task.message,
                started_at=task.started_at,
            )

    if should_persist_cleanup:
        _save_download_tasks()

    return DownloadStatusResponse(downloads=items)


@download_router.post("/download/cancel", response_model=DownloadCancelResponse)
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
    target_id = resolve_layout_model_alias(model)
    if not target_id and model in {"paddleocr", "paddle", "paddle_ocr"}:
        target_id = "paddleocr"
    if not target_id and model in {"sam", "mobilesam", "mobile_sam"}:
        target_id = "sam"

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
# Model deletion helpers
# ---------------------------------------------------------------------------


def _delete_paddlex_model(model_id: str, model_info: LayoutModelInfo) -> bool:
    """Delete a PaddleX model from its cache directory."""
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
                shutil.rmtree(d)  # type: ignore[has-type]
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
        shutil.rmtree(model_dir)  # type: ignore[has-type]
        logger.info("Deleted DocLayout-YOLO model cache: %s", model_dir)
        return True
    except Exception as e:
        logger.warning("Failed to delete DocLayout-YOLO cache %s: %s", model_dir, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"Failed to delete model cache: {e}",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------


@download_router.post("/delete", response_model=ModelDeleteResponse)
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
    import shutil as _shutil  # G3b-G3: local import to avoid top-level dependency
    model = payload.model.strip().lower()

    # Resolve layout model aliases
    target_id = resolve_layout_model_alias(model)
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
                _shutil.rmtree(paddleocr_cache)
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

    if model in {"sam", "mobilesam", "mobile_sam"}:
        with _download_tasks_lock:
            task = _download_tasks.get("sam")
            if task and task.status == "downloading":
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="SAM 模型正在下载中，无法删除",
                    status_code=400,
                )

        sam_dir = Path(os.getenv("APP_DATA_DIR", "/app/data")) / "models" / "sam"
        deleted = False
        if sam_dir.exists():
            try:
                _shutil.rmtree(sam_dir)
                logger.info("Deleted SAM model cache: %s", sam_dir)
                deleted = True
            except Exception as e:
                logger.warning("Failed to delete SAM cache %s: %s", sam_dir, e)
                raise AppException(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to delete SAM cache: {e}",
                    status_code=500,
                )

        return ModelDeleteResponse(
            success=True,
            model=model_name,
            message="已删除 SAM 模型缓存" if deleted else "SAM 模型缓存不存在",
        )

    supported = ", ".join(sorted(LAYOUT_MODELS.keys())) + ", paddleocr, sam"
    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        message=f"Unsupported model for deletion: {payload.model}. Supported: {supported}",
        details={"model": payload.model},
        status_code=400,
    )
