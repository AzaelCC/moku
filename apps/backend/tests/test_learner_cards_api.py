from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from moku_backend.api.deps import get_session
from moku_backend.api.v1 import learner_cards as learner_cards_api
from moku_backend.config import Settings
from moku_backend.persistence.models import Learner, LearnerCard, LearnerNote, ReviewLog
from moku_backend.services.learner_card_service import (
    LearnerCardConflictError,
    LearnerCardNotFoundError,
)


async def fake_get_session() -> AsyncIterator[object]:
    yield object()


def make_app(monkeypatch, fake_service_type: type) -> FastAPI:
    monkeypatch.setattr(learner_cards_api, "LearnerCardService", fake_service_type)

    app = FastAPI()
    app.state.settings = Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused")
    app.include_router(learner_cards_api.router, prefix="/v1")
    app.dependency_overrides[get_session] = fake_get_session
    return app


def make_card() -> LearnerCard:
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    note = LearnerNote(
        learner=learner,
        public_id=uuid4(),
        word="casa",
        language="en",
        note_key="manual:casa",
        source_metadata={},
    )
    reviewed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return LearnerCard(
        id=55,
        public_id=uuid4(),
        note=note,
        card_type="reading",
        due_at=reviewed_at,
        interval_days=1,
        schedule_status="scheduled",
        scheduling_algorithm="fsrs",
        fsrs_card={
            "card_id": 55,
            "state": 1,
            "step": 0,
            "stability": None,
            "difficulty": None,
            "due": reviewed_at.isoformat(),
            "last_review": None,
        },
        source_metadata={},
    )


def test_create_learner_card_api_returns_fsrs_card(monkeypatch) -> None:
    seen: dict[str, object] = {}
    card = make_card()

    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def create_fsrs_card(self, **kwargs: object) -> LearnerCard:
            seen.update(kwargs)
            return card

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).post(
        "/v1/learner-cards",
        json={"word": "Casa", "card_type": "reading", "language": "en"},
    )

    assert response.status_code == 201
    assert seen["word"] == "Casa"
    assert seen["card_type"] == "reading"
    payload = response.json()
    assert payload["public_id"] == str(card.public_id)
    assert payload["note_id"] == str(card.note.public_id)
    assert payload["card_type"] == "reading"
    assert payload["scheduling_algorithm"] == "fsrs"
    assert payload["fsrs_state"]["state"] == "learning"


def test_create_learner_card_api_requires_card_type(monkeypatch) -> None:
    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).post(
        "/v1/learner-cards",
        json={"word": "Casa", "language": "en"},
    )

    assert response.status_code == 422


def test_list_learner_cards_api_passes_filters(monkeypatch) -> None:
    seen: dict[str, object] = {}
    card = make_card()

    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def list_cards(self, **kwargs: object) -> list[LearnerCard]:
            seen.update(kwargs)
            return [card]

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).get(
        "/v1/learner-cards",
        params={"language": "en", "scheduling_algorithm": "fsrs", "limit": 10},
    )

    assert response.status_code == 200
    assert seen["language"] == "en"
    assert seen["scheduling_algorithm"] == "fsrs"
    assert seen["limit"] == 10
    assert response.json()[0]["public_id"] == str(card.public_id)


def test_review_learner_card_api_returns_review_log_id(monkeypatch) -> None:
    card = make_card()
    review_log = ReviewLog(
        public_id=uuid4(),
        learner_card=card,
        rating="good",
        reviewed_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        source_metadata={},
    )

    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def review_card(self, **_kwargs: object):
            return SimpleNamespace(card=card, review_log=review_log)

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).post(
        f"/v1/learner-cards/{card.public_id}/reviews",
        json={"rating": "good", "reviewed_at": "2026-01-01T12:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["review_log_id"] == str(review_log.public_id)


def test_review_learner_card_api_rejects_invalid_rating(monkeypatch) -> None:
    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).post(
        f"/v1/learner-cards/{uuid4()}/reviews",
        json={"rating": "perfect"},
    )

    assert response.status_code == 422


def test_review_learner_card_api_maps_conflicts(monkeypatch) -> None:
    card_id = uuid4()

    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def review_card(self, **_kwargs: object):
            raise LearnerCardConflictError("not fsrs")

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).post(
        f"/v1/learner-cards/{card_id}/reviews",
        json={"rating": "good"},
    )

    assert response.status_code == 409


def test_list_learner_cards_api_maps_missing_learner(monkeypatch) -> None:
    class FakeLearnerCardService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def list_cards(self, **_kwargs: object):
            raise LearnerCardNotFoundError("missing")

    app = make_app(monkeypatch, FakeLearnerCardService)

    response = TestClient(app).get("/v1/learner-cards", params={"learner_id": str(uuid4())})

    assert response.status_code == 404
