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
    linuxdo_id = Column(Integer, unique=True, nullable=True, index=True)
    username = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=True, default="")
    avatar_url = Column(String(1024), nullable=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default=UserRole.user.value)
    trust_level = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    is_initial_admin = Column(Boolean, nullable=False, default=False)
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
    linuxdo_id: Optional[int] = None
    username: str
    name: Optional[str] = ""
    avatar_url: Optional[str] = None
    role: UserRole = UserRole.user
    trust_level: int = 0
    active: bool = True
    is_initial_admin: bool = False
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
    origin: Optional[str] = None


class TokenResponse(BaseModel):
    """JWT token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""

    refresh_token: str


# Invite code models


class InviteCodeORM(Base):
    """Invite code database model."""

    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    created_by = Column(Integer, nullable=False)  # admin user id
    used_by = Column(Integer, nullable=True)  # user id who used it
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<InviteCode(id={self.id}, code={self.code!r})>"


class InviteCodeResponse(BaseModel):
    """Invite code response model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    created_by: int
    used_by: Optional[int] = None
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime


class InviteCodeListResponse(BaseModel):
    """Invite code list response model."""

    invites: list[InviteCodeResponse]
    total: int


class RegisterRequest(BaseModel):
    """Register request model."""

    invite_code: str
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)


class LoginPasswordRequest(BaseModel):
    """Password login request model."""

    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    """Change password request model."""

    old_password: str
    new_password: str


# Site settings models (public mode)


class SiteSettingsORM(Base):
    """Global site settings (admin-configured, key-value store)."""

    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    value = Column(String(4096), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<SiteSettings(key={self.key!r})>"


class UserPreferencesORM(Base):
    """Per-user preferences (non-sensitive settings)."""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(String(4096), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<UserPreferences(user_id={self.user_id}, key={self.key!r})>"


class SiteSettingsResponse(BaseModel):
    """Site settings response model."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Optional[str] = None
    updated_at: Optional[datetime] = None


class SiteSettingsUpdateRequest(BaseModel):
    """Site settings update request."""

    settings: dict[str, Optional[str]]


class UserPreferencesResponse(BaseModel):
    """User preferences response model."""

    preferences: dict[str, Optional[str]]


class UserPreferencesUpdateRequest(BaseModel):
    """User preferences update request."""

    preferences: dict[str, Optional[str]]
