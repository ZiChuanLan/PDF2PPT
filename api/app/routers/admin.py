"""Admin API endpoints for user management."""

import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import create_user_with_password, generate_invite_code
from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_logger
from app.models.error import AppException, ErrorCode
from app.models.job import JobStatus
from app.models.user import (
    InviteCodeListResponse,
    InviteCodeORM,
    InviteCodeResponse,
    SiteSettingsORM,
    SiteSettingsResponse,
    SiteSettingsUpdateRequest,
    UserListResponse,
    UserORM,
    UserResponse,
    UserRole,
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


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.user


class BatchDeleteRequest(BaseModel):
    user_ids: list[int]


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=100)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: int,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft delete a user (set active=False) (admin only)."""
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"User {user_id} not found",
            status_code=404,
        )

    if user_id == admin.id:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Cannot delete your own account",
            status_code=400,
        )

    if user.is_initial_admin:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Cannot disable the initial admin account",
            status_code=400,
        )

    user.active = False
    db.commit()
    db.refresh(user)

    logger.info("Admin soft-deleted user %d: %s", user_id, user.username)
    return UserResponse.model_validate(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    payload: CreateUserRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user with password (admin only)."""
    user = create_user_with_password(db, payload.username, payload.password, payload.role)
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Username already exists",
            status_code=400,
        )

    logger.info("Admin created user %s (role=%s)", user.username, payload.role.value)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset a user's password (admin only). No old password required."""
    from app.auth import hash_password

    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"User {user_id} not found",
            status_code=404,
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)

    logger.info("Admin reset password for user %d: %s", user_id, user.username)
    return {"message": "密码已重置"}


@router.post("/users/batch-delete")
async def batch_delete_users(
    payload: BatchDeleteRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Batch soft delete users (admin only)."""
    if not payload.user_ids:
        return {"deleted": 0, "skipped": 0}

    # Filter out admin's own ID
    ids_to_delete = [uid for uid in payload.user_ids if uid != admin.id]
    skipped = len(payload.user_ids) - len(ids_to_delete)

    users = db.query(UserORM).filter(UserORM.id.in_(ids_to_delete)).all()
    deleted = 0
    for user in users:
        if user.active and not user.is_initial_admin:
            user.active = False
            deleted += 1
        elif user.is_initial_admin:
            skipped += 1

    db.commit()

    logger.info("Admin batch-deleted %d users (skipped %d)", deleted, skipped)
    return {"deleted": deleted, "skipped": skipped}


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


@router.post("/invites", response_model=InviteCodeResponse)
async def create_invite(
    expires_in_days: int = Query(7, ge=1, le=30),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Generate a new invite code (admin only)."""
    code = generate_invite_code(db, admin.id, expires_in_days)
    if not code:
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to generate invite code",
            status_code=500,
        )

    invite = db.query(InviteCodeORM).filter(InviteCodeORM.code == code).first()
    return InviteCodeResponse.model_validate(invite)


@router.get("/invites", response_model=InviteCodeListResponse)
async def list_invites(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all invite codes (admin only)."""
    total = db.query(InviteCodeORM).count()
    invites = (
        db.query(InviteCodeORM)
        .order_by(InviteCodeORM.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return InviteCodeListResponse(
        invites=[InviteCodeResponse.model_validate(i) for i in invites],
        total=total,
    )


# ---------------------------------------------------------------------------
# Environment variable editor
# ---------------------------------------------------------------------------

ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

# Keys whose values should be masked in the GET response
SENSITIVE_KEYS = {
    "jwt_secret",
    "linuxdo_client_secret",
    "api_bearer_token",
    "web_access_password",
}


class EnvVar(BaseModel):
    key: str
    value: str
    is_sensitive: bool = False


class EnvVarsResponse(BaseModel):
    vars: list[EnvVar]
    raw: str


class EnvVarsUpdateRequest(BaseModel):
    vars: dict[str, str]


def _parse_env_file(path: str) -> tuple[list[EnvVar], str]:
    """Parse .env file into structured vars and return raw content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return [], ""

    env_vars: list[EnvVar] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2)
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key in seen:
            continue
        seen.add(key)
        env_vars.append(EnvVar(
            key=key,
            value=value,
            is_sensitive=key.lower() in SENSITIVE_KEYS,
        ))
    return env_vars, raw


