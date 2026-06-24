"""CC-CEDICT parser."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

_ENTRY_RE = re.compile(
    r"^(?P<traditional>\S+)\s+"
    r"(?P<simplified>\S+)\s+"
    r"(?P<reading>\[\[[^\]]+\]\]|\[[^\]]+\])\s+"
    r"(?P<definitions>/.*?/)\s*$"
)


class CcCedictParseError(ValueError):
    """Raised when a CC-CEDICT line cannot be parsed."""


@dataclass(frozen=True)
class CcCedictEntry:
    traditional: str
    simplified: str
    pinyin: str
    pinyin_format: str
    senses: tuple[tuple[str, ...], ...]
    raw_line: str
    line_number: int | None = None


def parse_cc_cedict_line(line: str, *, line_number: int | None = None) -> CcCedictEntry | None:
    """Parse one CC-CEDICT data line.

    Blank and comment lines return None. Entries may use either v1 single-bracket
    pinyin or v2 double-bracket pinyin.
    """
    raw_line = line.rstrip("\n\r")
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    match = _ENTRY_RE.match(stripped)
    if match is None:
        raise _parse_error("Malformed CC-CEDICT entry", line_number)

    reading = match.group("reading")
    if reading.startswith("[[") and reading.endswith("]]"):
        pinyin = reading[2:-2]
        pinyin_format = "v2"
    elif reading.startswith("[") and reading.endswith("]"):
        pinyin = reading[1:-1]
        pinyin_format = "v1"
    else:
        raise _parse_error("Malformed CC-CEDICT pinyin", line_number)

    senses = _parse_definitions(match.group("definitions"), line_number=line_number)
    return CcCedictEntry(
        traditional=match.group("traditional"),
        simplified=match.group("simplified"),
        pinyin=pinyin,
        pinyin_format=pinyin_format,
        senses=senses,
        raw_line=raw_line,
        line_number=line_number,
    )


def parse_cc_cedict_lines(lines: Iterable[str]) -> Iterator[CcCedictEntry]:
    """Parse CC-CEDICT lines, skipping blank and comment rows."""
    for line_number, line in enumerate(lines, start=1):
        entry = parse_cc_cedict_line(line, line_number=line_number)
        if entry is not None:
            yield entry


def _parse_definitions(
    definitions: str,
    *,
    line_number: int | None,
) -> tuple[tuple[str, ...], ...]:
    if not definitions.startswith("/") or not definitions.endswith("/"):
        raise _parse_error("Malformed CC-CEDICT definition", line_number)

    body = definitions[1:-1]
    senses: list[tuple[str, ...]] = []
    for raw_sense in body.split("/"):
        sense = raw_sense.strip()
        if not sense:
            continue
        glosses = tuple(gloss.strip() for gloss in sense.split(";") if gloss.strip())
        if not glosses:
            raise _parse_error("Empty CC-CEDICT sense", line_number)
        senses.append(glosses)

    if not senses:
        raise _parse_error("Empty CC-CEDICT definition", line_number)
    return tuple(senses)


def _parse_error(message: str, line_number: int | None) -> CcCedictParseError:
    if line_number is None:
        return CcCedictParseError(message)
    return CcCedictParseError(f"{message} on line {line_number}")
