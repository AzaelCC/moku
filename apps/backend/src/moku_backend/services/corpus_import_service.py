"""Corpus import orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import cast

from moku_core.corpus import CorpusLoadConfig, CorpusSentence, iter_corpus_sentences
from moku_core.corpus.types import CorpusSource
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.repositories.import_repository import ImportRunRepository
from moku_backend.persistence.repositories.learner_repository import LearnerRepository
from moku_backend.persistence.repositories.sentence_repository import SentenceRepository


@dataclass(frozen=True)
class CorpusImportResult:
    run_public_id: str
    corpus_public_id: str
    corpus_name: str
    sentence_count: int
    seeded_learner_cards: int


class CorpusImportService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.import_runs = ImportRunRepository(session)
        self.learners = LearnerRepository(session)
        self.sentences = SentenceRepository(session)

    async def import_corpus(
        self,
        *,
        source: str,
        language: str,
        corpus_name: str | None = None,
        max_documents: int | None = None,
        max_sentences: int | None = None,
        split: str = "train",
        opensubtitles_language_pairs: tuple[str, ...] = (),
        seed_default_learner: bool | None = None,
    ) -> CorpusImportResult:
        normalized_source = self._normalize_source(source)
        corpus_name = corpus_name or f"{normalized_source}-{language}"
        if max_documents is None:
            max_documents = self.settings.import_max_documents
        if max_sentences is None:
            max_sentences = self.settings.import_max_sentences
        if seed_default_learner is None:
            should_seed = normalized_source == "sample"
        else:
            should_seed = seed_default_learner

        run = await self.import_runs.create_run(
            source=normalized_source,
            language=language,
            corpus_name=corpus_name,
            max_documents=max_documents,
            max_sentences=max_sentences,
            metadata={
                "split": split,
                "opensubtitles_language_pairs": list(opensubtitles_language_pairs),
            },
        )
        await self.session.commit()

        try:
            config = CorpusLoadConfig(
                source=cast(CorpusSource, normalized_source),
                language=language,
                split=split,
                max_documents=max_documents,
                max_sentences=max_sentences,
                min_sentence_tokens=self.settings.min_sentence_tokens,
                max_sentence_tokens=self.settings.max_sentence_tokens,
                opensubtitles_language_pairs=opensubtitles_language_pairs,
            )
            records = self._deduplicate(iter_corpus_sentences(config))
            corpus = await self.sentences.get_or_create_corpus(
                name=corpus_name,
                source=normalized_source,
                language=language,
            )
            persisted_records = await self.sentences.replace_sentences(
                corpus=corpus, sentences=records
            )

            seeded_cards = 0
            if should_seed:
                seeded_cards = await self._seed_default_learner(
                    persisted_records, language=language
                )

            await self.import_runs.mark_succeeded(run.id, len(persisted_records))
            await self.session.commit()
            return CorpusImportResult(
                run_public_id=str(run.public_id),
                corpus_public_id=str(corpus.public_id),
                corpus_name=corpus.name,
                sentence_count=len(persisted_records),
                seeded_learner_cards=seeded_cards,
            )
        except Exception as exc:
            await self.session.rollback()
            await self.import_runs.mark_failed(run.id, f"{type(exc).__name__}: {exc}")
            await self.session.commit()
            raise

    def _normalize_source(self, source: str) -> str:
        normalized_source = source.lower().strip()
        if normalized_source == "opensubtitles":
            normalized_source = "opensubtitles2024"
        if normalized_source not in {"sample", "wiki40b", "opensubtitles2024"}:
            raise ValueError(
                "Unsupported corpus source. Use sample, wiki40b, or opensubtitles2024."
            )
        return normalized_source

    def _deduplicate(self, records: object) -> list[CorpusSentence]:
        seen_texts = set()
        deduplicated = []
        for record in records:
            if not isinstance(record, CorpusSentence):
                raise TypeError(f"Expected CorpusSentence, got {type(record).__name__}")
            if record.text in seen_texts:
                continue
            seen_texts.add(record.text)
            deduplicated.append(record)
        return deduplicated

    async def _seed_default_learner(self, records: list[CorpusSentence], language: str) -> int:
        counts: Counter[str] = Counter()
        for record in records:
            counts.update(record.content_tokens)

        words = [word for word, _count in counts.most_common(36)]
        offsets = [-3, -2, -1, 0, 0, 1, 2, 3, 5, 8, 13, 21]
        intervals = [1, 2, 4, 7, 14, 30]
        card_specs = [
            (word, offsets[index % len(offsets)], intervals[index % len(intervals)])
            for index, word in enumerate(words)
        ]

        learner = await self.learners.get_or_create_default(self.settings.default_learner_handle)
        await self.learners.replace_cards(
            learner=learner,
            language=language,
            card_specs=card_specs,
            metadata={"source": "sample-seed"},
        )
        return len(card_specs)
