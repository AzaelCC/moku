from __future__ import annotations

import pytest
from moku_backend.config import Settings
from moku_backend.services.anki_import_service import (
    AnkiCard,
    AnkiImportError,
    AnkiImportService,
    build_deck_query,
    clean_anki_field,
)


class FakeSession:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeAnkiClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def deck_names(self) -> list[str]:
        return ["Japanese", "Spanish::Words"]

    def find_cards(self, query: str) -> list[int]:
        self.queries.append(query)
        return [1]

    def cards_info(self, cards: list[int]) -> list[dict[str, object]]:
        return [
            {
                "cardId": cards[0],
                "note": 101,
                "deckName": "Japanese::Core",
                "modelName": "Basic",
                "fields": {"Expression": {"value": "Casa"}},
                "interval": 7,
                "due": 0,
                "queue": 2,
                "type": 2,
                "reps": 4,
                "lapses": 0,
                "mod": 123,
            }
        ]

    def are_suspended(self, cards: list[int]) -> dict[int, bool]:
        return {card: False for card in cards}

    def are_due(self, cards: list[int]) -> dict[int, bool]:
        return {card: True for card in cards}


def test_build_deck_query_quotes_deck_and_keeps_subdeck_scope() -> None:
    assert build_deck_query('Japanese "Core"') == 'deck:"Japanese \\"Core\\""'


def test_clean_anki_field_strips_html_entities_and_whitespace() -> None:
    assert clean_anki_field("<div>Casa&nbsp;<b>Grande</b></div>") == "Casa Grande"


def test_fetch_cards_uses_deck_query_that_includes_subdecks() -> None:
    client = FakeAnkiClient()
    service = AnkiImportService(
        FakeSession(),
        Settings(database_url="postgresql+asyncpg://unused/unused"),
        client=client,
    )

    cards = service._fetch_cards("Japanese")

    assert client.queries == ['deck:"Japanese"']
    assert len(cards) == 1
    assert cards[0].deck_name == "Japanese::Core"
    assert cards[0].due_now is True


def test_fetch_cards_fails_when_deck_is_missing() -> None:
    service = AnkiImportService(
        FakeSession(),
        Settings(database_url="postgresql+asyncpg://unused/unused"),
        client=FakeAnkiClient(),
    )

    with pytest.raises(AnkiImportError, match="Anki deck not found"):
        service._fetch_cards("Missing")


def test_build_card_specs_normalizes_skips_and_deduplicates_cards() -> None:
    service = AnkiImportService(
        FakeSession(),
        Settings(database_url="postgresql+asyncpg://unused/unused"),
        client=FakeAnkiClient(),
    )
    cards = [
        _card(
            card_id=1,
            note_id=101,
            value="<b>Casa&nbsp;Grande</b>",
            interval=7,
            due_now=True,
        ),
        _card(
            card_id=2,
            note_id=102,
            value="casa grande",
            interval=21,
            due_now=False,
        ),
        _card(card_id=3, note_id=103, fields={}),
        _card(card_id=4, note_id=104, value="<br>"),
        _card(card_id=5, note_id=105, value="Waiting Room", card_type=0, reps=0),
        _card(card_id=6, note_id=106, value="Paused", suspended=True),
    ]

    specs, skipped, duplicate_count = service._build_card_specs(
        cards=cards,
        deck="Japanese",
        word_field="Expression",
    )

    specs_by_word = {spec.word: spec for spec in specs}
    assert set(specs_by_word) == {"casa grande", "waiting room", "paused"}
    assert duplicate_count == 1
    assert [skip.reason for skip in skipped] == ["missing_field", "empty_field"]

    casa = specs_by_word["casa grande"]
    assert casa.schedule_status == "scheduled"
    assert casa.scheduling_algorithm == "anki"
    assert casa.fsrs_card is None
    assert casa.days_until_due == 0
    assert casa.interval_days == 7
    assert casa.metadata["card_ids"] == [1, 2]
    assert casa.metadata["note_ids"] == [101, 102]
    assert casa.metadata["cards"][0]["original_field_value"] == "Casa Grande"

    assert specs_by_word["waiting room"].schedule_status == "unscheduled"
    assert specs_by_word["waiting room"].days_until_due is None
    assert specs_by_word["paused"].schedule_status == "suspended"
    assert specs_by_word["paused"].interval_days is None


def _card(
    *,
    card_id: int,
    note_id: int,
    value: str | None = None,
    fields: dict[str, object] | None = None,
    interval: int = 7,
    due_now: bool = False,
    card_type: int = 2,
    reps: int = 3,
    suspended: bool = False,
) -> AnkiCard:
    if fields is None:
        fields = {"Expression": {"value": value}}
    return AnkiCard(
        card_id=card_id,
        note_id=note_id,
        deck_name="Japanese",
        model_name="Basic",
        fields=fields,
        interval=interval,
        due=0,
        queue=2,
        card_type=card_type,
        reps=reps,
        lapses=0,
        mod=123,
        suspended=suspended,
        due_now=due_now,
    )
