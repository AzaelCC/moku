"""Import learner schedules from Anki package exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.repositories.learner_repository import (
    LearnerCardSpec,
    LearnerRepository,
    LearnerReviewLogSpec,
)
from moku_backend.services.anki_import_service import (
    CARD_WORD_MAX_LENGTH,
    SCHEDULED,
    SUSPENDED,
    UNSCHEDULED,
    SkippedAnkiCard,
    clean_anki_field,
)
from moku_backend.services.anki_package_reader import (
    AnkiPackage,
    AnkiPackageCard,
    AnkiPackageError,
    AnkiPackageReader,
    AnkiPackageReviewLog,
)

ANKI_PACKAGE_SOURCE = "anki_package"
ANKI_ALGORITHM = "anki"


class AnkiPackageImportError(RuntimeError):
    """Raised when an Anki package import cannot be completed."""


@dataclass
class ImportedAnkiPackageCard:
    word: str
    schedule_status: str
    due_at: datetime | None
    interval_days: int | None
    fsrs_card: dict[str, object] | None
    review_logs: list[LearnerReviewLogSpec]
    metadata: dict[str, object]


@dataclass
class AggregatedAnkiPackageCard:
    word: str
    schedule_status: str
    due_at: datetime | None
    interval_days: int | None
    fsrs_card: dict[str, object] | None
    review_logs: list[LearnerReviewLogSpec] = field(default_factory=list)
    cards: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class AnkiPackageImportResult:
    learner_public_id: str
    learner_handle: str
    package_path: str
    deck: str
    language: str
    found_card_count: int
    imported_card_count: int
    imported_review_log_count: int
    fsrs_card_count: int
    scheduled_count: int
    unscheduled_count: int
    suspended_count: int
    skipped_missing_field_count: int
    skipped_empty_field_count: int
    skipped_too_long_count: int
    duplicate_card_count: int
    skipped_samples: tuple[SkippedAnkiCard, ...] = ()

    @property
    def skipped_count(self) -> int:
        return (
            self.skipped_missing_field_count
            + self.skipped_empty_field_count
            + self.skipped_too_long_count
        )


class AnkiPackageImportService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        reader: AnkiPackageReader | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        print(settings.database_url)
        self.reader = reader or AnkiPackageReader()
        self.learners = LearnerRepository(session)

    async def import_package(
        self,
        *,
        package_path: str | Path,
        deck: str,
        word_field: str,
        language: str | None = None,
        learner_handle: str | None = None,
    ) -> AnkiPackageImportResult:
        package_path = self._require_package_path(package_path)
        deck = self._require_non_empty(deck, "deck")
        word_field = self._require_non_empty(word_field, "word_field")
        language = language or self.settings.default_language
        learner_handle = learner_handle or self.settings.default_learner_handle

        try:
            package = self.reader.read(package_path)
        except AnkiPackageError as exc:
            raise AnkiPackageImportError(str(exc)) from exc

        cards = self._cards_for_deck(package, deck)
        if cards and not self._has_scheduling_data(package, cards):
            raise AnkiPackageImportError(
                "Anki package export does not include scheduling data. "
                "Export with scheduling enabled."
            )

        card_specs, skipped, duplicate_count = self._build_card_specs(
            package=package,
            cards=cards,
            deck=deck,
            word_field=word_field,
        )

        learner = await self.learners.get_or_create_default(learner_handle)
        try:
            await self.learners.replace_cards_for_language(
                learner=learner,
                language=language,
                card_specs=card_specs,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return AnkiPackageImportResult(
            learner_public_id=str(learner.public_id),
            learner_handle=learner.handle,
            package_path=str(package_path),
            deck=deck,
            language=language,
            found_card_count=len(cards),
            imported_card_count=len(card_specs),
            imported_review_log_count=sum(len(card.review_logs) for card in card_specs),
            fsrs_card_count=sum(1 for card in card_specs if card.fsrs_card is not None),
            scheduled_count=sum(1 for card in card_specs if card.schedule_status == SCHEDULED),
            unscheduled_count=sum(1 for card in card_specs if card.schedule_status == UNSCHEDULED),
            suspended_count=sum(1 for card in card_specs if card.schedule_status == SUSPENDED),
            skipped_missing_field_count=sum(
                1 for card in skipped if card.reason == "missing_field"
            ),
            skipped_empty_field_count=sum(1 for card in skipped if card.reason == "empty_field"),
            skipped_too_long_count=sum(1 for card in skipped if card.reason == "too_long"),
            duplicate_card_count=duplicate_count,
            skipped_samples=tuple(skipped[:5]),
        )

    def _cards_for_deck(self, package: AnkiPackage, deck: str) -> list[AnkiPackageCard]:
        deck_names = {deck_info.name for deck_info in package.decks}
        if deck not in deck_names:
            raise AnkiPackageImportError(f"Anki package deck not found: {deck}")

        return [
            card
            for card in package.cards
            if card.deck_name == deck or card.deck_name.startswith(f"{deck}::")
        ]

    def _has_scheduling_data(
        self,
        package: AnkiPackage,
        cards: list[AnkiPackageCard],
    ) -> bool:
        card_ids = {card.id for card in cards}
        has_review_logs = any(review_log.card_id in card_ids for review_log in package.review_logs)
        has_fsrs_state = any(card.fsrs_stability is not None for card in cards)
        return has_review_logs or has_fsrs_state

    def _build_card_specs(
        self,
        *,
        package: AnkiPackage,
        cards: list[AnkiPackageCard],
        deck: str,
        word_field: str,
    ) -> tuple[list[LearnerCardSpec], list[SkippedAnkiCard], int]:
        imported: list[ImportedAnkiPackageCard] = []
        skipped: list[SkippedAnkiCard] = []
        collection_date = package.created_at.date()

        for card in cards:
            note = package.notes_by_id.get(card.note_id)
            if note is None or word_field not in note.fields:
                skipped.append(SkippedAnkiCard(card.id, "missing_field"))
                continue

            original_value = clean_anki_field(note.fields[word_field])
            word = original_value.casefold()
            if not word:
                skipped.append(SkippedAnkiCard(card.id, "empty_field"))
                continue
            if len(word) > CARD_WORD_MAX_LENGTH:
                skipped.append(SkippedAnkiCard(card.id, "too_long"))
                continue

            status, due_at, interval_days = _schedule_for_card(
                card,
                collection_date=collection_date,
            )
            fsrs_card = _fsrs_card_for(card, due_at=due_at)
            review_logs = [
                _review_log_spec(review_log)
                for review_log in package.review_logs_by_card_id.get(card.id, ())
            ]
            imported.append(
                ImportedAnkiPackageCard(
                    word=word,
                    schedule_status=status,
                    due_at=due_at,
                    interval_days=interval_days,
                    fsrs_card=fsrs_card,
                    review_logs=review_logs,
                    metadata={
                        "card_id": card.id,
                        "note_id": card.note_id,
                        "deck": deck,
                        "deck_name": card.deck_name,
                        "notetype_name": note.notetype_name,
                        "word_field": word_field,
                        "original_field_value": original_value,
                        "queue": card.queue,
                        "type": card.card_type,
                        "reps": card.reps,
                        "lapses": card.lapses,
                        "raw_due": card.due,
                        "raw_interval": card.interval,
                        "factor": card.factor,
                        "mod": card.mod,
                        "flags": card.flags,
                        "card_data": card.card_data,
                        "fsrs_card": fsrs_card,
                    },
                )
            )

        aggregated = _aggregate_cards(imported)
        card_specs = [
            LearnerCardSpec(
                word=card.word,
                schedule_status=card.schedule_status,
                due_at=card.due_at,
                interval_days=card.interval_days,
                scheduling_algorithm=ANKI_ALGORITHM,
                fsrs_card=card.fsrs_card,
                review_logs=tuple(card.review_logs),
                metadata={
                    "source": ANKI_PACKAGE_SOURCE,
                    "package_path": str(package.path),
                    "collection_entry": package.collection_entry,
                    "deck": deck,
                    "word_field": word_field,
                    "card_ids": [detail["card_id"] for detail in card.cards],
                    "note_ids": sorted({detail["note_id"] for detail in card.cards}),
                    "cards": card.cards,
                },
            )
            for card in aggregated
        ]
        return card_specs, skipped, len(imported) - len(card_specs)

    def _require_non_empty(self, value: str, name: str) -> str:
        value = value.strip()
        if not value:
            raise AnkiPackageImportError(f"Anki package {name} must not be empty.")
        return value

    def _require_package_path(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.exists():
            raise AnkiPackageImportError(f"Anki package not found: {path}")
        return path


def _schedule_for_card(
    card: AnkiPackageCard,
    *,
    collection_date: date,
) -> tuple[str, datetime | None, int | None]:
    if card.queue == -1:
        return SUSPENDED, None, None
    if card.card_type == 0 or card.reps <= 0:
        return UNSCHEDULED, None, None

    interval_days = max(card.interval, 1)
    return SCHEDULED, _due_at(card, collection_date=collection_date), interval_days


def _due_at(card: AnkiPackageCard, *, collection_date: date) -> datetime:
    if card.queue in {1, 4} and card.due > 1_000_000_000:
        return datetime.fromtimestamp(card.due, UTC)
    if card.card_type in {1, 3} and card.due > 1_000_000_000:
        return datetime.fromtimestamp(card.due, UTC)

    due_date = collection_date + timedelta(days=card.due)
    return datetime.combine(due_date, time.min, tzinfo=UTC)


def _fsrs_card_for(
    card: AnkiPackageCard,
    *,
    due_at: datetime | None,
) -> dict[str, object] | None:
    stability = card.fsrs_stability
    difficulty = card.fsrs_difficulty
    if stability is None or difficulty is None:
        return None

    last_review = _timestamp_from_card_data(card.card_data.get("lrt"))
    return {
        "card_id": card.id,
        "state": {1: 1, 2: 2, 3: 3}.get(card.card_type, 2),
        "step": None,
        "stability": stability,
        "difficulty": difficulty,
        "due": due_at.isoformat() if due_at is not None else None,
        "last_review": last_review.isoformat() if last_review is not None else None,
    }


def _timestamp_from_card_data(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, UTC)


def _review_log_spec(review_log: AnkiPackageReviewLog) -> LearnerReviewLogSpec:
    return LearnerReviewLogSpec(
        rating=_rating_for_ease(review_log.ease),
        reviewed_at=datetime.fromtimestamp(review_log.id / 1000, UTC),
        duration_ms=review_log.duration_ms,
        metadata={
            "source": ANKI_PACKAGE_SOURCE,
            "anki_revlog_id": review_log.id,
            "anki_card_id": review_log.card_id,
            "usn": review_log.usn,
            "ease": review_log.ease,
            "interval": review_log.interval,
            "last_interval": review_log.last_interval,
            "factor": review_log.factor,
            "type": review_log.review_type,
        },
    )


def _rating_for_ease(ease: int) -> str:
    return {1: "again", 2: "hard", 3: "good", 4: "easy"}.get(ease, "unknown")


def _aggregate_cards(cards: list[ImportedAnkiPackageCard]) -> list[AggregatedAnkiPackageCard]:
    aggregated: dict[str, AggregatedAnkiPackageCard] = {}
    for card in cards:
        detail = dict(card.metadata)
        current = aggregated.get(card.word)
        if current is None:
            aggregated[card.word] = AggregatedAnkiPackageCard(
                word=card.word,
                schedule_status=card.schedule_status,
                due_at=card.due_at,
                interval_days=card.interval_days,
                fsrs_card=card.fsrs_card,
                review_logs=list(card.review_logs),
                cards=[detail],
            )
            continue

        current.cards.append(detail)
        current.review_logs.extend(card.review_logs)
        if _schedule_priority(card) < _schedule_priority(current):
            current.schedule_status = card.schedule_status
            current.due_at = card.due_at
            current.interval_days = card.interval_days
            current.fsrs_card = card.fsrs_card
        elif current.fsrs_card is None and card.fsrs_card is not None:
            current.fsrs_card = card.fsrs_card

    return list(aggregated.values())


def _schedule_priority(
    card: ImportedAnkiPackageCard | AggregatedAnkiPackageCard,
) -> tuple[int, datetime, int]:
    if card.schedule_status == SCHEDULED:
        return (
            0,
            card.due_at or datetime.fromtimestamp(0, UTC),
            card.interval_days or 1,
        )
    if card.schedule_status == UNSCHEDULED:
        return (1, datetime.fromtimestamp(0, UTC), 0)
    return (2, datetime.fromtimestamp(0, UTC), 0)
