from __future__ import annotations

import gzip
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from moku_backend.config import Settings
from moku_backend.persistence.models import DictionarySource
from moku_backend.services import dictionary_import_service as import_service
from moku_backend.services.dictionary_import_service import (
    DictionaryImportError,
    DictionaryImportService,
    _read_dictionary_lines,
)


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class _FakeDictionaryRepository:
    seen_entries: list[object] = []
    seen_kwargs: dict[str, object] = {}

    def __init__(self, session: object) -> None:
        pass

    async def replace_source_entries(self, **kwargs: object) -> DictionarySource:
        self.__class__.seen_kwargs = kwargs
        self.__class__.seen_entries = list(kwargs["entries"])
        return DictionarySource(
            id=1,
            public_id=uuid4(),
            source_key=str(kwargs["source_key"]),
            language=str(kwargs["language"]).lower().replace("-", "_"),
            definition_language=str(kwargs["definition_language"]).lower().replace("-", "_"),
            license_name=str(kwargs["license_name"]),
            license_url=str(kwargs["license_url"]),
            attribution=str(kwargs["attribution"]),
            entry_count=len(self.__class__.seen_entries),
            source_metadata={},
        )


def test_read_dictionary_lines_supports_txt_gz_and_zip(tmp_path: Path) -> None:
    text = "\u738b \u738b [[wang2]] /king/\n"
    txt_path = tmp_path / "cedict.txt"
    txt_path.write_text(text, encoding="utf-8")
    gz_path = tmp_path / "cedict.txt.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write(text)
    zip_path = tmp_path / "cedict.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nested/cedict.txt", text)

    assert list(_read_dictionary_lines(txt_path)) == [text]
    assert list(_read_dictionary_lines(gz_path)) == [text]
    assert list(_read_dictionary_lines(zip_path)) == [text]


async def test_import_dictionary_parses_cc_cedict_and_replaces_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_service, "DictionaryRepository", _FakeDictionaryRepository)
    path = tmp_path / "cedict.txt"
    path.write_text(
        "# header\n"
        "\u5b78\u7fd2 \u5b66\u4e60 [xue2 xi2] /to learn; to study/\n",
        encoding="utf-8",
    )
    session = _FakeSession()
    service = DictionaryImportService(
        session,
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
    )

    result = await service.import_dictionary(
        source="cc-cedict",
        language="zh-CN",
        definition_language="EN",
        path=str(path),
    )

    assert result.source_key == "cc-cedict"
    assert result.language == "zh_cn"
    assert result.definition_language == "en"
    assert result.entry_count == 1
    assert session.commit_count == 1
    spec = _FakeDictionaryRepository.seen_entries[0]
    assert spec.headword == "\u5b66\u4e60"
    assert spec.reading == "xue2 xi2"
    assert spec.senses == (("to learn", "to study"),)


async def test_import_dictionary_rolls_back_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("bad line\n", encoding="utf-8")
    session = _FakeSession()
    service = DictionaryImportService(
        session,
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
    )

    with pytest.raises(DictionaryImportError, match="Malformed"):
        await service.import_dictionary(
            source="cc-cedict",
            language="zh",
            definition_language="en",
            path=str(path),
        )

    assert session.rollback_count == 1


async def test_import_dictionary_rejects_unknown_source(tmp_path: Path) -> None:
    path = tmp_path / "cedict.txt"
    path.write_text("", encoding="utf-8")
    service = DictionaryImportService(
        _FakeSession(),
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
    )

    with pytest.raises(DictionaryImportError, match="Unsupported"):
        await service.import_dictionary(
            source="other",
            language="zh",
            definition_language="en",
            path=str(path),
        )
