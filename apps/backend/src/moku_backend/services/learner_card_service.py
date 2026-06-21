"""Learner card creation, listing, and review scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fsrs import Card as FsrsCard
from fsrs import Rating as FsrsRating
from fsrs import ReviewLog as FsrsReviewLog
from fsrs import Scheduler
from moku_core.text.languages import normalize_language
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.models import Learner, LearnerCard, ReviewLog
from moku_backend.persistence.repositories.learner_repository import LearnerRepository

FSRS_ALGORITHM = "fsrs"
LEGACY_ALGORITHM = "legacy"
SCHEDULED = "scheduled"
CARD_WORD_MAX_LENGTH = 255

RATINGS: dict[str, FsrsRating] = {
    "again": FsrsRating.Again,
    "hard": FsrsRating.Hard,
    "good": FsrsRating.Good,
    "easy": FsrsRating.Easy,
}


class LearnerCardServiceError(RuntimeError):
    """Base learner card service error."""


class LearnerCardNotFoundError(LearnerCardServiceError):
    """Raised when a learner or card cannot be found."""


class LearnerCardConflictError(LearnerCardServiceError):
    """Raised when a requested learner card mutation conflicts with current state."""


class LearnerCardValidationError(LearnerCardServiceError):
    """Raised when a learner card request is invalid."""


@dataclass(frozen=True)
class LearnerCardReviewResult:
    card: LearnerCard
    review_log: ReviewLog
    fsrs_review_log: FsrsReviewLog


class LearnerCardService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.learners = LearnerRepository(session)
        self.scheduler = Scheduler()

    async def create_fsrs_card(
        self,
        *,
        word: str,
        language: str | None = None,
        learner_public_id: UUID | None = None,
    ) -> LearnerCard:
        learner = await self._resolve_learner(learner_public_id)
        normalized_word = _normalize_word(word)
        normalized_language = normalize_language(language or self.settings.default_language)
        existing = await self.learners.get_card_by_word_language(
            learner=learner,
            word=normalized_word,
            language=normalized_language,
        )
        if existing is not None:
            raise LearnerCardConflictError(
                f"Learner already has a card for {normalized_word!r} in {normalized_language}."
            )

        now = datetime.now(UTC)
        card = LearnerCard(
            learner=learner,
            word=normalized_word,
            language=normalized_language,
            due_at=now,
            interval_days=1,
            schedule_status=SCHEDULED,
            scheduling_algorithm=FSRS_ALGORITHM,
            fsrs_card=None,
            source_metadata={"source": "moku-fsrs"},
        )
        self.session.add(card)

        try:
            await self.session.flush()
            fsrs_card = FsrsCard(card_id=card.id, due=now)
            card.fsrs_card = fsrs_card.to_dict()
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise LearnerCardConflictError(
                f"Learner already has a card for {normalized_word!r} in {normalized_language}."
            ) from exc
        except Exception:
            await self.session.rollback()
            raise

        return card

    async def list_cards(
        self,
        *,
        learner_public_id: UUID | None = None,
        language: str | None = None,
        schedule_status: str | None = None,
        scheduling_algorithm: str | None = None,
        due_before: datetime | None = None,
        limit: int = 100,
    ) -> list[LearnerCard]:
        learner = await self._resolve_learner(learner_public_id)
        if due_before is not None:
            due_before = _require_utc(due_before)
        return await self.learners.list_cards(
            learner=learner,
            language=language,
            schedule_status=_normalize_optional_filter(schedule_status),
            scheduling_algorithm=_normalize_optional_filter(scheduling_algorithm),
            due_before=due_before,
            limit=limit,
        )

    async def review_card(
        self,
        *,
        card_public_id: UUID,
        rating: str,
        reviewed_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> LearnerCardReviewResult:
        card = await self.learners.get_card_by_public_id(card_public_id, load_learner=True)
        if card is None:
            raise LearnerCardNotFoundError(f"Learner card not found: {card_public_id}")
        if card.scheduling_algorithm != FSRS_ALGORITHM or card.fsrs_card is None:
            raise LearnerCardConflictError(
                "Learner card is not FSRS-managed and cannot be reviewed with FSRS."
            )

        reviewed_at = _require_utc(reviewed_at or datetime.now(UTC))
        rating_enum = parse_rating(rating)
        fsrs_card = FsrsCard.from_dict(card.fsrs_card)
        updated_card, fsrs_review_log = self.scheduler.review_card(
            fsrs_card,
            rating_enum,
            review_datetime=reviewed_at,
            review_duration=duration_ms,
        )

        card.fsrs_card = updated_card.to_dict()
        card.due_at = updated_card.due
        card.interval_days = _interval_days(updated_card.due, reviewed_at)
        card.schedule_status = SCHEDULED

        review_log = ReviewLog(
            learner_card=card,
            rating=_rating_name(rating_enum),
            reviewed_at=reviewed_at,
            duration_ms=duration_ms,
            source_metadata={
                "source": "fsrs",
                "fsrs_review_log": fsrs_review_log.to_dict(),
            },
        )
        self.session.add(review_log)

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return LearnerCardReviewResult(
            card=card,
            review_log=review_log,
            fsrs_review_log=fsrs_review_log,
        )

    async def _resolve_learner(self, learner_public_id: UUID | None) -> Learner:
        if learner_public_id is None:
            return await self.learners.get_or_create_default(self.settings.default_learner_handle)

        learner = await self.learners.get_by_public_id(learner_public_id)
        if learner is None:
            raise LearnerCardNotFoundError(f"Learner not found: {learner_public_id}")
        return learner


def parse_rating(value: str) -> FsrsRating:
    normalized = value.strip().lower()
    try:
        return RATINGS[normalized]
    except KeyError as exc:
        raise LearnerCardValidationError(f"Unsupported FSRS rating: {value}") from exc


def _normalize_word(value: str) -> str:
    word = value.strip().casefold()
    if not word:
        raise LearnerCardValidationError("Learner card word must not be empty.")
    if len(word) > CARD_WORD_MAX_LENGTH:
        raise LearnerCardValidationError(
            f"Learner card word must be {CARD_WORD_MAX_LENGTH} characters or fewer."
        )
    return word


def _normalize_optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise LearnerCardValidationError("Datetime values must be timezone-aware UTC.")
    return value.astimezone(UTC)


def _interval_days(due_at: datetime, reviewed_at: datetime) -> int:
    return max((due_at.date() - reviewed_at.date()).days, 1)


def _rating_name(rating: FsrsRating) -> str:
    for name, candidate in RATINGS.items():
        if candidate == rating:
            return name
    raise LearnerCardValidationError(f"Unsupported FSRS rating: {rating}")
