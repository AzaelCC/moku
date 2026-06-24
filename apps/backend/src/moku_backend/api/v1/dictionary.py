"""Dictionary API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.api.deps import get_session, get_settings
from moku_backend.config import Settings
from moku_backend.services.dictionary_service import DictionaryService

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


class DictionarySourceResponse(BaseModel):
    source_key: str
    version: str | None = None
    license_name: str
    license_url: str
    attribution: str


class DictionaryEntryResponse(BaseModel):
    entry_id: UUID
    headword: str
    forms: dict[str, str]
    reading: str
    senses: list[list[str]]
    source: DictionarySourceResponse


class DictionaryLookupResponse(BaseModel):
    term: str
    language: str
    definition_language: str
    entries: list[DictionaryEntryResponse] = Field(default_factory=list)


@router.get("/lookup", response_model=DictionaryLookupResponse)
async def lookup_dictionary(
    *,
    term: Annotated[str, Query(min_length=1, max_length=255)],
    language: Annotated[str, Query(min_length=1, max_length=32)],
    definition_language: Annotated[str, Query(min_length=1, max_length=32)] = "en",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DictionaryLookupResponse:
    service = DictionaryService(session, settings)
    result = await service.lookup(
        term=term,
        language=language,
        definition_language=definition_language,
        limit=limit,
    )
    return DictionaryLookupResponse(
        term=result.term,
        language=result.language,
        definition_language=result.definition_language,
        entries=[
            DictionaryEntryResponse(
                entry_id=entry.entry_id,
                headword=entry.headword,
                forms=entry.forms,
                reading=entry.reading,
                senses=entry.senses,
                source=DictionarySourceResponse(
                    source_key=entry.source.source_key,
                    version=entry.source.version,
                    license_name=entry.source.license_name,
                    license_url=entry.source.license_url,
                    attribution=entry.source.attribution,
                ),
            )
            for entry in result.entries
        ],
    )
