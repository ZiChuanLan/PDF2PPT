"""FastAPI dependencies for authentication and authorization."""

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.database import get_db
from app.logging_config import get_logger
from app.models.user import UserORM, UserRole

logger = get_logger(__name__)


async def get_current_user(
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
) -> UserORM:
    """Get the current authenticated user from JWT cookie."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(access_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(UserORM).filter(UserORM.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_user_optional(
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
) -> Optional[UserORM]:
    """Get the current user if authenticated, otherwise None."""
    if not access_token:
        return None

    payload = decode_token(access_token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.query(UserORM).filter(UserORM.id == int(user_id)).first()
    if not user or not user.active:
        return None

    return user


async def require_admin(
    current_user: UserORM = Depends(get_current_user),
) -> UserORM:
    """Require the current user to be an admin."""
    if current_user.role != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
