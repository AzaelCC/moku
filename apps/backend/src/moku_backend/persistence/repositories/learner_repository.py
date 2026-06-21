"""Learner persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from moku_core.retrieval import ScheduleItem
from moku_core.text.languages import normalize_language
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from moku_backend.persistence.models import Learner, LearnerCard, ReviewLog


@dataclass(frozen=True)
class LearnerReviewLogSpec:
    rating: str
    reviewed_at: datetime
    duration_ms: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LearnerCardSpec:
    word: str
    schedule_status: str = "scheduled"
    due_at: datetime | None = None
    days_until_due: int | None = None
    interval_days: int | None = None
    scheduling_algorithm: str = "legacy"
    fsrs_card: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    review_logs: Sequence[LearnerReviewLogSpec] = field(default_factory=tuple)


class LearnerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_default(self, handle: str) -> Learner:
        result = await self.session.execute(select(Learner).where(Learner.handle == handle))
        learner = result.scalar_one_or_none()
        if learner is not None:
            return learner

        learner = Learner(handle=handle)
        self.session.add(learner)
        await self.session.flush()
        return learner

    async def get_by_public_id(self, public_id: UUID) -> Learner | None:
        result = await self.session.execute(select(Learner).where(Learner.public_id == public_id))
        return result.scalar_one_or_none()

    async def replace_cards(
        self,
        *,
        learner: Learner,
        language: str,
        card_specs: Sequence[tuple[str, int, int]],
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self.session.execute(delete(LearnerCard).where(LearnerCard.learner_id == learner.id))
        specs = [
            LearnerCardSpec(
                word=word,
                schedule_status="scheduled",
                days_until_due=days_until_due,
                interval_days=interval_days,
                metadata=metadata or {},
            )
            for word, days_until_due, interval_days in card_specs
        ]
        await self._add_cards(learner=learner, language=language, card_specs=specs)

    async def replace_cards_for_language(
        self,
        *,
        learner: Learner,
        language: str,
        card_specs: Sequence[LearnerCardSpec],
    ) -> None:
        normalized_language = normalize_language(language)
        await self.session.execute(
            delete(LearnerCard).where(
                LearnerCard.learner_id == learner.id,
                _normalized_language(LearnerCard.language) == normalized_language,
            )
        )
        await self._add_cards(learner=learner, language=normalized_language, card_specs=card_specs)

    async def _add_cards(
        self,
        *,
        learner: Learner,
        language: str,
        card_specs: Sequence[LearnerCardSpec],
    ) -> None:
        now = datetime.now(UTC)
        normalized_language = normalize_language(language)
        learner_cards: list[LearnerCard] = []
        for card in card_specs:
            learner_card = LearnerCard(
                learner_id=learner.id,
                word=card.word,
                language=normalized_language,
                due_at=(
                    card.due_at
                    if card.due_at is not None
                    else (
                        now + timedelta(days=card.days_until_due)
                        if card.days_until_due is not None
                        else None
                    )
                ),
                interval_days=card.interval_days,
                schedule_status=card.schedule_status,
                scheduling_algorithm=card.scheduling_algorithm,
                fsrs_card=card.fsrs_card,
                source_metadata=card.metadata,
            )
            learner_card.review_logs = [
                ReviewLog(
                    rating=review_log.rating,
                    reviewed_at=review_log.reviewed_at,
                    duration_ms=review_log.duration_ms,
                    source_metadata=review_log.metadata,
                )
                for review_log in card.review_logs
            ]
            learner_cards.append(learner_card)

        self.session.add_all(learner_cards)
        await self.session.flush()

    async def list_schedule(
        self,
        *,
        learner: Learner,
        language: str | None = None,
        now: datetime | None = None,
    ) -> list[ScheduleItem]:
        now = now or datetime.now(UTC)
        statement = select(LearnerCard).where(
            LearnerCard.learner_id == learner.id,
            LearnerCard.schedule_status == "scheduled",
            LearnerCard.due_at.is_not(None),
            LearnerCard.interval_days.is_not(None),
        )
        if language is not None:
            statement = statement.where(
                _normalized_language(LearnerCard.language) == normalize_language(language)
            )
        result = await self.session.execute(statement.order_by(LearnerCard.due_at.asc()))
        cards = result.scalars().all()
        return [
            ScheduleItem(
                word=card.word,
                days_until_due=(card.due_at.date() - now.date()).days,
                interval_days=card.interval_days,
            )
            for card in cards
            if card.due_at is not None and card.interval_days is not None
        ]

    async def get_card_by_public_id(
        self,
        public_id: UUID,
        *,
        load_learner: bool = False,
    ) -> LearnerCard | None:
        statement = select(LearnerCard).where(LearnerCard.public_id == public_id)
        if load_learner:
            statement = statement.options(selectinload(LearnerCard.learner))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_card_by_word_language(
        self,
        *,
        learner: Learner,
        word: str,
        language: str,
        load_learner: bool = False,
    ) -> LearnerCard | None:
        statement = select(LearnerCard).where(
            LearnerCard.learner_id == learner.id,
            LearnerCard.word == word,
            _normalized_language(LearnerCard.language) == normalize_language(language),
        )
        if load_learner:
            statement = statement.options(selectinload(LearnerCard.learner))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_cards(
        self,
        *,
        learner: Learner,
        language: str | None = None,
        schedule_status: str | None = None,
        scheduling_algorithm: str | None = None,
        due_before: datetime | None = None,
        limit: int = 100,
    ) -> list[LearnerCard]:
        statement = (
            select(LearnerCard)
            .options(selectinload(LearnerCard.learner))
            .where(LearnerCard.learner_id == learner.id)
        )
        if language is not None:
            statement = statement.where(
                _normalized_language(LearnerCard.language) == normalize_language(language)
            )
        if schedule_status is not None:
            statement = statement.where(LearnerCard.schedule_status == schedule_status)
        if scheduling_algorithm is not None:
            statement = statement.where(LearnerCard.scheduling_algorithm == scheduling_algorithm)
        if due_before is not None:
            statement = statement.where(LearnerCard.due_at <= due_before)

        result = await self.session.execute(
            statement.order_by(LearnerCard.due_at.asc(), LearnerCard.word.asc()).limit(limit)
        )
        return list(result.scalars().all())


def _normalized_language(language_column: ColumnElement[str]) -> ColumnElement[str]:
    return func.replace(func.lower(language_column), "-", "_")
