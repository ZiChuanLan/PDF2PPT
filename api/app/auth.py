"""OAuth flow and JWT token management for LinuxDo authentication."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import bcrypt
import httpx
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models.user import InviteCodeORM, UserORM, UserRole

logger = get_logger(__name__)

# LinuxDo OAuth endpoints
LINUXDO_AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
LINUXDO_TOKEN_URL = "https://connect.linux.do/oauth2/token"
LINUXDO_USERINFO_URL = "https://connect.linux.do/api/user"

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# OAuth state TTL in seconds (10 minutes)
_STATE_EXPIRY_SECONDS = 600


def _get_state_redis():
    """Get Redis client for OAuth state storage."""
    from app.services.redis_service import get_redis_service
    return get_redis_service().redis_client


def generate_state() -> str:
    """Generate a random state parameter for OAuth flow."""
    state = secrets.token_urlsafe(32)
    try:
        _get_state_redis().setex(f"oauth_state:{state}", _STATE_EXPIRY_SECONDS, "1")
    except Exception as e:
        logger.warning("Failed to store OAuth state in Redis: %s", e)
    return state


def validate_state(state: str) -> bool:
    """Validate an OAuth state parameter."""
    try:
        key = f"oauth_state:{state}"
        redis_client = _get_state_redis()
        if redis_client.exists(key):
            redis_client.delete(key)
            return True
    except Exception as e:
        logger.warning("Failed to validate OAuth state from Redis: %s", e)
    return False


def get_authorize_url(state: str, origin: Optional[str] = None) -> str:
    """Build the LinuxDo OAuth authorization URL.

    If origin is provided, builds redirect_uri dynamically from it
    so cookies are set for the correct hostname (e.g., localhost vs 0.0.0.0).
    """
    settings = get_settings()
    if origin:
        redirect_uri = f"{origin.rstrip('/')}/auth/callback"
    else:
        redirect_uri = settings.linuxdo_redirect_uri
    params = {
        "response_type": "code",
        "client_id": settings.linuxdo_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "user",
    }
    return f"{LINUXDO_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Optional[dict]:
    """Exchange authorization code for access token."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                LINUXDO_TOKEN_URL,
                data={
                    "client_id": settings.linuxdo_client_id,
                    "client_secret": settings.linuxdo_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri or settings.linuxdo_redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if response.status_code != 200:
                logger.error(
                    "Token exchange failed: status=%d body=%s",
                    response.status_code,
                    response.text[:500],
                )
                return None
            return response.json()
        except Exception as e:
            logger.error("Token exchange error: %s", e)
            return None


async def fetch_user_info(access_token: str) -> Optional[dict]:
    """Fetch user info from LinuxDo API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                LINUXDO_USERINFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if response.status_code != 200:
                logger.error(
                    "User info fetch failed: status=%d body=%s",
                    response.status_code,
                    response.text[:500],
                )
                return None
            return response.json()
        except Exception as e:
            logger.error("User info fetch error: %s %s", type(e).__name__, e)
            return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning("JWT decode error: %s", e)
        return None


def create_token_pair(user_id: int, role: str) -> dict:
    """Create access and refresh token pair for a user."""
    access_token = create_access_token({"sub": str(user_id), "role": role})
    refresh_token = create_refresh_token({"sub": str(user_id), "role": role})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# Password hashing functions


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_user_with_password(
    db: Session, username: str, password: str, role: UserRole = UserRole.user
) -> Optional[UserORM]:
    """Create a new user with password authentication."""
    # Check if username already exists
    existing = db.query(UserORM).filter(UserORM.username == username).first()
    if existing:
        logger.warning("Username already exists: %s", username)
        return None

    password_hash = hash_password(password)
    user = UserORM(
        username=username,
        password_hash=password_hash,
        role=role.value,
        active=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        logger.info("Created new user with password: %s", username)
        return user
    except IntegrityError:
        db.rollback()
        logger.error("Failed to create user: %s", username)
        return None


# Invite code functions


def generate_invite_code(db: Session, created_by: int, expires_in_days: int = 7) -> Optional[str]:
    """Generate a new invite code."""
    code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    invite = InviteCodeORM(
        code=code,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(invite)
    try:
        db.commit()
        logger.info("Generated invite code by user %d", created_by)
        return code
    except IntegrityError:
        db.rollback()
        logger.error("Failed to generate invite code")
        return None


def validate_invite_code(db: Session, code: str) -> Optional[InviteCodeORM]:
    """Validate an invite code and return it if valid."""
    invite = db.query(InviteCodeORM).filter(InviteCodeORM.code == code).first()
    if not invite:
        return None
    if invite.used_by is not None:
        return None
    if invite.expires_at < datetime.now(timezone.utc):
        return None
    return invite


def use_invite_code(db: Session, invite: InviteCodeORM, user_id: int) -> bool:
    """Mark an invite code as used."""
    invite.used_by = user_id
    invite.used_at = datetime.now(timezone.utc)
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error("Failed to mark invite code as used: %s", e)
        return False


def authenticate_user(db: Session, username: str, password: str) -> Optional[UserORM]:
    """Authenticate user with username and password."""
    user = db.query(UserORM).filter(UserORM.username == username).first()
    if not user:
        logger.warning("User not found: %s", username)
        return None
    if not user.password_hash:
        logger.warning("User has no password set: %s", username)
        return None
    if not verify_password(password, user.password_hash):
        logger.warning("Invalid password for user: %s", username)
        return None
    if not user.active:
        logger.warning("User is disabled: %s", username)
        return None

    # Update last login time
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(db: Session, userinfo: dict) -> Optional[UserORM]:
    """Get existing user or create new user from LinuxDo userinfo."""
    linuxdo_id = userinfo.get("id")
    if not linuxdo_id:
        logger.error("No user id in userinfo response")
        return None

    user = db.query(UserORM).filter(UserORM.linuxdo_id == linuxdo_id).first()

    username = userinfo.get("username", "")
    name = userinfo.get("name", "")
    avatar_template = userinfo.get("avatar_template", "")

    # Build full avatar URL if it's a template
    avatar_url = avatar_template
    if avatar_url and not avatar_url.startswith("http"):
        avatar_url = f"https://linux.do{avatar_template}"

    trust_level = userinfo.get("trust_level", 0)
    active = userinfo.get("active", True)

    settings = get_settings()
    admin_names = {n.strip().lower() for n in settings.admin_usernames.split(",") if n.strip()}
    is_admin = username.lower() in admin_names

    if user:
        # Update existing user
        user.username = username
        user.name = name or user.name
        user.avatar_url = avatar_url
        user.trust_level = trust_level
        user.active = active
        user.last_login_at = datetime.now(timezone.utc)
        if is_admin and user.role != UserRole.admin.value:
            user.role = UserRole.admin.value
            logger.info("Promoted user to admin: %s", username)
        db.commit()
        db.refresh(user)
        logger.info("Updated user: %s (linuxdo_id=%d)", username, linuxdo_id)
    else:
        # Create new user (handle race condition: another worker may have inserted)
        user = UserORM(
            linuxdo_id=linuxdo_id,
            username=username,
            name=name,
            avatar_url=avatar_url,
            role=UserRole.admin.value if is_admin else UserRole.user.value,
            trust_level=trust_level,
            active=active,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            logger.info("Created new user: %s (linuxdo_id=%d)", username, linuxdo_id)
        except IntegrityError:
            db.rollback()
            user = db.query(UserORM).filter(UserORM.linuxdo_id == linuxdo_id).first()
            if user:
                user.last_login_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(user)
                logger.info("User already existed, updated: %s (linuxdo_id=%d)", username, linuxdo_id)
            else:
                logger.error("Failed to create or retrieve user after IntegrityError")
                return None

    return user
