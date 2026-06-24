from __future__ import annotations

from uuid import uuid4

from moku_backend.config import Settings
from moku_backend.persistence.models import DictionaryEntry, DictionarySource
from moku_backend.services.dictionary_service import DictionaryService


class _FakeRepository:
    seen: dict[str, object] = {}

    def __init__(self, session: object) -> None:
        pass

    async def lookup_entries(self, **kwargs: object) -> list[DictionaryEntry]:
        self.__class__.seen = kwargs
        source = DictionarySource(
            source_key="cc-cedict",
            language="zh_cn",
            definition_language="en",
            version=None,
            license_name="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            attribution="CC-CEDICT",
            source_metadata={},
        )
        return [
            DictionaryEntry(
                public_id=uuid4(),
                source=source,
                headword="\u5b66\u4e60",
                reading="xue2 xi2",
                senses=[["to learn", "to study"]],
                source_metadata={
                    "simplified": "\u5b66\u4e60",
                    "traditional": "\u5b78\u7fd2",
                },
            )
        ]


async def test_dictionary_service_returns_language_agnostic_lookup(monkeypatch) -> None:
    monkeypatch.setattr(
        "moku_backend.services.dictionary_service.DictionaryRepository",
        _FakeRepository,
    )
    service = DictionaryService(
        object(),
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
    )

    result = await service.lookup(
        term="\u5b66\u4e60",
        language="zh-CN",
        definition_language="EN",
        limit=20,
    )

    assert _FakeRepository.seen["term"] == "\u5b66\u4e60"
    assert _FakeRepository.seen["language"] == "zh-CN"
    assert result.language == "zh_cn"
    assert result.definition_language == "en"
    assert result.entries[0].forms == {
        "simplified": "\u5b66\u4e60",
        "traditional": "\u5b78\u7fd2",
    }
    assert result.entries[0].source.license_name == "CC BY-SA 4.0"
