"""Dictionary persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from moku_core.text.languages import normalize_language
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from moku_backend.persistence.models import (
    DictionaryEntry,
    DictionaryEntryTerm,
    DictionarySource,
)


@dataclass(frozen=True)
class DictionaryEntryTermSpec:
    term: str
    term_kind: str


@dataclass(frozen=True)
class DictionaryEntrySpec:
    headword: str
    reading: str
    senses: Sequence[Sequence[str]]
    terms: Sequence[DictionaryEntryTermSpec]
    metadata: dict[str, object] = field(default_factory=dict)


class DictionaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_source_entries(
        self,
        *,
        source_key: str,
        language: str,
        definition_language: str,
        version: str | None,
        license_name: str,
        license_url: str,
        attribution: str,
        metadata: dict[str, object],
        entries: Sequence[DictionaryEntrySpec],
    ) -> DictionarySource:
        normalized_source_key = normalize_source_key(source_key)
        normalized_language = normalize_language(language)
        normalized_definition_language = normalize_language(definition_language)
        source = await self.get_source(
            source_key=normalized_source_key,
            language=normalized_language,
            definition_language=normalized_definition_language,
        )
        if source is None:
            source = DictionarySource(
                source_key=normalized_source_key,
                language=normalized_language,
                definition_language=normalized_definition_language,
                version=version,
                license_name=license_name,
                license_url=license_url,
                attribution=attribution,
                entry_count=0,
                source_metadata=metadata,
            )
            self.session.add(source)
            await self.session.flush()
        else:
            source.version = version
            source.license_name = license_name
            source.license_url = license_url
            source.attribution = attribution
            source.source_metadata = metadata
            await self.session.execute(
                delete(DictionaryEntry).where(DictionaryEntry.dictionary_source_id == source.id)
            )

        source.entry_count = len(entries)
        self.session.add_all([_entry_model(source, entry) for entry in entries])
        await self.session.flush()
        return source

    async def get_source(
        self,
        *,
        source_key: str,
        language: str,
        definition_language: str,
    ) -> DictionarySource | None:
        result = await self.session.execute(
            select(DictionarySource).where(
                DictionarySource.source_key == normalize_source_key(source_key),
                DictionarySource.language == normalize_language(language),
                DictionarySource.definition_language == normalize_language(definition_language),
            )
        )
        return result.scalar_one_or_none()

    async def lookup_entries(
        self,
        *,
        term: str,
        language: str,
        definition_language: str,
        limit: int,
    ) -> list[DictionaryEntry]:
        normalized_term = normalize_dictionary_term(term)
        matching_ids = (
            select(DictionaryEntry.id)
            .join(DictionaryEntry.source)
            .join(DictionaryEntry.terms)
            .where(
                DictionarySource.language == normalize_language(language),
                DictionarySource.definition_language == normalize_language(definition_language),
                DictionaryEntryTerm.normalized_term == normalized_term,
            )
            .distinct()
            .order_by(DictionaryEntry.id)
            .limit(limit)
            .subquery()
        )
        result = await self.session.execute(
            select(DictionaryEntry)
            .where(DictionaryEntry.id.in_(select(matching_ids.c.id)))
            .options(
                selectinload(DictionaryEntry.source),
                selectinload(DictionaryEntry.terms),
            )
            .order_by(DictionaryEntry.id)
        )
        return list(result.scalars().all())


def normalize_source_key(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def normalize_dictionary_term(value: str) -> str:
    return value.strip().casefold()


def _entry_model(source: DictionarySource, spec: DictionaryEntrySpec) -> DictionaryEntry:
    entry = DictionaryEntry(
        source=source,
        headword=spec.headword,
        reading=spec.reading,
        senses=[list(sense) for sense in spec.senses],
        source_metadata=spec.metadata,
    )
    entry.terms = [
        DictionaryEntryTerm(
            term=term.term,
            normalized_term=normalize_dictionary_term(term.term),
            term_kind=term.term_kind,
        )
        for term in spec.terms
    ]
    return entry
