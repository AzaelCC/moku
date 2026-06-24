"""Dictionary lookup service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from moku_core.text.languages import normalize_language
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.models import DictionaryEntry
from moku_backend.persistence.repositories.dictionary_repository import DictionaryRepository


@dataclass(frozen=True)
class DictionarySourceSummary:
    source_key: str
    version: str | None
    license_name: str
    license_url: str
    attribution: str


@dataclass(frozen=True)
class DictionaryLookupEntry:
    entry_id: UUID
    headword: str
    forms: dict[str, str]
    reading: str
    senses: list[list[str]]
    source: DictionarySourceSummary


@dataclass(frozen=True)
class DictionaryLookupResult:
    term: str
    language: str
    definition_language: str
    entries: list[DictionaryLookupEntry]


class DictionaryService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.dictionaries = DictionaryRepository(session)

    async def lookup(
        self,
        *,
        term: str,
        language: str,
        definition_language: str,
        limit: int,
    ) -> DictionaryLookupResult:
        entries = await self.dictionaries.lookup_entries(
            term=term,
            language=language,
            definition_language=definition_language,
            limit=limit,
        )
        return DictionaryLookupResult(
            term=term,
            language=normalize_language(language),
            definition_language=normalize_language(definition_language),
            entries=[_lookup_entry(entry) for entry in entries],
        )


def _lookup_entry(entry: DictionaryEntry) -> DictionaryLookupEntry:
    source_metadata = entry.source_metadata or {}
    forms = {
        "simplified": str(source_metadata.get("simplified", entry.headword)),
        "traditional": str(source_metadata.get("traditional", entry.headword)),
    }
    return DictionaryLookupEntry(
        entry_id=entry.public_id,
        headword=entry.headword,
        forms=forms,
        reading=entry.reading,
        senses=[list(sense) for sense in entry.senses],
        source=DictionarySourceSummary(
            source_key=entry.source.source_key,
            version=entry.source.version,
            license_name=entry.source.license_name,
            license_url=entry.source.license_url,
            attribution=entry.source.attribution,
        ),
    )
