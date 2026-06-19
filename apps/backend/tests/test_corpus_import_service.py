from __future__ import annotations

from types import SimpleNamespace

from moku_backend.config import Settings
from moku_backend.services import corpus_import_service
from moku_backend.services.corpus_import_service import CorpusImportService


class FakeSession:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeImportRuns:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.succeeded: tuple[int, int] | None = None

    async def create_run(self, **kwargs: object):
        self.created = kwargs
        return SimpleNamespace(id=1, public_id="run-public-id")

    async def mark_succeeded(self, run_id: int, sentence_count: int) -> None:
        self.succeeded = (run_id, sentence_count)

    async def mark_failed(self, run_id: int, error_message: str) -> None:
        raise AssertionError(f"unexpected failed import {run_id}: {error_message}")


class FakeSentences:
    async def get_or_create_corpus(self, *, name: str, source: str, language: str):
        return SimpleNamespace(public_id="corpus-public-id", name=name)

    async def replace_sentences(self, *, corpus: object, sentences: object) -> list[object]:
        return list(sentences)


async def test_corpus_import_service_defaults_to_unbounded_limits(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_iter_corpus_sentences(config):
        seen["config"] = config
        return iter(())

    monkeypatch.delenv("MOKU_IMPORT_MAX_DOCUMENTS", raising=False)
    monkeypatch.delenv("MOKU_IMPORT_MAX_SENTENCES", raising=False)
    monkeypatch.setattr(corpus_import_service, "iter_corpus_sentences", fake_iter_corpus_sentences)

    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused")
    service = CorpusImportService(FakeSession(), settings)
    import_runs = FakeImportRuns()
    service.import_runs = import_runs
    service.sentences = FakeSentences()

    result = await service.import_corpus(
        source="sample",
        language="en",
        seed_default_learner=False,
    )

    assert settings.import_max_documents is None
    assert settings.import_max_sentences is None
    assert import_runs.created is not None
    assert import_runs.created["max_documents"] is None
    assert import_runs.created["max_sentences"] is None
    assert seen["config"].max_documents is None
    assert seen["config"].max_sentences is None
    assert import_runs.succeeded == (1, 0)
    assert result.sentence_count == 0
