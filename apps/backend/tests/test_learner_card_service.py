from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fsrs import Card as FsrsCard
from moku_backend.config import Settings
from moku_backend.persistence.models import Learner, LearnerCard
from moku_backend.services.learner_card_service import (
    FSRS_ALGORITHM,
    LearnerCardConflictError,
    LearnerCardService,
    LearnerCardValidationError,
    parse_rating,
)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0
        self.next_id = 101

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1
        for value in self.added:
            if isinstance(value, LearnerCard) and value.id is None:
                value.id = self.next_id
                self.next_id += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeLearners:
    def __init__(self, learner: Learner, card: LearnerCard | None = None) -> None:
        self.learner = learner
        self.card = card
        self.listed_cards: list[LearnerCard] = []
        self.seen_list_kwargs: dict[str, object] | None = None

    async def get_or_create_default(self, handle: str) -> Learner:
        return self.learner

    async def get_by_public_id(self, public_id):
        if public_id == self.learner.public_id:
            return self.learner
        return None

    async def get_card_by_word_language(self, **_kwargs):
        return self.card

    async def get_card_by_public_id(self, public_id, *, load_learner: bool = False):
        if self.card is not None and public_id == self.card.public_id:
            return self.card
        return None

    async def list_cards(self, **kwargs):
        self.seen_list_kwargs = kwargs
        return self.listed_cards


def make_service(fake_session: FakeSession, fake_learners: FakeLearners) -> LearnerCardService:
    service = LearnerCardService(
        fake_session,
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
    )
    service.learners = fake_learners
    return service


async def test_create_fsrs_card_initializes_fsrs_state() -> None:
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    session = FakeSession()
    service = make_service(session, FakeLearners(learner))

    card = await service.create_fsrs_card(word=" Casa ", language="EN")

    assert card.word == "casa"
    assert card.language == "en"
    assert card.scheduling_algorithm == FSRS_ALGORITHM
    assert card.schedule_status == "scheduled"
    assert card.interval_days == 1
    assert card.fsrs_card is not None
    assert card.fsrs_card["card_id"] == card.id
    assert session.flush_count == 1
    assert session.commit_count == 1


async def test_create_fsrs_card_rejects_duplicate_word_language() -> None:
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    existing = LearnerCard(
        learner=learner,
        word="casa",
        language="en",
        schedule_status="scheduled",
        scheduling_algorithm="fsrs",
        source_metadata={},
    )
    service = make_service(FakeSession(), FakeLearners(learner, existing))

    with pytest.raises(LearnerCardConflictError):
        await service.create_fsrs_card(word="casa", language="en")


async def test_review_card_persists_fsrs_update_and_review_log() -> None:
    reviewed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    card = LearnerCard(
        id=55,
        public_id=uuid4(),
        learner=learner,
        word="casa",
        language="en",
        due_at=reviewed_at,
        interval_days=1,
        schedule_status="scheduled",
        scheduling_algorithm="fsrs",
        fsrs_card=FsrsCard(card_id=55, due=reviewed_at).to_dict(),
        source_metadata={},
    )
    session = FakeSession()
    service = make_service(session, FakeLearners(learner, card))

    result = await service.review_card(
        card_public_id=card.public_id,
        rating="good",
        reviewed_at=reviewed_at,
        duration_ms=1200,
    )

    assert result.card is card
    assert card.fsrs_card is not None
    assert card.fsrs_card["last_review"] == reviewed_at.isoformat()
    assert card.due_at is not None and card.due_at > reviewed_at
    assert card.interval_days == 1
    assert result.review_log.rating == "good"
    assert result.review_log.source_metadata["source"] == "fsrs"
    assert result.review_log.source_metadata["fsrs_review_log"]["rating"] == 3
    assert session.commit_count == 1


async def test_review_card_rejects_non_fsrs_cards() -> None:
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    card = LearnerCard(
        id=55,
        public_id=uuid4(),
        learner=learner,
        word="casa",
        language="en",
        due_at=None,
        interval_days=None,
        schedule_status="scheduled",
        scheduling_algorithm="anki",
        fsrs_card=None,
        source_metadata={},
    )
    service = make_service(FakeSession(), FakeLearners(learner, card))

    with pytest.raises(LearnerCardConflictError):
        await service.review_card(card_public_id=card.public_id, rating="good")


async def test_review_card_requires_utc_review_datetime() -> None:
    learner = Learner(id=12, public_id=uuid4(), handle="default")
    card = LearnerCard(
        id=55,
        public_id=uuid4(),
        learner=learner,
        word="casa",
        language="en",
        due_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        interval_days=1,
        schedule_status="scheduled",
        scheduling_algorithm="fsrs",
        fsrs_card=FsrsCard(card_id=55).to_dict(),
        source_metadata={},
    )
    service = make_service(FakeSession(), FakeLearners(learner, card))

    with pytest.raises(LearnerCardValidationError):
        await service.review_card(
            card_public_id=card.public_id,
            rating="good",
            reviewed_at=datetime(2026, 1, 1, 12, 0),
        )


def test_parse_rating_rejects_unknown_values() -> None:
    with pytest.raises(LearnerCardValidationError):
        parse_rating("perfect")
