from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import zstandard as zstd
from moku_backend.services.anki_package_reader import (
    AnkiPackageReader,
    inspect_anki_package,
)


def test_reader_extracts_modern_zstd_package(tmp_path: Path) -> None:
    package_path = tmp_path / "modern.apkg"
    collection_path = tmp_path / "collection.anki21b"
    _write_modern_collection(collection_path)
    compressed = zstd.ZstdCompressor().compress(collection_path.read_bytes())
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("meta", b"\x08\x03")
        archive.writestr("collection.anki21b", compressed)

    package = AnkiPackageReader().read(package_path)

    assert package.collection_entry == "collection.anki21b"
    assert package.zstd_compressed is True
    assert [deck.name for deck in package.decks] == ["Parent::Child"]
    assert package.decks[0].card_count == 1
    assert package.fields[0].name == "Expression"
    assert package.notes[0].fields["Expression"] == "Casa"
    assert package.cards[0].fsrs_stability == 4.2
    assert package.cards[0].fsrs_difficulty == 5.1
    assert package.review_logs[0].ease == 3

    summary = inspect_anki_package(package_path)
    assert summary["card_count"] == 1
    assert summary["revlog_count"] == 1
    assert summary["cards_with_fsrs_stability"] == 1


def test_reader_extracts_legacy_uncompressed_package(tmp_path: Path) -> None:
    package_path = tmp_path / "legacy.apkg"
    collection_path = tmp_path / "collection.anki2"
    _write_legacy_collection(collection_path)
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("collection.anki2", collection_path.read_bytes())

    package = AnkiPackageReader().read(package_path)

    assert package.collection_entry == "collection.anki2"
    assert package.zstd_compressed is False
    assert [deck.name for deck in package.decks] == ["Legacy::Deck"]
    assert package.fields[0].notetype_name == "Legacy Basic"
    assert package.notes[0].fields["Front"] == "Ni hao"
    assert package.cards[0].card_data == {}


def _write_modern_collection(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            create table col (crt integer not null);
            create table decks (
                id integer primary key,
                name text not null,
                mtime_secs integer,
                usn integer,
                common blob,
                kind blob
            );
            create table notetypes (
                id integer primary key,
                name text not null,
                mtime_secs integer,
                usn integer,
                config blob
            );
            create table fields (
                ntid integer,
                ord integer,
                name text not null,
                config blob
            );
            create table notes (
                id integer primary key,
                guid text not null,
                mid integer not null,
                mod integer not null,
                usn integer,
                tags text not null,
                flds text not null,
                sfld integer,
                csum integer,
                flags integer,
                data text
            );
            create table cards (
                id integer primary key,
                nid integer not null,
                did integer not null,
                ord integer not null,
                mod integer not null,
                usn integer,
                type integer not null,
                queue integer not null,
                due integer not null,
                ivl integer not null,
                factor integer not null,
                reps integer not null,
                lapses integer not null,
                left integer not null,
                odue integer not null,
                odid integer not null,
                flags integer not null,
                data text not null
            );
            create table revlog (
                id integer primary key,
                cid integer not null,
                usn integer not null,
                ease integer not null,
                ivl integer not null,
                lastIvl integer not null,
                factor integer not null,
                time integer not null,
                type integer not null
            );
            """
        )
        connection.execute("insert into col values (?)", (1_700_000_000,))
        connection.execute(
            "insert into decks values (?, ?, 0, 0, x'', x'')",
            (2, "Parent\x1fChild"),
        )
        connection.execute(
            "insert into notetypes values (?, ?, 0, 0, x'')",
            (10, "Basic"),
        )
        connection.executemany(
            "insert into fields values (?, ?, ?, x'')",
            [(10, 0, "Expression"), (10, 1, "Meaning")],
        )
        connection.execute(
            "insert into notes values (?, ?, ?, ?, 0, ?, ?, 0, 0, 0, '')",
            (100, "guid", 10, 1_700_000_000, "", "Casa\x1fHouse"),
        )
        connection.execute(
            "insert into cards values (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                200,
                100,
                2,
                0,
                1_700_000_000,
                2,
                2,
                10,
                7,
                1000,
                3,
                0,
                0,
                0,
                0,
                0,
                json.dumps({"s": 4.2, "d": 5.1, "lrt": 1_700_000_000}),
            ),
        )
        connection.execute(
            "insert into revlog values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1_700_000_000_123, 200, 0, 3, 7, 3, 510, 1200, 1),
        )
        connection.commit()
    finally:
        connection.close()


def _write_legacy_collection(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            create table col (crt integer not null, decks text not null, models text not null);
            create table notes (
                id integer primary key,
                guid text not null,
                mid integer not null,
                mod integer not null,
                tags text not null,
                flds text not null
            );
            create table cards (
                id integer primary key,
                nid integer not null,
                did integer not null,
                ord integer not null,
                mod integer not null,
                type integer not null,
                queue integer not null,
                due integer not null,
                ivl integer not null,
                factor integer not null,
                reps integer not null,
                lapses integer not null,
                left integer not null,
                odue integer not null,
                odid integer not null,
                flags integer not null,
                data text not null
            );
            create table revlog (
                id integer primary key,
                cid integer not null,
                usn integer not null,
                ease integer not null,
                ivl integer not null,
                lastIvl integer not null,
                factor integer not null,
                time integer not null,
                type integer not null
            );
            """
        )
        decks = {"3": {"id": 3, "name": "Legacy::Deck"}}
        models = {
            "20": {
                "id": 20,
                "name": "Legacy Basic",
                "flds": [{"ord": 0, "name": "Front"}, {"ord": 1, "name": "Back"}],
            }
        }
        connection.execute(
            "insert into col values (?, ?, ?)",
            (1_700_000_000, json.dumps(decks), json.dumps(models)),
        )
        connection.execute(
            "insert into notes values (?, ?, ?, ?, ?, ?)",
            (101, "legacy-guid", 20, 1_700_000_000, "", "Ni hao\x1fHello"),
        )
        connection.execute(
            "insert into cards values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (201, 101, 3, 0, 1_700_000_000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ""),
        )
        connection.commit()
    finally:
        connection.close()
