"""OAuth flow and JWT token management for LinuxDo authentication."""

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models.user import UserORM, UserRole

logger = get_logger(__name__)

# LinuxDo OAuth endpoints
LINUXDO_AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
LINUXDO_TOKEN_URL = "https://connect.linux.do/oauth2/token"
LINUXDO_USERINFO_URL = "https://connect.linux.do/api/user"

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# In-memory state store for OAuth flow (state -> timestamp)
_oauth_states: dict[str, float] = {}
_STATE_EXPIRY_SECONDS = 600  # 10 minutes


def _cleanup_expired_states() -> None:
    """Remove expired OAuth states."""
    now = time.time()
    expired = [s for s, ts in _oauth_states.items() if now - ts > _STATE_EXPIRY_SECONDS]
    for s in expired:
        _oauth_states.pop(s, None)


def generate_state() -> str:
    """Generate a random state parameter for OAuth flow."""
    _cleanup_expired_states()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    return state


def validate_state(state: str) -> bool:
    """Validate an OAuth state parameter."""
    _cleanup_expired_states()
    if state not in _oauth_states:
        return False
    _oauth_states.pop(state)
    return True


def get_authorize_url(state: str) -> str:
    """Build the LinuxDo OAuth authorization URL."""
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.linuxdo_client_id,
        "redirect_uri": settings.linuxdo_redirect_uri,
        "state": state,
        "scope": "user",
    }
    return f"{LINUXDO_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> Optional[dict]:
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
                    "redirect_uri": settings.linuxdo_redirect_uri,
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
            logger.error("User info fetch error: %s", e)
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

    if user:
        # Update existing user
        user.username = username
        user.name = name or user.name
        user.avatar_url = avatar_url
        user.trust_level = trust_level
        user.active = active
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        logger.info("Updated user: %s (linuxdo_id=%d)", username, linuxdo_id)
    else:
        # Create new user
        user = UserORM(
            linuxdo_id=linuxdo_id,
            username=username,
            name=name,
            avatar_url=avatar_url,
            role=UserRole.user.value,
            trust_level=trust_level,
            active=active,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created new user: %s (linuxdo_id=%d)", username, linuxdo_id)

    return user
