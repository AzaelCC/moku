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
                "ord": 0,
                "templateName": "Reading",
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


def test_build_note_specs_preserves_notes_and_card_types() -> None:
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
        _card(
            card_id=7,
            note_id=101,
            value="<b>Casa&nbsp;Grande</b>",
            ord_value=1,
            template_name="Listening",
        ),
        _card(
            card_id=8,
            note_id=101,
            value="<b>Casa&nbsp;Grande</b>",
            ord_value=0,
            template_name="Reading",
        ),
    ]

    specs, skipped, duplicate_count = service._build_note_specs(
        cards=cards,
        deck="Japanese",
        word_field="Expression",
    )

    specs_by_key = {spec.note_key: spec for spec in specs}
    assert set(specs_by_key) == {"anki:101", "anki:102", "anki:105", "anki:106"}
    assert duplicate_count == 1
    assert [skip.reason for skip in skipped] == ["missing_field", "empty_field"]

    casa = specs_by_key["anki:101"]
    assert casa.word == "casa grande"
    assert casa.metadata["note_id"] == 101
    assert casa.metadata["original_field_value"] == "Casa Grande"
    assert casa.metadata["fields"] == {"Expression": "Casa Grande"}
    assert [card.card_type for card in casa.cards] == ["reading", "listening"]
    assert casa.cards[0].schedule_status == "scheduled"
    assert casa.cards[0].scheduling_algorithm == "anki"
    assert casa.cards[0].fsrs_card is None
    assert casa.cards[0].days_until_due == 0
    assert casa.cards[0].interval_days == 7
    assert casa.cards[0].metadata["card_id"] == 1
    assert casa.cards[1].metadata["card_id"] == 7

    same_word_other_note = specs_by_key["anki:102"]
    assert same_word_other_note.word == "casa grande"
    assert same_word_other_note.cards[0].metadata["card_id"] == 2

    assert specs_by_key["anki:105"].cards[0].schedule_status == "unscheduled"
    assert specs_by_key["anki:105"].cards[0].days_until_due is None
    assert specs_by_key["anki:106"].cards[0].schedule_status == "suspended"
    assert specs_by_key["anki:106"].cards[0].interval_days is None


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
    ord_value: int | None = 0,
    template_name: str | None = "Reading",
) -> AnkiCard:
    if fields is None:
        fields = {"Expression": {"value": value}}
    return AnkiCard(
        card_id=card_id,
        note_id=note_id,
        deck_name="Japanese",
        model_name="Basic",
        fields=fields,
        ord=ord_value,
        template_name=template_name,
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
