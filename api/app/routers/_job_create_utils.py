# pyright: reportMissingImports=false

"""Shared job creation helpers for v1 and v2 endpoints (R3-G3b)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import get_settings
from ..logging_config import get_logger
from ..models.error import AppException, ErrorCode
from ..models.job import JobStage, JobStatus

if TYPE_CHECKING:
    from ..config import Settings
    from ..models.user import UserORM
    from ..services.redis_service import RedisService

logger = get_logger(__name__)


def check_disk_space(settings: "Settings") -> None:
    """Verify sufficient disk space exists before accepting an upload job."""
    _job_root = Path(settings.job_root_dir)
    _job_root.mkdir(parents=True, exist_ok=True)
    _disk = shutil.disk_usage(_job_root)
    _min_bytes = settings.min_disk_space_mb * 1024 * 1024
    if _disk.free < _min_bytes:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=(
                f"磁盘空间不足，剩余 {_disk.free // (1024*1024)}MB，"
                f"需要至少 {settings.min_disk_space_mb}MB"
            ),
            details={
                "free_mb": _disk.free // (1024 * 1024),
                "required_mb": settings.min_disk_space_mb,
            },
        )


def create_job_record_and_check_quotas(
    *,
    redis_service: "RedisService",
    job_id: str,
    current_user: "UserORM | None",
) -> tuple[str, Any]:
    """Create job in Redis, enforce user quotas, return (user_id, job_record).

    Raises AppException on quota violations.
    """
    user_id = current_user.id if current_user else None

    if current_user:
        # Check concurrent task limit
        if current_user.concurrent_task_limit > 0:
            active_jobs = redis_service.count_active_jobs_for_user(user_id)
            if active_jobs >= current_user.concurrent_task_limit:
                raise AppException(
                    code=ErrorCode.QUOTA_EXCEEDED,
                    message=(
                        f"Concurrent task limit reached "
                        f"({current_user.concurrent_task_limit})"
                    ),
                    details={
                        "limit": current_user.concurrent_task_limit,
                        "active": active_jobs,
                    },
                )

        # Check daily task limit
        if current_user.daily_task_limit > 0:
            daily_jobs = redis_service.count_daily_jobs_for_user(user_id)
            if daily_jobs >= current_user.daily_task_limit:
                raise AppException(
                    code=ErrorCode.QUOTA_EXCEEDED,
                    message=(
                        f"Daily task limit reached "
                        f"({current_user.daily_task_limit})"
                    ),
                    details={
                        "limit": current_user.daily_task_limit,
                        "used": daily_jobs,
                    },
                )

    job = redis_service.create_job(job_id, user_id=user_id)
    return user_id, job


def persist_job_queued(redis_service: "RedisService", job_id: str) -> None:
    """Persist queued state before starting worker execution.

    Ensures debug events remain ordered even when a local in-process worker
    begins immediately.
    """
    redis_service.update_job(
        job_id,
        status=JobStatus.pending,
        stage=JobStage.queued,
        message="Job queued for processing",
    )


def cleanup_job_on_error(
    *,
    job_dir: Path | None,
    job_id: str,
    redis_service: "RedisService",
    job_created: bool,
) -> None:
    """Clean up job directory and Redis record on creation failure.

    Call from within the outermost error handler of create_job / create_job_v2.
    Silently swallows cleanup errors (logged internally) to avoid masking the
    original exception.
    """
    if job_created:
        try:
            redis_service.delete_job(job_id)
        except Exception as cleanup_error:
            logger.exception(
                "Failed to rollback job metadata for %s: %s",
                job_id,
                cleanup_error,
            )
    if job_dir is not None and job_dir.exists():
        shutil.rmtree(job_dir)
