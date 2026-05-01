"""User and Quota models for LinuxDo OAuth authentication."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class UserRole(str, Enum):
    """User role enum."""
    user = "user"
    admin = "admin"


# SQLAlchemy models


class UserORM(Base):
    """User database model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    linuxdo_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True, default="")
    avatar_url = Column(String(1024), nullable=True)
    role = Column(String(20), nullable=False, default=UserRole.user.value)
    trust_level = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Quota fields
    daily_task_limit = Column(Integer, nullable=False, default=10)
    max_file_size_mb = Column(Float, nullable=False, default=100.0)
    concurrent_task_limit = Column(Integer, nullable=False, default=2)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, linuxdo_id={self.linuxdo_id}, username={self.username!r})>"


# Pydantic models for API


class UserResponse(BaseModel):
    """User response model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    linuxdo_id: int
    username: str
    name: Optional[str] = ""
    avatar_url: Optional[str] = None
    role: UserRole = UserRole.user
    trust_level: int = 0
    active: bool = True
    created_at: datetime
    last_login_at: Optional[datetime] = None
    daily_task_limit: int = 10
    max_file_size_mb: float = 100.0
    concurrent_task_limit: int = 2


class UserListResponse(BaseModel):
    """User list response model."""

    users: list[UserResponse]
    total: int


class UserUpdateRequest(BaseModel):
    """Admin user update request model."""

    role: Optional[UserRole] = None
    active: Optional[bool] = None
    daily_task_limit: Optional[int] = Field(None, ge=0, le=1000)
    max_file_size_mb: Optional[float] = Field(None, ge=0, le=10000)
    concurrent_task_limit: Optional[int] = Field(None, ge=0, le=100)


class QuotaInfo(BaseModel):
    """User quota information."""

    daily_task_limit: int = 10
    max_file_size_mb: float = 100.0
    concurrent_task_limit: int = 2
    tasks_today: int = 0
    active_tasks: int = 0


class AuthCallbackRequest(BaseModel):
    """OAuth callback request model."""

    code: str
    state: str


class TokenResponse(BaseModel):
    """JWT token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""

    refresh_token: str
