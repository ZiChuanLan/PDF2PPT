"""Admin API endpoints for user management."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_logger
from app.models.error import AppException, ErrorCode
from app.models.job import JobStatus
from app.models.user import (
    UserListResponse,
    UserORM,
    UserResponse,
    UserUpdateRequest,
)
from app.services.redis_service import get_redis_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users (admin only)."""
    total = db.query(UserORM).count()
    users = (
        db.query(UserORM)
        .order_by(UserORM.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get user details (admin only)."""
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"User {user_id} not found",
            status_code=404,
        )
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update user settings (admin only)."""
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"User {user_id} not found",
            status_code=404,
        )

    # Prevent admin from deactivating or demoting themselves
    if user_id == admin.id:
        if payload.active is not None and not payload.active:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Cannot deactivate your own account",
                status_code=400,
            )
        if payload.role is not None and payload.role.value != admin.role:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Cannot change your own role",
                status_code=400,
            )

    if payload.role is not None:
        user.role = payload.role.value
    if payload.active is not None:
        user.active = payload.active
    if payload.daily_task_limit is not None:
        user.daily_task_limit = payload.daily_task_limit
    if payload.max_file_size_mb is not None:
        user.max_file_size_mb = payload.max_file_size_mb
    if payload.concurrent_task_limit is not None:
        user.concurrent_task_limit = payload.concurrent_task_limit

    db.commit()
    db.refresh(user)

    logger.info("Admin updated user %d: %s", user_id, payload.model_dump(exclude_none=True))
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/tasks")
async def get_user_tasks(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get tasks for a specific user (admin only)."""
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"User {user_id} not found",
            status_code=404,
        )

    redis_service = get_redis_service()
    all_jobs = redis_service.list_jobs(limit=1000)

    # Filter jobs by user_id
    user_jobs = [
        j for j in all_jobs
        if hasattr(j, "user_id") and getattr(j, "user_id", None) == user_id
    ][:limit]

    return {
        "user_id": user_id,
        "username": user.username,
        "tasks": [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "created_at": j.created_at.isoformat(),
                "message": j.message,
            }
            for j in user_jobs
        ],
        "total": len(user_jobs),
    }


@router.get("/stats")
async def get_admin_stats(
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get admin dashboard statistics (admin only)."""
    total_users = db.query(UserORM).count()
    active_users = db.query(UserORM).filter(UserORM.active == True).count()
    admin_users = db.query(UserORM).filter(UserORM.role == "admin").count()

    redis_service = get_redis_service()
    all_jobs = redis_service.list_jobs(limit=10000)

    total_jobs = len(all_jobs)
    pending_jobs = sum(1 for j in all_jobs if j.status == JobStatus.pending)
    processing_jobs = sum(1 for j in all_jobs if j.status == JobStatus.processing)
    completed_jobs = sum(1 for j in all_jobs if j.status == JobStatus.completed)
    failed_jobs = sum(1 for j in all_jobs if j.status == JobStatus.failed)

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "admins": admin_users,
        },
        "jobs": {
            "total": total_jobs,
            "pending": pending_jobs,
            "processing": processing_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
        },
    }
