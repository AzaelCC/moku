"""Dictionary import orchestration."""

from __future__ import annotations

import gzip
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from moku_core.dictionary import CcCedictEntry, CcCedictParseError, parse_cc_cedict_lines
from moku_core.text.languages import normalize_language
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.repositories.dictionary_repository import (
    DictionaryEntrySpec,
    DictionaryEntryTermSpec,
    DictionaryRepository,
    normalize_source_key,
)

CC_CEDICT_SOURCE_KEY = "cc-cedict"
CC_CEDICT_LICENSE_NAME = "CC BY-SA 4.0"
CC_CEDICT_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
CC_CEDICT_ATTRIBUTION = "CC-CEDICT, maintained by MDBG and CC-CEDICT editors."


class DictionaryImportError(RuntimeError):
    """Raised when a dictionary import cannot be completed."""


@dataclass(frozen=True)
class DictionaryImportResult:
    source_public_id: str
    source_key: str
    language: str
    definition_language: str
    entry_count: int


class DictionaryImportService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.dictionaries = DictionaryRepository(session)

    async def import_dictionary(
        self,
        *,
        source: str,
        language: str,
        definition_language: str,
        path: str,
    ) -> DictionaryImportResult:
        normalized_source = normalize_source_key(source)
        if normalized_source != CC_CEDICT_SOURCE_KEY:
            raise DictionaryImportError("Unsupported dictionary source. Use cc-cedict.")

        source_path = Path(path)
        try:
            entries = [
                _entry_spec(entry)
                for entry in parse_cc_cedict_lines(_read_dictionary_lines(source_path))
            ]
            dictionary_source = await self.dictionaries.replace_source_entries(
                source_key=normalized_source,
                language=language,
                definition_language=definition_language,
                version=None,
                license_name=CC_CEDICT_LICENSE_NAME,
                license_url=CC_CEDICT_LICENSE_URL,
                attribution=CC_CEDICT_ATTRIBUTION,
                metadata={"file_name": source_path.name},
                entries=entries,
            )
            await self.session.commit()
        except (OSError, zipfile.BadZipFile, CcCedictParseError) as exc:
            await self.session.rollback()
            raise DictionaryImportError(str(exc)) from exc
        except Exception:
            await self.session.rollback()
            raise

        return DictionaryImportResult(
            source_public_id=str(dictionary_source.public_id),
            source_key=dictionary_source.source_key,
            language=normalize_language(language),
            definition_language=normalize_language(definition_language),
            entry_count=len(entries),
        )


def _read_dictionary_lines(path: Path) -> Iterable[str]:
    if not path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".gz":
        return _iter_text_file(gzip.open(path, "rt", encoding="utf-8-sig"))
    if suffix == ".zip":
        return _iter_zip_text_file(path)
    if suffix == ".txt":
        return _iter_text_file(path.open("rt", encoding="utf-8-sig"))

    raise DictionaryImportError("Unsupported dictionary file type. Use .txt, .gz, or .zip.")


def _iter_text_file(handle: TextIO) -> Iterator[str]:
    with handle:
        yield from handle


def _iter_zip_text_file(path: Path) -> Iterator[str]:
    with zipfile.ZipFile(path) as archive:
        name = _zip_member_name(archive)
        with archive.open(name) as raw:
            for line in raw.read().decode("utf-8-sig").splitlines():
                yield f"{line}\n"


def _zip_member_name(archive: zipfile.ZipFile) -> str:
    candidates = [name for name in archive.namelist() if not name.endswith("/")]
    txt_candidates = [name for name in candidates if name.lower().endswith(".txt")]
    if txt_candidates:
        return sorted(txt_candidates)[0]
    if candidates:
        return sorted(candidates)[0]
    raise DictionaryImportError("Dictionary ZIP archive does not contain a file.")


def _entry_spec(entry: CcCedictEntry) -> DictionaryEntrySpec:
    return DictionaryEntrySpec(
        headword=entry.simplified,
        reading=entry.pinyin,
        senses=entry.senses,
        terms=(
            DictionaryEntryTermSpec(term=entry.simplified, term_kind="simplified"),
            DictionaryEntryTermSpec(term=entry.traditional, term_kind="traditional"),
        ),
        metadata={
            "source": CC_CEDICT_SOURCE_KEY,
            "traditional": entry.traditional,
            "simplified": entry.simplified,
            "pinyin_format": entry.pinyin_format,
            "line_number": entry.line_number,
            "raw_line": entry.raw_line,
        },
    )
