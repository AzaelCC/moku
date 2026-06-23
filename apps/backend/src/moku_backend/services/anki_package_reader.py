"""Read Anki .apkg/.colpkg package data without importing it into Anki."""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import zstandard as zstd

ANKI_DECK_SEPARATOR = "\x1f"
ANKI_FIELD_SEPARATOR = "\x1f"
SQLITE_HEADER = b"SQLite format 3\x00"
COLLECTION_ENTRY_NAMES = ("collection.anki21b", "collection.anki21", "collection.anki2")


class AnkiPackageError(RuntimeError):
    """Raised when an Anki package cannot be read."""


@dataclass(frozen=True)
class AnkiPackageDeck:
    id: int
    name: str
    raw_name: str
    card_count: int


@dataclass(frozen=True)
class AnkiPackageField:
    notetype_id: int
    notetype_name: str
    ord: int
    name: str


@dataclass(frozen=True)
class AnkiPackageTemplate:
    notetype_id: int
    notetype_name: str
    ord: int
    name: str


@dataclass(frozen=True)
class AnkiPackageNote:
    id: int
    guid: str
    notetype_id: int
    notetype_name: str
    fields: dict[str, str]
    raw_fields: tuple[str, ...]
    tags: str
    mod: int


@dataclass(frozen=True)
class AnkiPackageCard:
    id: int
    note_id: int
    deck_id: int
    deck_name: str
    ord: int
    mod: int
    card_type: int
    queue: int
    due: int
    interval: int
    factor: int
    reps: int
    lapses: int
    left: int
    odue: int
    odid: int
    flags: int
    raw_data: str
    card_data: dict[str, object]

    @property
    def fsrs_stability(self) -> float | None:
        return _optional_float(self.card_data.get("s"))

    @property
    def fsrs_difficulty(self) -> float | None:
        return _optional_float(self.card_data.get("d"))


@dataclass(frozen=True)
class AnkiPackageReviewLog:
    id: int
    card_id: int
    usn: int
    ease: int
    interval: int
    last_interval: int
    factor: int
    duration_ms: int
    review_type: int


@dataclass(frozen=True)
class AnkiPackage:
    path: Path
    collection_entry: str
    zstd_compressed: bool
    created_at: datetime
    decks: list[AnkiPackageDeck]
    fields: list[AnkiPackageField]
    notes: list[AnkiPackageNote]
    cards: list[AnkiPackageCard]
    review_logs: list[AnkiPackageReviewLog]
    templates: list[AnkiPackageTemplate] = field(default_factory=list)
    notes_by_id: dict[int, AnkiPackageNote] = field(init=False)
    templates_by_notetype_ord: dict[tuple[int, int], AnkiPackageTemplate] = field(init=False)
    review_logs_by_card_id: dict[int, list[AnkiPackageReviewLog]] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes_by_id", {note.id: note for note in self.notes})
        object.__setattr__(
            self,
            "templates_by_notetype_ord",
            {(template.notetype_id, template.ord): template for template in self.templates},
        )
        logs_by_card: dict[int, list[AnkiPackageReviewLog]] = {}
        for review_log in self.review_logs:
            logs_by_card.setdefault(review_log.card_id, []).append(review_log)
        for logs in logs_by_card.values():
            logs.sort(key=lambda log: log.id)
        object.__setattr__(self, "review_logs_by_card_id", logs_by_card)


