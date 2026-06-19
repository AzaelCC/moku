from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_sample_import_to_recommendations_vertical_path(monkeypatch) -> None:
    database_url = os.getenv("MOKU_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set MOKU_TEST_DATABASE_URL to run Postgres integration tests.")

    pytest.importorskip("alembic")
    pytest.importorskip("asyncpg")

    from alembic import command
    from alembic.config import Config
    from moku_backend.config import Settings
    from moku_backend.db.engine import create_engine, create_sessionmaker
    from moku_backend.main import create_app
    from moku_backend.services.corpus_import_service import CorpusImportService

    backend_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("MOKU_DATABASE_URL", database_url)
    alembic_config = Config(str(backend_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(alembic_config, "head")

    settings = Settings(
        database_url=database_url,
        default_corpus_name="sample-en",
        default_language="en",
        import_max_sentences=20,
    )

    async def import_sample() -> None:
        engine = create_engine(settings)
        sessionmaker = create_sessionmaker(engine)
        try:
            async with sessionmaker() as session:
                service = CorpusImportService(session, settings)
                await service.import_corpus(
                    source="sample",
                    language="en",
                    corpus_name="sample-en",
                    max_sentences=20,
                    seed_default_learner=True,
                )
        finally:
            await engine.dispose()

    import anyio

    anyio.run(import_sample)

    client = TestClient(create_app(settings))
    response = client.get("/v1/recommendations", params={"top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["corpus_name"] == "sample-en"
    assert len(payload["recommendations"]) > 0
