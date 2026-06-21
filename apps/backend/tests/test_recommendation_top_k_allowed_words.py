from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from moku_backend.api.deps import get_session
from moku_backend.api.v1 import recommendations as recommendations_api
from moku_backend.config import Settings
from moku_backend.services import recommendation_service
from moku_backend.services.recommendation_service import RecommendationService


async def fake_get_session() -> AsyncIterator[object]:
    yield object()


def make_recommendations_app(monkeypatch, seen: list[dict[str, object]]) -> FastAPI:
    class FakeRecommendationService:
        def __init__(self, session: object, settings: Settings) -> None:
            self.session = session
            self.settings = settings

        async def recommend(self, **kwargs: object):
            seen.append(kwargs)
            return SimpleNamespace(
                corpus=SimpleNamespace(public_id=uuid4(), name="sample-en"),
                learner=SimpleNamespace(public_id=uuid4()),
                recommendations=[],
            )

    monkeypatch.setattr(
        recommendations_api,
        "RecommendationService",
        FakeRecommendationService,
    )

    app = FastAPI()
    app.state.settings = Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused")
    app.include_router(recommendations_api.router, prefix="/v1")
    app.dependency_overrides[get_session] = fake_get_session
    return app


def test_recommendations_api_defaults_top_k_allowed_words_to_5000(monkeypatch) -> None:
    seen: list[dict[str, object]] = []
    app = make_recommendations_app(monkeypatch, seen)

    response = TestClient(app).get("/v1/recommendations")

    assert response.status_code == 200
    assert seen[0]["top_k_allowed_words"] == 5_000


def test_recommendations_api_preserves_explicit_top_k_allowed_words_zero(monkeypatch) -> None:
    seen: list[dict[str, object]] = []
    app = make_recommendations_app(monkeypatch, seen)

    response = TestClient(app).get("/v1/recommendations", params={"top_k_allowed_words": 0})

    assert response.status_code == 200
    assert seen[0]["top_k_allowed_words"] == 0


async def test_recommendation_service_does_not_read_top_k_allowed_words_from_settings(
    monkeypatch,
) -> None:
    document_filters_seen: list[int] = []
    retrieval_filters_seen: list[int] = []
    corpus = SimpleNamespace(language="en")
    learner = SimpleNamespace()

    class SettingsWithoutTopK:
        default_learner_handle = "default"

        def __getattribute__(self, name: str):
            if name == "top_k_allowed_words":
                raise AssertionError("top_k_allowed_words should be passed per recommendation call")
            return super().__getattribute__(name)

    class FakeSentences:
        async def get_corpus_by_name(self, corpus_name: str):
            return corpus

        async def list_documents(
            self,
            resolved_corpus: object,
            *,
            top_k_allowed_words: int = 0,
        ) -> list[object]:
            document_filters_seen.append(top_k_allowed_words)
            return []

    class FakeLearners:
        async def get_or_create_default(self, handle: str):
            return learner

        async def list_schedule(self, learner: object, language: str) -> list[object]:
            return []

    def fake_retrieve_recommendations(**kwargs: object) -> list[object]:
        retrieval_filters_seen.append(kwargs["top_k_allowed_words"])
        return []

    monkeypatch.setattr(
        recommendation_service,
        "retrieve_recommendations",
        fake_retrieve_recommendations,
    )

    service = RecommendationService(session=object(), settings=SettingsWithoutTopK())
    service.sentences = FakeSentences()
    service.learners = FakeLearners()

    await service.recommend(corpus_name="sample-en")
    await service.recommend(corpus_name="sample-en", top_k_allowed_words=0)

    assert document_filters_seen == [5_000, 0]
    assert retrieval_filters_seen == [0, 0]