class AnkiPackageReader:
    """Extract and read the SQLite collection embedded in an Anki package."""

    def read(self, package_path: str | Path) -> AnkiPackage:
        path = Path(package_path)
        if not path.exists():
            raise AnkiPackageError(f"Anki package not found: {path}")

        collection_entry, db_bytes, compressed = _read_collection_bytes(path)
        with tempfile.NamedTemporaryFile(suffix=".anki2", delete=False) as temp_file:
            temp_file.write(db_bytes)
            temp_path = Path(temp_file.name)

        try:
            return self._read_sqlite_package(
                path=path,
                collection_entry=collection_entry,
                zstd_compressed=compressed,
                sqlite_path=temp_path,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def _read_sqlite_package(
        self,
        *,
        path: Path,
        collection_entry: str,
        zstd_compressed: bool,
        sqlite_path: Path,
    ) -> AnkiPackage:
        connection = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.create_collation("unicase", _unicase_compare)
        try:
            tables = _table_names(connection)
            if "cards" not in tables or "notes" not in tables or "revlog" not in tables:
                raise AnkiPackageError("Anki package collection is missing required tables.")

            created_at = _collection_created_at(connection)
            if {"decks", "notetypes", "fields"}.issubset(tables):
                (
                    decks,
                    fields,
                    templates,
                    field_names_by_notetype,
                    notetype_names,
                ) = _read_modern_metadata(
                    connection
                )
            else:
                (
                    decks,
                    fields,
                    templates,
                    field_names_by_notetype,
                    notetype_names,
                ) = _read_legacy_metadata(
                    connection
                )

            notes = _read_notes(connection, field_names_by_notetype, notetype_names)
            cards = _read_cards(connection, {deck.id: deck.name for deck in decks})
            review_logs = _read_review_logs(connection)
            decks = _with_card_counts(decks, cards)

            return AnkiPackage(
                path=path,
                collection_entry=collection_entry,
                zstd_compressed=zstd_compressed,
                created_at=created_at,
                decks=decks,
                fields=fields,
                notes=notes,
                cards=cards,
                review_logs=review_logs,
                templates=templates,
            )
        finally:
            connection.close()


def inspect_anki_package(package_path: str | Path) -> dict[str, object]:
    """Return a metadata-only summary suitable for CLI/script output."""

    package = AnkiPackageReader().read(package_path)
    data_key_samples: list[list[str]] = []
    cards_with_stability = 0
    cards_with_difficulty = 0
    cards_with_last_review_time = 0
    cards_with_nonempty_data = 0

    for card in package.cards:
        if card.raw_data:
            cards_with_nonempty_data += 1
        if card.card_data:
            keys = sorted(card.card_data)
            if keys and len(data_key_samples) < 5:
                data_key_samples.append(keys)
        cards_with_stability += int(card.fsrs_stability is not None)
        cards_with_difficulty += int(card.fsrs_difficulty is not None)
        cards_with_last_review_time += int(isinstance(card.card_data.get("lrt"), int))

    return {
        "package": str(package.path),
        "collection_entry": package.collection_entry,
        "zstd_compressed": package.zstd_compressed,
        "card_count": len(package.cards),
        "note_count": len(package.notes),
        "revlog_count": len(package.review_logs),
        "cards_with_nonempty_data": cards_with_nonempty_data,
        "cards_with_fsrs_stability": cards_with_stability,
        "cards_with_fsrs_difficulty": cards_with_difficulty,
        "cards_with_last_review_time": cards_with_last_review_time,
        "sample_card_data_keys": data_key_samples,
        "decks": [
            {"id": deck.id, "name": deck.name, "card_count": deck.card_count}
            for deck in package.decks
        ],
        "fields": [
            {
                "notetype": field.notetype_name,
                "ord": field.ord,
                "name": field.name,
            }
            for field in package.fields
        ],
        "templates": [
            {
                "notetype": template.notetype_name,
                "ord": template.ord,
                "name": template.name,
            }
            for template in package.templates
        ],
    }


def _read_collection_bytes(package_path: Path) -> tuple[str, bytes, bool]:
    try:
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            collection_entry = next(
                (name for name in COLLECTION_ENTRY_NAMES if name in names),
                None,
            )
            if collection_entry is None:
                raise AnkiPackageError(
                    "Anki package does not contain a supported collection entry."
                )
            raw_collection = archive.read(collection_entry)
    except zipfile.BadZipFile as exc:
        raise AnkiPackageError(f"Anki package is not a valid zip file: {package_path}") from exc

    if raw_collection.startswith(SQLITE_HEADER):
        return collection_entry, raw_collection, False

    with zstd.ZstdDecompressor().stream_reader(io.BytesIO(raw_collection)) as reader:
        return collection_entry, reader.read(), True


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute("select name from sqlite_master where type = 'table'")
    }


