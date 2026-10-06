import asyncio
from types import SimpleNamespace

from fastapi.security import HTTPAuthorizationCredentials

import app.api.ml_routes as ml_routes


def _clear(monkeypatch):
    for name in ("ENV", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "CORE_ML_PUBLIC_COMPUTE"):
        monkeypatch.delenv(name, raising=False)


def test_production_defaults_to_private_compute(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert ml_routes._public_compute_allowed() is False


def test_explicit_public_override_is_respected(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("CORE_ML_PUBLIC_COMPUTE", "true")
    assert ml_routes._public_compute_allowed() is True


def test_predict_permission_allows_compute(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    async def fake_current_principal(credentials, session_token):
        return SimpleNamespace(permissions=["ung.core.ml.predict"])

    monkeypatch.setattr(ml_routes, "current_principal", fake_current_principal)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")
    asyncio.run(ml_routes.ml_compute_guard(credentials, None))
