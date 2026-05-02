"""Setup wizard API endpoints for first-time deployment."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth import create_token_pair, create_user_with_password
from app.config import get_settings
from app.database import get_db
from app.logging_config import get_logger
from app.models.error import AppException, ErrorCode
from app.models.user import SiteSettingsORM, UserORM, UserResponse, UserRole


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    """Set authentication cookies (mirrors auth.py pattern)."""
    secure = get_settings().cookie_secure
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


class SetupCompleteRequest(BaseModel):
    """Setup completion request."""
    deploy_mode: str = Field(..., pattern="^(self|public)$")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)


@router.get("/status")
async def get_setup_status(db: Session = Depends(get_db)):
    """Check if initial setup is needed.

    Returns { needs_setup: true } if no users exist in the database.
    """
    user_count = db.query(UserORM).count()
    return {"needs_setup": user_count == 0}


@router.post("/complete")
async def complete_setup(
    payload: SetupCompleteRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Complete first-time setup: set deploy mode and create admin account.

    This endpoint is only available when no users exist (needs_setup=true).
    """
    # Guard: only allow when no users exist
    user_count = db.query(UserORM).count()
    if user_count > 0:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Setup has already been completed",
            status_code=400,
        )

    # 1. Write deploy_mode to site_settings
    existing = db.query(SiteSettingsORM).filter(SiteSettingsORM.key == "deploy_mode").first()
    if existing:
        existing.value = payload.deploy_mode
    else:
        db.add(SiteSettingsORM(key="deploy_mode", value=payload.deploy_mode))
    db.commit()
    logger.info("Setup: deploy_mode set to %s", payload.deploy_mode)

    # 2. Create admin user
    user = create_user_with_password(
        db,
        username=payload.username,
        password=payload.password,
        role=UserRole.admin,
    )
    if not user:
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to create admin account",
            status_code=500,
        )

    # Mark as initial admin (protected from being disabled)
    user.is_initial_admin = True
    db.commit()

    # 3. Create JWT tokens and set cookies
    tokens = create_token_pair(user.id, user.role)
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])

    logger.info("Setup complete: admin user '%s' created, deploy_mode=%s", user.username, payload.deploy_mode)

    return {
        "user": UserResponse.model_validate(user).model_dump(),
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }
