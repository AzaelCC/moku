"""Import learner schedules from Anki via AnkiConnect."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.repositories.learner_repository import (
    LearnerCardSpec,
    LearnerRepository,
)
from moku_backend.services.anki_connect_client import AnkiConnectClient

CARD_WORD_MAX_LENGTH = 255
SCHEDULED = "scheduled"
UNSCHEDULED = "unscheduled"
SUSPENDED = "suspended"
HTML_BREAK_RE = re.compile(r"<\s*(?:br|/p|/div)\s*/?\s*>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class AnkiImportError(RuntimeError):
    """Raised when an Anki import cannot be completed."""


class AnkiImportClient(Protocol):
    def deck_names(self) -> list[str]: ...
    def find_cards(self, query: str) -> list[int]: ...
    def cards_info(self, cards: list[int]) -> list[dict[str, Any]]: ...
    def are_suspended(self, cards: list[int]) -> dict[int, bool]: ...
    def are_due(self, cards: list[int]) -> dict[int, bool]: ...


@dataclass(frozen=True)
class SkippedAnkiCard:
    card_id: int
    reason: str


@dataclass(frozen=True)
class AnkiCard:
    card_id: int
    note_id: int
    deck_name: str
    model_name: str
    fields: dict[str, Any]
    interval: int
    due: int
    queue: int
    card_type: int
    reps: int
    lapses: int
    mod: int | None
    suspended: bool
    due_now: bool


@dataclass
class ImportedAnkiCard:
    word: str
    schedule_status: str
    days_until_due: int | None
    interval_days: int | None
    metadata: dict[str, object]


@dataclass
class AggregatedAnkiCard:
    word: str
    schedule_status: str
    days_until_due: int | None
    interval_days: int | None
    cards: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class AnkiImportResult:
    learner_public_id: str
    learner_handle: str
    deck: str
    language: str
    found_card_count: int
    imported_card_count: int
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


class AnkiImportService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        client: AnkiImportClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = client or AnkiConnectClient(
            url=settings.anki_connect_url,
            api_key=settings.anki_connect_api_key,
            timeout_seconds=settings.anki_connect_timeout_seconds,
            batch_size=settings.anki_connect_batch_size,
        )
        self.learners = LearnerRepository(session)

    async def import_deck(
        self,
        *,
        deck: str,
        word_field: str,
        language: str | None = None,
        learner_handle: str | None = None,
    ) -> AnkiImportResult:
        deck = self._require_non_empty(deck, "deck")
        word_field = self._require_non_empty(word_field, "word_field")
        language = language or self.settings.default_language
        learner_handle = learner_handle or self.settings.default_learner_handle

        cards = self._fetch_cards(deck)
        card_specs, skipped, duplicate_count = self._build_card_specs(
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

        return AnkiImportResult(
            learner_public_id=str(learner.public_id),
            learner_handle=learner.handle,
            deck=deck,
            language=language,
            found_card_count=len(cards),
            imported_card_count=len(card_specs),
            scheduled_count=sum(1 for card in card_specs if card.schedule_status == SCHEDULED),
            unscheduled_count=sum(
                1 for card in card_specs if card.schedule_status == UNSCHEDULED
            ),
            suspended_count=sum(1 for card in card_specs if card.schedule_status == SUSPENDED),
            skipped_missing_field_count=sum(
                1 for card in skipped if card.reason == "missing_field"
            ),
            skipped_empty_field_count=sum(1 for card in skipped if card.reason == "empty_field"),
            skipped_too_long_count=sum(1 for card in skipped if card.reason == "too_long"),
            duplicate_card_count=duplicate_count,
            skipped_samples=tuple(skipped[:5]),
        )

    def _fetch_cards(self, deck: str) -> list[AnkiCard]:
        if deck not in self.client.deck_names():
            raise AnkiImportError(f"Anki deck not found: {deck}")

        card_ids = self.client.find_cards(build_deck_query(deck))
        if not card_ids:
            return []

        raw_cards = self.client.cards_info(card_ids)
        suspended_by_card = self.client.are_suspended(card_ids)
        due_by_card = self.client.are_due(card_ids)
        cards_by_id = {
            _required_int(raw_card.get("cardId"), "cardId"): raw_card
            for raw_card in raw_cards
        }
        missing_cards = [card_id for card_id in card_ids if card_id not in cards_by_id]
        if missing_cards:
            raise AnkiImportError(
                "AnkiConnect cardsInfo did not return records for cards: "
                + ", ".join(str(card_id) for card_id in missing_cards[:5])
            )

        return [
            _parse_card(
                cards_by_id[card_id],
                suspended=suspended_by_card.get(card_id, False),
                due_now=due_by_card.get(card_id, False),
            )
            for card_id in card_ids
        ]

    def _build_card_specs(
        self,
        *,
        cards: list[AnkiCard],
        deck: str,
        word_field: str,
    ) -> tuple[list[LearnerCardSpec], list[SkippedAnkiCard], int]:
        imported: list[ImportedAnkiCard] = []
        skipped: list[SkippedAnkiCard] = []
        for card in cards:
            field_result = _extract_word(card, word_field)
            if isinstance(field_result, SkippedAnkiCard):
                skipped.append(field_result)
                continue

            original_value, word = field_result
            if len(word) > CARD_WORD_MAX_LENGTH:
                skipped.append(SkippedAnkiCard(card.card_id, "too_long"))
                continue

            status, days_until_due, interval_days = _schedule_for_card(card)
            imported.append(
                ImportedAnkiCard(
                    word=word,
                    schedule_status=status,
                    days_until_due=days_until_due,
                    interval_days=interval_days,
                    metadata={
                        "card_id": card.card_id,
                        "note_id": card.note_id,
                        "deck": deck,
                        "deck_name": card.deck_name,
                        "model_name": card.model_name,
                        "word_field": word_field,
                        "original_field_value": original_value,
                        "queue": card.queue,
                        "type": card.card_type,
                        "reps": card.reps,
                        "lapses": card.lapses,
                        "raw_due": card.due,
                        "raw_interval": card.interval,
                        "mod": card.mod,
                        "suspended": card.suspended,
                        "due_now": card.due_now,
                    },
                )
            )

        aggregated = _aggregate_cards(imported)
        card_specs = [
            LearnerCardSpec(
                word=card.word,
                schedule_status=card.schedule_status,
                days_until_due=card.days_until_due,
                interval_days=card.interval_days,
                metadata={
                    "source": "anki",
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
            raise AnkiImportError(f"Anki {name} must not be empty.")
        return value


def build_deck_query(deck: str) -> str:
    escaped = deck.replace("\\", "\\\\").replace('"', '\\"')
    return f'deck:"{escaped}"'


def clean_anki_field(value: str) -> str:
    without_breaks = HTML_BREAK_RE.sub(" ", value)
    without_tags = HTML_TAG_RE.sub(" ", without_breaks)
    return WHITESPACE_RE.sub(" ", html.unescape(without_tags)).strip()


def _extract_word(card: AnkiCard, word_field: str) -> tuple[str, str] | SkippedAnkiCard:
    field = card.fields.get(word_field)
    if not isinstance(field, dict) or "value" not in field:
        return SkippedAnkiCard(card.card_id, "missing_field")
    raw_value = field["value"]
    if not isinstance(raw_value, str):
        return SkippedAnkiCard(card.card_id, "empty_field")

    original_value = clean_anki_field(raw_value)
    word = original_value.casefold()
    if not word:
        return SkippedAnkiCard(card.card_id, "empty_field")
    return original_value, word


def _schedule_for_card(card: AnkiCard) -> tuple[str, int | None, int | None]:
    if card.suspended:
        return SUSPENDED, None, None
    if card.card_type == 0 or card.reps <= 0:
        return UNSCHEDULED, None, None

    interval_days = max(card.interval, 1)
    days_until_due = 0 if card.due_now else interval_days
    return SCHEDULED, days_until_due, interval_days


def _aggregate_cards(cards: list[ImportedAnkiCard]) -> list[AggregatedAnkiCard]:
    aggregated: dict[str, AggregatedAnkiCard] = {}
    for card in cards:
        current = aggregated.get(card.word)
        detail = dict(card.metadata)
        if current is None:
            aggregated[card.word] = AggregatedAnkiCard(
                word=card.word,
                schedule_status=card.schedule_status,
                days_until_due=card.days_until_due,
                interval_days=card.interval_days,
                cards=[detail],
            )
            continue

        current.cards.append(detail)
        if _schedule_priority(card) < _schedule_priority(current):
            current.schedule_status = card.schedule_status
            current.days_until_due = card.days_until_due
            current.interval_days = card.interval_days

    return list(aggregated.values())


def _schedule_priority(card: ImportedAnkiCard | AggregatedAnkiCard) -> tuple[int, int, int]:
    if card.schedule_status == SCHEDULED:
        return (0, card.days_until_due or 0, card.interval_days or 1)
    if card.schedule_status == UNSCHEDULED:
        return (1, 0, 0)
    return (2, 0, 0)


def _parse_card(raw_card: dict[str, Any], *, suspended: bool, due_now: bool) -> AnkiCard:
    fields = raw_card.get("fields")
    if not isinstance(fields, dict):
        raise AnkiImportError("AnkiConnect cardsInfo returned a card without fields.")

    return AnkiCard(
        card_id=_required_int(raw_card.get("cardId"), "cardId"),
        note_id=_required_int(raw_card.get("note"), "note"),
        deck_name=_required_str(raw_card.get("deckName"), "deckName"),
        model_name=_required_str(raw_card.get("modelName"), "modelName"),
        fields=fields,
        interval=_optional_int(raw_card.get("interval")),
        due=_optional_int(raw_card.get("due")),
        queue=_optional_int(raw_card.get("queue")),
        card_type=_optional_int(raw_card.get("type")),
        reps=_optional_int(raw_card.get("reps")),
        lapses=_optional_int(raw_card.get("lapses")),
        mod=_optional_int_or_none(raw_card.get("mod")),
        suspended=suspended,
        due_now=due_now,
    )


def _required_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise AnkiImportError(f"AnkiConnect cardsInfo returned invalid {name}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AnkiImportError(f"AnkiConnect cardsInfo returned invalid {name}.") from exc


def _optional_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise AnkiImportError(f"AnkiConnect cardsInfo returned invalid {name}.")
    return value
