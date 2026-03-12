from __future__ import annotations

import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import api_auth


def test_has_valid_bearer_token_requires_matching_bearer_value() -> None:
    assert api_auth.has_valid_bearer_token("Bearer secret-token", "secret-token") is True
    assert api_auth.has_valid_bearer_token("Bearer wrong-token", "secret-token") is False
    assert api_auth.has_valid_bearer_token(None, "secret-token") is False
    assert api_auth.has_valid_bearer_token("Basic abc", "secret-token") is False


def test_has_valid_bearer_token_allows_requests_when_not_configured() -> None:
    assert api_auth.has_valid_bearer_token(None, None) is True
    assert api_auth.has_valid_bearer_token(None, "") is True
