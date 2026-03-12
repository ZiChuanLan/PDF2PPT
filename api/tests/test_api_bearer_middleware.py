from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import main


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        return await main.request_id_middleware(request, call_next)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def test_api_requests_require_configured_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", "secret-token")

    client = TestClient(_build_test_app())
    response = client.get("/api/ping")

    assert response.status_code == 401
    assert response.json() == {
        "code": "auth_required",
        "message": "Missing or invalid API bearer token",
    }
    assert response.headers["X-Request-ID"]


def test_api_requests_accept_matching_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", "secret-token")

    client = TestClient(_build_test_app())
    response = client.get(
        "/api/ping",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["X-Request-ID"]


def test_api_requests_do_not_require_token_when_auth_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", None)

    client = TestClient(_build_test_app())
    response = client.get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
