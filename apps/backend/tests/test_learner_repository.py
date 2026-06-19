from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from moku_backend.persistence.models import Learner, LearnerCard
from moku_backend.persistence.repositories.learner_repository import (
    LearnerCardSpec,
    LearnerRepository,
)


class FakeScalarResult:
    def __init__(self, values: list[LearnerCard]) -> None:
        self.values = values

    def all(self) -> list[LearnerCard]:
        return self.values


class FakeResult:
    def __init__(self, values: list[LearnerCard]) -> None:
        self.values = values

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.values)


class FakeSession:
    def __init__(self, cards: list[LearnerCard] | None = None) -> None:
        self.cards = cards or []
        self.executed: list[Any] = []
        self.added: list[LearnerCard] = []
        self.flush_count = 0

    async def execute(self, statement: Any) -> FakeResult:
        self.executed.append(statement)
        return FakeResult(self.cards)

    def add_all(self, cards: list[LearnerCard]) -> None:
        self.added.extend(cards)

    async def flush(self) -> None:
        self.flush_count += 1


def test_learner_card_schedule_columns_support_unscheduled_imports() -> None:
    assert LearnerCard.__table__.c.schedule_status.nullable is False
    assert LearnerCard.__table__.c.due_at.nullable is True
    assert LearnerCard.__table__.c.interval_days.nullable is True


async def test_replace_cards_for_language_deletes_only_target_language() -> None:
    learner = Learner(id=12, handle="test")
    session = FakeSession()
    repository = LearnerRepository(session)

    await repository.replace_cards_for_language(
        learner=learner,
        language="ja",
        card_specs=[
            LearnerCardSpec(
                word="go",
                schedule_status="scheduled",
                days_until_due=0,
                interval_days=4,
                metadata={"source": "anki"},
            )
        ],
    )

    delete_statement = str(session.executed[0])
    assert "learner_cards.learner_id" in delete_statement
    assert "learner_cards.language" in delete_statement
    assert [card.word for card in session.added] == ["go"]
    assert session.added[0].schedule_status == "scheduled"
    assert session.added[0].interval_days == 4
    assert session.flush_count == 1


async def test_replace_cards_for_language_normalizes_language_tags() -> None:
    learner = Learner(id=12, handle="test")
    session = FakeSession()
    repository = LearnerRepository(session)

    await repository.replace_cards_for_language(
        learner=learner,
        language="zh-CN",
        card_specs=[
            LearnerCardSpec(
                word="你好",
                schedule_status="scheduled",
                days_until_due=0,
                interval_days=4,
            )
        ],
    )

    delete_statement = str(session.executed[0])
    assert "replace(lower(learner_cards.language)" in delete_statement
    assert session.added[0].language == "zh_cn"


async def test_list_schedule_excludes_unscheduled_and_suspended_cards() -> None:
    now = datetime.now(UTC)
    learner = Learner(id=12, handle="test")
    cards = [
        LearnerCard(
            learner_id=12,
            word="due",
            language="en",
            due_at=now,
            interval_days=7,
            schedule_status="scheduled",
            source_metadata={},
        ),
        LearnerCard(
            learner_id=12,
            word="new",
            language="en",
            due_at=None,
            interval_days=None,
            schedule_status="unscheduled",
            source_metadata={},
        ),
        LearnerCard(
            learner_id=12,
            word="paused",
            language="en",
            due_at=None,
            interval_days=None,
            schedule_status="suspended",
            source_metadata={},
        ),
    ]
    session = FakeSession(cards)
    repository = LearnerRepository(session)

    schedule = await repository.list_schedule(learner=learner, language="en", now=now)

    query = str(session.executed[0])
    assert "learner_cards.schedule_status" in query
    assert "learner_cards.due_at IS NOT NULL" in query
    assert "learner_cards.interval_days IS NOT NULL" in query
    assert [(item.word, item.days_until_due, item.interval_days) for item in schedule] == [
        ("due", 0, 7),
    ]


async def test_list_schedule_matches_equivalent_language_tags() -> None:
    now = datetime.now(UTC)
    learner = Learner(id=12, handle="test")
    cards = [
        LearnerCard(
            learner_id=12,
            word="你好",
            language="zh-CN",
            due_at=now,
            interval_days=7,
            schedule_status="scheduled",
            source_metadata={},
        ),
    ]
    session = FakeSession(cards)
    repository = LearnerRepository(session)

    schedule = await repository.list_schedule(learner=learner, language="zh_CN", now=now)

    query = str(session.executed[0])
    assert "replace(lower(learner_cards.language)" in query
    assert [(item.word, item.days_until_due, item.interval_days) for item in schedule] == [
        ("你好", 0, 7),
    ]
