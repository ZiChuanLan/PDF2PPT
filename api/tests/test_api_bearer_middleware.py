from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx
from fastapi import FastAPI


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import main
from app.services import redis_service


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        return await main.request_id_middleware(request, call_next)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    @app.get("/api/v1/models/status")
    async def model_status():
        return {"ok": True}

    @app.get("/api/v1/models/download/status")
    async def model_download_status():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _get(path: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_build_test_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, headers=headers)

    return anyio.run(_request)


def test_api_requests_require_configured_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", "secret-token")

    response = _get("/api/ping")

    assert response.status_code == 401
    assert response.json() == {
        "code": "auth_required",
        "message": "Missing or invalid API bearer token",
    }
    assert response.headers["X-Request-ID"]


def test_api_requests_accept_matching_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", "secret-token")

    response = _get(
        "/api/ping",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["X-Request-ID"]


def test_api_requests_do_not_require_token_when_auth_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_bearer_token", None)

    response = _get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_model_status_polling_is_not_rate_limited(monkeypatch) -> None:
    class _DenyingRedisService:
        def check_rate_limit(self, client_ip: str, max_requests: int, window_seconds: int):
            _ = client_ip
            _ = max_requests
            _ = window_seconds
            return False, 0

    monkeypatch.setattr(main.settings, "api_bearer_token", None)
    monkeypatch.setattr(main, "_resolve_public_rate_limit", lambda: (True, 60, 60))
    monkeypatch.setattr(redis_service, "get_redis_service", lambda: _DenyingRedisService())

    response = _get("/api/v1/models/status")
    download_response = _get("/api/v1/models/download/status")
    regular_response = _get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert download_response.status_code == 200
    assert download_response.json() == {"ok": True}
    assert regular_response.status_code == 429
    assert regular_response.json()["code"] == "rate_limit_exceeded"


def test_self_deploy_mode_skips_global_rate_limit(monkeypatch) -> None:
    class _DenyingRedisService:
        def check_rate_limit(self, client_ip: str, max_requests: int, window_seconds: int):
            _ = client_ip
            _ = max_requests
            _ = window_seconds
            return False, 0

    monkeypatch.setattr(main.settings, "api_bearer_token", None)
    monkeypatch.setattr(main, "_resolve_public_rate_limit", lambda: (False, 60, 60))
    monkeypatch.setattr(redis_service, "get_redis_service", lambda: _DenyingRedisService())

    response = _get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_public_rate_limit_uses_site_setting_values(monkeypatch) -> None:
    class _FakeQuery:
        def filter(self, *args, **kwargs):
            _ = args
            _ = kwargs
            return self

        def all(self):
            return [
                SimpleNamespace(key="deploy_mode", value="public"),
                SimpleNamespace(key="rate_limit_requests", value="7"),
                SimpleNamespace(key="rate_limit_window_seconds", value="11"),
            ]

    class _FakeSession:
        def query(self, model):
            _ = model
            return _FakeQuery()

        def close(self):
            return None

    from app import database

    monkeypatch.setattr(main.settings, "deploy_mode", "self")
    monkeypatch.setattr(main.settings, "rate_limit_requests", 60)
    monkeypatch.setattr(main.settings, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(database, "get_session_factory", lambda: lambda: _FakeSession())

    assert main._resolve_public_rate_limit() == (True, 7, 11)