def _collection_created_at(connection: sqlite3.Connection) -> datetime:
    row = connection.execute("select crt from col limit 1").fetchone()
    if row is None:
        return datetime.fromtimestamp(0, UTC)
    return datetime.fromtimestamp(int(row["crt"]), UTC)


def _read_modern_metadata(
    connection: sqlite3.Connection,
) -> tuple[
    list[AnkiPackageDeck],
    list[AnkiPackageField],
    list[AnkiPackageTemplate],
    dict[int, list[str]],
    dict[int, str],
]:
    notetype_names = {
        int(row["id"]): str(row["name"])
        for row in connection.execute("select id, name from notetypes")
    }
    decks = [
        AnkiPackageDeck(
            id=int(row["id"]),
            raw_name=str(row["name"]),
            name=normalize_deck_name(str(row["name"])),
            card_count=0,
        )
        for row in connection.execute("select id, name from decks")
    ]

    fields: list[AnkiPackageField] = []
    field_names_by_notetype: dict[int, list[str]] = {}
    for row in connection.execute("select ntid, ord, name from fields order by ntid, ord"):
        notetype_id = int(row["ntid"])
        name = str(row["name"])
        field_names_by_notetype.setdefault(notetype_id, []).append(name)
        fields.append(
            AnkiPackageField(
                notetype_id=notetype_id,
                notetype_name=notetype_names.get(notetype_id, str(notetype_id)),
                ord=int(row["ord"]),
                name=name,
            )
        )

    templates = _read_modern_templates(connection, notetype_names)

    return decks, fields, templates, field_names_by_notetype, notetype_names


def _read_legacy_metadata(
    connection: sqlite3.Connection,
) -> tuple[
    list[AnkiPackageDeck],
    list[AnkiPackageField],
    list[AnkiPackageTemplate],
    dict[int, list[str]],
    dict[int, str],
]:
    row = connection.execute("select decks, models from col limit 1").fetchone()
    if row is None:
        raise AnkiPackageError("Anki package collection has no col metadata row.")

    raw_decks = _json_object(row["decks"])
    raw_models = _json_object(row["models"])
    decks = [
        AnkiPackageDeck(
            id=int(deck["id"]),
            raw_name=str(deck["name"]),
            name=normalize_deck_name(str(deck["name"])),
            card_count=0,
        )
        for deck in raw_decks.values()
        if isinstance(deck, dict) and "id" in deck and "name" in deck
    ]

    fields: list[AnkiPackageField] = []
    templates: list[AnkiPackageTemplate] = []
    field_names_by_notetype: dict[int, list[str]] = {}
    notetype_names: dict[int, str] = {}
    for model in raw_models.values():
        if not isinstance(model, dict) or "id" not in model:
            continue
        notetype_id = int(model["id"])
        notetype_name = str(model.get("name", notetype_id))
        notetype_names[notetype_id] = notetype_name
        field_names: list[str] = []
        for model_field in sorted(
            model.get("flds", []),
            key=lambda item: int(item.get("ord", 0)),
        ):
            if not isinstance(model_field, dict):
                continue
            field_name = str(model_field.get("name", ""))
            ord_value = int(model_field.get("ord", len(field_names)))
            field_names.append(field_name)
            fields.append(
                AnkiPackageField(
                    notetype_id=notetype_id,
                    notetype_name=notetype_name,
                    ord=ord_value,
                    name=field_name,
                )
            )
        field_names_by_notetype[notetype_id] = field_names
        for template in sorted(
            model.get("tmpls", []),
            key=lambda item: int(item.get("ord", 0)),
        ):
            if not isinstance(template, dict):
                continue
            templates.append(
                AnkiPackageTemplate(
                    notetype_id=notetype_id,
                    notetype_name=notetype_name,
                    ord=int(template.get("ord", 0)),
                    name=str(template.get("name", "")),
                )
            )

    return decks, fields, templates, field_names_by_notetype, notetype_names


