from __future__ import annotations

import moku_backend.cli.app as cli_app
from moku_backend.services.dictionary_import_service import (
    DictionaryImportError,
    DictionaryImportResult,
)
from typer.testing import CliRunner


def test_import_dictionary_cli_passes_options(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_import_dictionary(**kwargs: object) -> DictionaryImportResult:
        seen.update(kwargs)
        return DictionaryImportResult(
            source_public_id="source-id",
            source_key="cc-cedict",
            language="zh_cn",
            definition_language="en",
            entry_count=2,
        )

    monkeypatch.setattr(cli_app, "_import_dictionary", fake_import_dictionary)

    result = CliRunner().invoke(
        cli_app.app,
        [
            "import-dictionary",
            "--source",
            "cc-cedict",
            "--language",
            "zh-CN",
            "--definition-language",
            "en",
            "--path",
            "cedict.txt.gz",
        ],
    )

    assert result.exit_code == 0
    assert seen == {
        "source": "cc-cedict",
        "language": "zh-CN",
        "definition_language": "en",
        "path": "cedict.txt.gz",
    }
    assert "Imported 2 dictionary entries from cc-cedict" in result.output


def test_import_dictionary_cli_reports_import_errors(monkeypatch) -> None:
    async def fake_import_dictionary(**_kwargs: object) -> DictionaryImportResult:
        raise DictionaryImportError("bad dictionary")

    monkeypatch.setattr(cli_app, "_import_dictionary", fake_import_dictionary)

    result = CliRunner().invoke(
        cli_app.app,
        ["import-dictionary", "--path", "bad.txt"],
    )

    assert result.exit_code != 0
    assert "bad dictionary" in result.output
