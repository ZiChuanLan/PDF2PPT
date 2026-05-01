"""Auth API endpoints for LinuxDo OAuth login."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.auth import (
    create_token_pair,
    decode_token,
    exchange_code_for_token,
    fetch_user_info,
    generate_state,
    get_authorize_url,
    get_or_create_user,
    validate_state,
)
from app.database import get_db
from app.dependencies import get_current_user
from app.logging_config import get_logger
from app.models.error import AppException, ErrorCode
from app.models.user import (
    AuthCallbackRequest,
    QuotaInfo,
    RefreshTokenRequest,
    TokenResponse,
    UserORM,
    UserResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/login")
async def login():
    """Initiate LinuxDo OAuth login flow.

    Returns the authorization URL for the user to visit.
    """
    state = generate_state()
    authorize_url = get_authorize_url(state)
    return {
        "authorize_url": authorize_url,
        "state": state,
    }


@router.post("/callback")
async def callback(
    payload: AuthCallbackRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Handle OAuth callback with authorization code.

    Exchanges the code for tokens, fetches user info, and sets JWT cookies.
    """
    # Validate state
    if not validate_state(payload.state):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid or expired OAuth state",
            status_code=400,
        )

    # Exchange code for token
    token_data = await exchange_code_for_token(payload.code)
    if not token_data:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Failed to exchange authorization code for token",
            status_code=400,
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="No access token in response",
            status_code=400,
        )

    # Fetch user info
    userinfo = await fetch_user_info(access_token)
    if not userinfo:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Failed to fetch user info from LinuxDo",
            status_code=400,
        )

    # Get or create user in database
    user = get_or_create_user(db, userinfo)
    if not user:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Failed to create or update user",
            status_code=500,
        )

    # Create JWT tokens
    tokens = create_token_pair(user.id, user.role)

    # Set cookies
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])

    logger.info("User %s logged in successfully", user.username)

    return {
        "user": UserResponse.model_validate(user).model_dump(),
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
    }


@router.get("/me")
async def get_me(
    current_user: UserORM = Depends(get_current_user),
):
    """Get current authenticated user info."""
    return UserResponse.model_validate(current_user).model_dump()


@router.post("/logout")
async def logout(response: Response):
    """Logout by clearing auth cookies."""
    from app.config import get_settings
    secure = get_settings().cookie_secure
    response.delete_cookie("access_token", path="/", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie("refresh_token", path="/", httponly=True, secure=secure, samesite="lax")
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token(
    response: Response,
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    body: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
):
    """Refresh access token using refresh token."""
    token = body.refresh_token if body else refresh_token_cookie
    if not token:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Refresh token required",
            status_code=400,
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid or expired refresh token",
            status_code=401,
        )

    user_id = payload.get("sub")
    if not user_id:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid token payload",
            status_code=401,
        )

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid token payload",
            status_code=401,
        )

    user = db.query(UserORM).filter(UserORM.id == user_id_int).first()
    if not user or not user.active:
        raise AppException(
            code=ErrorCode.AUTH_FAILED,
            message="User not found or disabled",
            status_code=401,
        )

    # Create new token pair
    tokens = create_token_pair(user.id, user.role)
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])

    return {
        "token_type": "bearer",
        "expires_in": tokens["expires_in"],
    }


@router.get("/quota")
async def get_quota(
    current_user: UserORM = Depends(get_current_user),
):
    """Get current user's quota information."""
    from app.services.redis_service import get_redis_service

    redis_service = get_redis_service()

    # Count today's tasks
    all_jobs = redis_service.list_jobs(limit=1000)
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tasks_today = sum(
        1
        for j in all_jobs
        if j.created_at >= today_start
        and hasattr(j, "user_id")
        and getattr(j, "user_id", None) == current_user.id
    )

    # Count active tasks
    from app.models.job import JobStatus

    active_tasks = sum(
        1
        for j in all_jobs
        if j.status in {JobStatus.pending, JobStatus.processing}
        and hasattr(j, "user_id")
        and getattr(j, "user_id", None) == current_user.id
    )

    return QuotaInfo(
        daily_task_limit=current_user.daily_task_limit,
        max_file_size_mb=current_user.max_file_size_mb,
        concurrent_task_limit=current_user.concurrent_task_limit,
        tasks_today=tasks_today,
        active_tasks=active_tasks,
    ).model_dump()


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    """Set authentication cookies."""
    from app.config import get_settings
    secure = get_settings().cookie_secure
    # Access token cookie - 1 hour
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Refresh token cookie - 30 days
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
