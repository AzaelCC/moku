from __future__ import annotations

from fastapi.testclient import TestClient
from moku_backend.config import Settings
from moku_backend.main import create_app


class FakeEngine:
    async def dispose(self) -> None:
        return None


def test_health_route(monkeypatch) -> None:
    monkeypatch.setattr("moku_backend.main.create_engine", lambda settings: FakeEngine())
    monkeypatch.setattr("moku_backend.main.create_sessionmaker", lambda engine: object())
    app = create_app(
        Settings(database_url="postgresql+asyncpg://unused/unused", app_name="Test Moku")
    )

    response = TestClient(app).get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app_name": "Test Moku"}
