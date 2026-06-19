from __future__ import annotations

import moku_backend.cli.app as cli_app
from moku_backend.services.anki_import_service import (
    AnkiImportError,
    AnkiImportResult,
    SkippedAnkiCard,
)
from typer.testing import CliRunner


def test_import_anki_cli_prints_summary(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_import_anki(**kwargs: object) -> AnkiImportResult:
        seen.update(kwargs)
        return AnkiImportResult(
            learner_public_id="learner-id",
            learner_handle="default",
            deck="Japanese",
            language="en",
            found_card_count=5,
            imported_card_count=3,
            scheduled_count=1,
            unscheduled_count=1,
            suspended_count=1,
            skipped_missing_field_count=1,
            skipped_empty_field_count=1,
            skipped_too_long_count=0,
            duplicate_card_count=1,
            skipped_samples=(SkippedAnkiCard(42, "missing_field"),),
        )

    monkeypatch.setattr(cli_app, "_import_anki", fake_import_anki)

    result = CliRunner().invoke(
        cli_app.app,
        [
            "import-anki",
            "--deck",
            "Japanese",
            "--word-field",
            "Expression",
            "--language",
            "en",
        ],
    )

    assert result.exit_code == 0
    assert seen == {
        "deck": "Japanese",
        "word_field": "Expression",
        "language": "en",
        "learner_handle": None,
    }
    assert "Imported 3 learner cards from Anki deck Japanese" in result.output
    assert "scheduled=1, unscheduled=1, suspended=1" in result.output
    assert "skipped=2" in result.output
    assert "Skipped sample cards: 42:missing_field" in result.output


def test_import_anki_cli_reports_import_errors(monkeypatch) -> None:
    async def fake_import_anki(**_kwargs: object) -> AnkiImportResult:
        raise AnkiImportError("Anki deck not found: Missing")

    monkeypatch.setattr(cli_app, "_import_anki", fake_import_anki)

    result = CliRunner().invoke(
        cli_app.app,
        ["import-anki", "--deck", "Missing", "--word-field", "Expression"],
    )

    assert result.exit_code != 0
    assert "Anki deck not found: Missing" in result.output


def test_import_anki_cli_requires_deck_and_word_field() -> None:
    result = CliRunner().invoke(cli_app.app, ["import-anki", "--deck", "Japanese"])

    assert result.exit_code != 0
    assert "word-field" in result.output
