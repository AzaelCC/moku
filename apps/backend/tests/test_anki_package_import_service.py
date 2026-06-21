from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from moku_backend.config import Settings
from moku_backend.persistence.models import Learner
from moku_backend.persistence.repositories.learner_repository import LearnerCardSpec
from moku_backend.services.anki_package_import_service import (
    AnkiPackageImportError,
    AnkiPackageImportService,
)
from moku_backend.services.anki_package_reader import (
    AnkiPackage,
    AnkiPackageCard,
    AnkiPackageDeck,
    AnkiPackageNote,
    AnkiPackageReviewLog,
)


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeReader:
    def __init__(self, package: AnkiPackage) -> None:
        self.package = package

    def read(self, package_path: str | Path) -> AnkiPackage:
        return self.package


class FakeLearners:
    def __init__(self) -> None:
        self.learner = Learner(id=12, public_id=uuid4(), handle="default")
        self.language: str | None = None
        self.card_specs: list[LearnerCardSpec] = []

    async def get_or_create_default(self, handle: str) -> Learner:
        self.learner.handle = handle
        return self.learner

    async def replace_cards_for_language(
        self,
        *,
        learner: Learner,
        language: str,
        card_specs,
    ) -> None:
        self.language = language
        self.card_specs = list(card_specs)


async def test_package_import_persists_fsrs_state_and_revlogs(tmp_path: Path) -> None:
    package_path = tmp_path / "deck.apkg"
    package_path.write_bytes(b"placeholder")
    package = _package(package_path)
    session = FakeSession()
    service = AnkiPackageImportService(
        session,
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
        reader=FakeReader(package),
    )
    learners = FakeLearners()
    service.learners = learners

    result = await service.import_package(
        package_path=package_path,
        deck="Deck",
        word_field="Expression",
        language="zh-CN",
    )

    assert result.found_card_count == 2
    assert result.imported_card_count == 1
    assert result.duplicate_card_count == 1
    assert result.imported_review_log_count == 2
    assert result.fsrs_card_count == 1
    assert session.commit_count == 1
    assert learners.language == "zh-CN"

    spec = learners.card_specs[0]
    assert spec.word == "casa"
    assert spec.scheduling_algorithm == "anki"
    assert spec.fsrs_card is not None
    assert spec.fsrs_card["stability"] == 4.2
    assert spec.fsrs_card["difficulty"] == 5.1
    assert spec.review_logs[0].rating == "good"
    assert spec.review_logs[1].rating == "again"
    assert spec.metadata["source"] == "anki_package"
    assert spec.metadata["card_ids"] == [200, 201]


async def test_package_import_requires_scheduling_data(tmp_path: Path) -> None:
    package_path = tmp_path / "deck.apkg"
    package_path.write_bytes(b"placeholder")
    package = _package(package_path, include_scheduling=False)
    service = AnkiPackageImportService(
        FakeSession(),
        Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused"),
        reader=FakeReader(package),
    )

    with pytest.raises(AnkiPackageImportError, match="scheduling data"):
        await service.import_package(
            package_path=package_path,
            deck="Deck",
            word_field="Expression",
            language="zh-CN",
        )


def _package(path: Path, *, include_scheduling: bool = True) -> AnkiPackage:
    fsrs_data = {"s": 4.2, "d": 5.1, "lrt": 1_700_000_000} if include_scheduling else {}
    review_logs = (
        [
            AnkiPackageReviewLog(
                id=1_700_000_000_123,
                card_id=200,
                usn=0,
                ease=3,
                interval=7,
                last_interval=3,
                factor=510,
                duration_ms=1200,
                review_type=1,
            ),
            AnkiPackageReviewLog(
                id=1_700_000_100_123,
                card_id=201,
                usn=0,
                ease=1,
                interval=1,
                last_interval=7,
                factor=700,
                duration_ms=2400,
                review_type=2,
            ),
        ]
        if include_scheduling
        else []
    )
    return AnkiPackage(
        path=path,
        collection_entry="collection.anki21b",
        zstd_compressed=True,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        decks=[
            AnkiPackageDeck(id=1, name="Deck", raw_name="Deck", card_count=0),
            AnkiPackageDeck(id=2, name="Deck::Child", raw_name="Deck\x1fChild", card_count=2),
        ],
        fields=[],
        notes=[
            AnkiPackageNote(
                id=100,
                guid="guid-1",
                notetype_id=10,
                notetype_name="Basic",
                fields={"Expression": "Casa"},
                raw_fields=("Casa",),
                tags="",
                mod=1,
            ),
            AnkiPackageNote(
                id=101,
                guid="guid-2",
                notetype_id=10,
                notetype_name="Basic",
                fields={"Expression": "casa"},
                raw_fields=("casa",),
                tags="",
                mod=1,
            ),
        ],
        cards=[
            AnkiPackageCard(
                id=200,
                note_id=100,
                deck_id=2,
                deck_name="Deck::Child",
                ord=0,
                mod=1,
                card_type=2,
                queue=2,
                due=10,
                interval=7,
                factor=1000,
                reps=3,
                lapses=0,
                left=0,
                odue=0,
                odid=0,
                flags=0,
                raw_data="{}",
                card_data=fsrs_data,
            ),
            AnkiPackageCard(
                id=201,
                note_id=101,
                deck_id=2,
                deck_name="Deck::Child",
                ord=0,
                mod=1,
                card_type=2,
                queue=2,
                due=12,
                interval=8,
                factor=1000,
                reps=4,
                lapses=1,
                left=0,
                odue=0,
                odid=0,
                flags=0,
                raw_data="{}",
                card_data={},
            ),
        ],
        review_logs=review_logs,
    )
