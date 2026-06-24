from __future__ import annotations

from typing import Any

from moku_backend.persistence.models import DictionaryEntry, DictionarySource
from moku_backend.persistence.repositories.dictionary_repository import (
    DictionaryEntrySpec,
    DictionaryEntryTermSpec,
    DictionaryRepository,
    normalize_dictionary_term,
    normalize_source_key,
)


class _FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        scalars: list[object] | None = None,
    ) -> None:
        self.scalar = scalar
        self.scalar_values = scalars or []

    def scalar_one_or_none(self) -> object | None:
        return self.scalar

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.scalar_values)


class _FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _FakeSession:
    def __init__(
        self,
        *,
        source: DictionarySource | None = None,
        lookup_entries: list[DictionaryEntry] | None = None,
    ) -> None:
        self.source = source
        self.lookup_entries = lookup_entries or []
        self.executed: list[Any] = []
        self.added: list[object] = []
        self.added_all: list[object] = []
        self.flush_count = 0

    async def execute(self, statement: Any) -> _FakeResult:
        self.executed.append(statement)
        if "FROM dictionary_sources" in str(statement):
            return _FakeResult(scalar=self.source)
        if "FROM dictionary_entries" in str(statement):
            return _FakeResult(scalars=self.lookup_entries)
        return _FakeResult()

    def add(self, value: object) -> None:
        if isinstance(value, DictionarySource) and value.id is None:
            value.id = 42
        self.added.append(value)

    def add_all(self, values: list[object]) -> None:
        self.added_all.extend(values)

    async def flush(self) -> None:
        self.flush_count += 1


async def test_replace_source_entries_creates_normalized_source_and_terms() -> None:
    session = _FakeSession()
    repository = DictionaryRepository(session)

    source = await repository.replace_source_entries(
        source_key="CC_CEDICT",
        language="zh-CN",
        definition_language="EN",
        version=None,
        license_name="CC BY-SA 4.0",
        license_url="https://example.test/license",
        attribution="CC-CEDICT",
        metadata={"file_name": "cedict.txt"},
        entries=[
            DictionaryEntrySpec(
                headword="\u5b66\u4e60",
                reading="xue2 xi2",
                senses=(("to learn",),),
                terms=(
                    DictionaryEntryTermSpec("\u5b66\u4e60", "simplified"),
                    DictionaryEntryTermSpec("\u5b78\u7fd2", "traditional"),
                ),
            )
        ],
    )

    assert source.source_key == "cc-cedict"
    assert source.language == "zh_cn"
    assert source.definition_language == "en"
    assert source.entry_count == 1
    entry = session.added_all[0]
    assert isinstance(entry, DictionaryEntry)
    assert [term.normalized_term for term in entry.terms] == [
        "\u5b66\u4e60",
        "\u5b78\u7fd2",
    ]


async def test_replace_source_entries_deletes_existing_entries_before_import() -> None:
    existing = DictionarySource(
        id=99,
        source_key="cc-cedict",
        language="zh_cn",
        definition_language="en",
        license_name="old",
        license_url="old",
        attribution="old",
        source_metadata={},
    )
    session = _FakeSession(source=existing)
    repository = DictionaryRepository(session)

    await repository.replace_source_entries(
        source_key="cc-cedict",
        language="zh_CN",
        definition_language="en",
        version="new",
        license_name="CC BY-SA 4.0",
        license_url="https://example.test/license",
        attribution="CC-CEDICT",
        metadata={},
        entries=[],
    )

    assert existing.version == "new"
    assert existing.entry_count == 0
    assert any("DELETE FROM dictionary_entries" in str(statement) for statement in session.executed)


async def test_lookup_entries_filters_by_normalized_term_and_languages() -> None:
    repository = DictionaryRepository(_FakeSession())

    await repository.lookup_entries(
        term="  ABC  ",
        language="zh-CN",
        definition_language="EN",
        limit=20,
    )

    statement = repository.session.executed[0]
    params = statement.compile().params
    assert "abc" in params.values()
    assert "zh_cn" in params.values()
    assert "en" in params.values()


def test_dictionary_normalizers() -> None:
    assert normalize_source_key("CC_CEDICT") == "cc-cedict"
    assert normalize_dictionary_term("  ABC  ") == "abc"