def _read_modern_templates(
    connection: sqlite3.Connection,
    notetype_names: dict[int, str],
) -> list[AnkiPackageTemplate]:
    if "templates" not in _table_names(connection):
        return []
    try:
        rows = connection.execute("select ntid, ord, name from templates order by ntid, ord")
    except sqlite3.OperationalError:
        return []
    return [
        AnkiPackageTemplate(
            notetype_id=int(row["ntid"]),
            notetype_name=notetype_names.get(int(row["ntid"]), str(row["ntid"])),
            ord=int(row["ord"]),
            name=str(row["name"]),
        )
        for row in rows
    ]


def _read_notes(
    connection: sqlite3.Connection,
    field_names_by_notetype: dict[int, list[str]],
    notetype_names: dict[int, str],
) -> list[AnkiPackageNote]:
    notes: list[AnkiPackageNote] = []
    for row in connection.execute("select id, guid, mid, mod, tags, flds from notes"):
        notetype_id = int(row["mid"])
        raw_fields = tuple(str(row["flds"]).split(ANKI_FIELD_SEPARATOR))
        field_names = field_names_by_notetype.get(notetype_id, ())
        fields = {
            name: raw_fields[index] if index < len(raw_fields) else ""
            for index, name in enumerate(field_names)
        }
        notes.append(
            AnkiPackageNote(
                id=int(row["id"]),
                guid=str(row["guid"]),
                notetype_id=notetype_id,
                notetype_name=notetype_names.get(notetype_id, str(notetype_id)),
                fields=fields,
                raw_fields=raw_fields,
                tags=str(row["tags"]),
                mod=int(row["mod"]),
            )
        )
    return notes


def _read_cards(
    connection: sqlite3.Connection,
    deck_names_by_id: dict[int, str],
) -> list[AnkiPackageCard]:
    cards: list[AnkiPackageCard] = []
    for row in connection.execute(
        "select id, nid, did, ord, mod, type, queue, due, ivl, factor, reps, "
        "lapses, left, odue, odid, flags, data from cards"
    ):
        raw_data = str(row["data"] or "")
        cards.append(
            AnkiPackageCard(
                id=int(row["id"]),
                note_id=int(row["nid"]),
                deck_id=int(row["did"]),
                deck_name=deck_names_by_id.get(int(row["did"]), str(row["did"])),
                ord=int(row["ord"]),
                mod=int(row["mod"]),
                card_type=int(row["type"]),
                queue=int(row["queue"]),
                due=int(row["due"]),
                interval=int(row["ivl"]),
                factor=int(row["factor"]),
                reps=int(row["reps"]),
                lapses=int(row["lapses"]),
                left=int(row["left"]),
                odue=int(row["odue"]),
                odid=int(row["odid"]),
                flags=int(row["flags"]),
                raw_data=raw_data,
                card_data=_json_object(raw_data),
            )
        )
    return cards


def _read_review_logs(connection: sqlite3.Connection) -> list[AnkiPackageReviewLog]:
    return [
        AnkiPackageReviewLog(
            id=int(row["id"]),
            card_id=int(row["cid"]),
            usn=int(row["usn"]),
            ease=int(row["ease"]),
            interval=int(row["ivl"]),
            last_interval=int(row["lastIvl"]),
            factor=int(row["factor"]),
            duration_ms=int(row["time"]),
            review_type=int(row["type"]),
        )
        for row in connection.execute(
            'select id, cid, usn, ease, ivl, "lastIvl", factor, time, type from revlog'
        )
    ]


def _with_card_counts(
    decks: list[AnkiPackageDeck],
    cards: list[AnkiPackageCard],
) -> list[AnkiPackageDeck]:
    counts = Counter(card.deck_id for card in cards)
    return [
        AnkiPackageDeck(
            id=deck.id,
            name=deck.name,
            raw_name=deck.raw_name,
            card_count=counts[deck.id],
        )
        for deck in decks
    ]


def normalize_deck_name(value: str) -> str:
    return value.replace(ANKI_DECK_SEPARATOR, "::")


def _json_object(value: Any) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _unicase_compare(left: str, right: str) -> int:
    left_folded = left.casefold()
    right_folded = right.casefold()
    return (left_folded > right_folded) - (left_folded < right_folded)