def _update_env_content(raw: str, updates: dict[str, str]) -> str:
    """Update key=value pairs in raw .env content, preserving comments and order."""
    lines = raw.splitlines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            new_lines.append(line)
            continue
        key = match.group(1)
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append keys that weren't in the original file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    return "\n".join(new_lines) + "\n"


@router.get("/env", response_model=EnvVarsResponse)
async def get_env_vars(
    admin: UserORM = Depends(require_admin),
):
    """Read environment variables from .env file (admin only)."""
    env_vars, raw = _parse_env_file(ENV_FILE_PATH)
    # Mask sensitive values
    masked_vars = []
    for v in env_vars:
        if v.is_sensitive and v.value:
            masked_vars.append(EnvVar(key=v.key, value="••••••••", is_sensitive=True))
        else:
            masked_vars.append(v)
    return EnvVarsResponse(vars=masked_vars, raw=raw)


@router.put("/env", response_model=EnvVarsResponse)
async def update_env_vars(
    payload: EnvVarsUpdateRequest,
    admin: UserORM = Depends(require_admin),
):
    """Update environment variables in .env file (admin only).

    Only updates keys provided in the payload; other keys are preserved.
    Sensitive keys are only updated if the value is not the masked placeholder.
    Changes take effect after container restart.
    """
    try:
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raw = ""

    # Filter out masked sensitive values (don't overwrite with the mask)
    filtered_updates = {}
    for key, value in payload.vars.items():
        if key.lower() in SENSITIVE_KEYS and value == "••••••••":
            continue
        filtered_updates[key] = value

    if filtered_updates:
        new_content = _update_env_content(raw, filtered_updates)
        os.makedirs(os.path.dirname(ENV_FILE_PATH), exist_ok=True)
        with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)

    logger.info("Admin updated .env file: %s", list(filtered_updates.keys()))

    # Re-read and return
    env_vars, new_raw = _parse_env_file(ENV_FILE_PATH)
    masked_vars = []
    for v in env_vars:
        if v.is_sensitive and v.value:
            masked_vars.append(EnvVar(key=v.key, value="••••••••", is_sensitive=True))
        else:
            masked_vars.append(v)
    return EnvVarsResponse(vars=masked_vars, raw=new_raw)


# --- Site Settings (public mode) ---

# Keys that contain sensitive API keys
SENSITIVE_SETTING_KEYS = {
    "openai_api_key", "claude_api_key",
    "mineru_api_token", "ocr_baidu_api_key", "ocr_baidu_secret_key",
    "ocr_ai_api_key",
}


@router.get("/site-settings", response_model=dict[str, Optional[str]])
async def get_site_settings(
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get all site settings (admin only)."""
    rows = db.query(SiteSettingsORM).all()
    settings = {}
    for row in rows:
        if row.key in SENSITIVE_SETTING_KEYS and row.value:
            settings[row.key] = "••••••••"
        else:
            settings[row.key] = row.value
    return settings


@router.put("/site-settings")
async def update_site_settings(
    payload: SiteSettingsUpdateRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update site settings (admin only)."""
    updated = []
    for key, value in payload.settings.items():
        # Skip masked sensitive values
        if key in SENSITIVE_SETTING_KEYS and value == "••••••••":
            continue
        existing = db.query(SiteSettingsORM).filter(SiteSettingsORM.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(SiteSettingsORM(key=key, value=value))
        updated.append(key)
    db.commit()
    logger.info("Admin updated site settings: %s", updated)
    return {"updated": updated}
