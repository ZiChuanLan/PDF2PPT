"""Helpers for API bearer-token access control."""

import secrets


def has_valid_bearer_token(
    authorization_header: str | None, expected_token: str | None
) -> bool:
    configured = str(expected_token or "").strip()
    if not configured:
        return True

    raw = str(authorization_header or "").strip()
    if not raw:
        return False

    scheme, _, token = raw.partition(" ")
    if scheme.lower() != "bearer":
        return False

    provided = token.strip()
    if not provided:
        return False

    return secrets.compare_digest(provided, configured)
