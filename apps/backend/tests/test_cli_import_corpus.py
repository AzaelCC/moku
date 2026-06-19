from __future__ import annotations

import moku_backend.cli.app as cli_app
from moku_backend.services.corpus_import_service import CorpusImportResult
from typer.testing import CliRunner


def test_import_corpus_cli_defaults_to_unbounded_limits(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_import_corpus(**kwargs: object) -> CorpusImportResult:
        seen.update(kwargs)
        return CorpusImportResult(
            run_public_id="run-id",
            corpus_public_id="corpus-id",
            corpus_name="sample-en",
            sentence_count=35,
            seeded_learner_cards=0,
        )

    monkeypatch.setattr(cli_app, "_import_corpus", fake_import_corpus)

    result = CliRunner().invoke(
        cli_app.app,
        ["import-corpus", "--source", "sample", "--language", "en"],
    )

    assert result.exit_code == 0
    assert seen["max_documents"] is None
    assert seen["max_sentences"] is None
    assert "Imported 35 sentences into sample-en" in result.output
