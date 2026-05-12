"""Security utilities for CSRF protection, password validation, and log sanitization."""

import re
import secrets
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# CSRF Protection
# ---------------------------------------------------------------------------
_CSRF_TOKEN_BYTES = 32
_CSRF_EXPIRY_SECONDS = 3600  # 1 hour


def _get_csrf_redis():
    """Get Redis client for CSRF token storage."""
    from app.services.redis_service import get_redis_service
    return get_redis_service().redis_client


def generate_csrf_token() -> str:
    """Generate a random CSRF token and store it in Redis."""
    token = secrets.token_urlsafe(_CSRF_TOKEN_BYTES)
    try:
        _get_csrf_redis().setex(f"csrf_token:{token}", _CSRF_EXPIRY_SECONDS, "1")
    except Exception as e:
        logger.warning("Failed to store CSRF token in Redis: %s", e)
    return token


def validate_csrf_token(token: str | None) -> bool:
    """Validate a CSRF token and consume it (one-time use)."""
    if not token:
        return False
    try:
        key = f"csrf_token:{token}"
        redis_client = _get_csrf_redis()
        if redis_client.exists(key):
            redis_client.delete(key)
            return True
    except Exception as e:
        logger.warning("Failed to validate CSRF token from Redis: %s", e)
    return False


# ---------------------------------------------------------------------------
# Password Policy
# ---------------------------------------------------------------------------
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 100


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Validate password meets complexity requirements.

    Requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit

    Returns:
        (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"

    if len(password) < _PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"

    if len(password) > _PASSWORD_MAX_LENGTH:
        return False, f"Password must not exceed {_PASSWORD_MAX_LENGTH} characters"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    return True, None


# ---------------------------------------------------------------------------
# Log Sanitization
# ---------------------------------------------------------------------------
_SENSITIVE_PATTERNS = [
    # API keys
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE), "sk-***REDACTED***"),
    (re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([a-zA-Z0-9_\-]{16,})", re.IGNORECASE), r"\1***REDACTED***"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE), r"\1***REDACTED***"),
    # Authorization headers
    (re.compile(r"(Authorization[\"']?\s*[:=]\s*[\"']?)([^\s\"']{20,})", re.IGNORECASE), r"\1***REDACTED***"),
    # JWT tokens (long base64 strings with dots)
    (re.compile(r"(eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,})", re.IGNORECASE), "***JWT_REDACTED***"),
    # Generic secrets/passwords in JSON
    (re.compile(r"([\"'](?:secret|password|token|key)[\"']\s*:\s*[\"'])([^\"']{8,})([\"'])", re.IGNORECASE), r"\1***REDACTED***\3"),
]


def sanitize_log_message(message: str) -> str:
    """Sanitize log message by redacting sensitive patterns.

    Redacts:
    - API keys (sk-*, api_key=...)
    - Bearer tokens
    - JWT tokens
    - Authorization headers
    - Secret/password values in JSON

    Args:
        message: Log message to sanitize

    Returns:
        Sanitized message with sensitive data redacted
    """
    if not message:
        return message

    sanitized = message
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_log_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize a dictionary for logging.

    Redacts values for keys that look sensitive (case-insensitive):
    - password, secret, token, api_key, authorization, bearer

    Args:
        data: Dictionary to sanitize

    Returns:
        New dictionary with sensitive values redacted
    """
    if not isinstance(data, dict):
        return data

    sensitive_keys = {
        "password", "secret", "token", "api_key", "apikey",
        "authorization", "bearer", "access_token", "refresh_token",
        "client_secret", "jwt", "key"
    }

    sanitized = {}
    for key, value in data.items():
        key_lower = str(key).lower()

        # Check if key is sensitive
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_log_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str):
            # Sanitize string values that might contain tokens
            sanitized[key] = sanitize_log_message(value)
        else:
            sanitized[key] = value

    return sanitized
