"""Persisted BM25 index persistence and ranking."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from moku_core.indexing.types import WeightedQueryTerm
from sqlalchemy import Float, String, and_, column, delete, func, insert, literal, select, values
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.persistence.models import (
    BM25CorpusDocument,
    BM25CorpusTerm,
    BM25IndexLevel,
    BM25IndexPosting,
    BM25IndexTerm,
    Corpus,
    Sentence,
)

BM25_ALGORITHM_VERSION = "bm25_v1"
BM25_PRESET_TOP_K_ALLOWED_WORDS = (500, 1_000, 2_000, 5_000, 8_000, 10_000, 15_000, 20_000, 0)


@dataclass(frozen=True)
class BM25RankedDocument:
    document_id: str
    sentence: str
    content_tokens: tuple[str, ...]
    bm25_rank: int
    bm25_score: float


class BM25IndexRepository:
    _BATCH_SIZE = 10_000

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rebuild_all_presets(self, corpus: Corpus) -> None:
        await self.rebuild_corpus_terms(corpus, delete_levels=True)
        for top_k_allowed_words in BM25_PRESET_TOP_K_ALLOWED_WORDS:
            await self.rebuild_level(corpus, top_k_allowed_words)

    async def rebuild_corpus_terms(self, corpus: Corpus, *, delete_levels: bool = True) -> None:
        if delete_levels:
            await self.session.execute(
                delete(BM25IndexLevel).where(
                    BM25IndexLevel.corpus_id == corpus.id,
                    BM25IndexLevel.algorithm_version == BM25_ALGORITHM_VERSION,
                )
            )
        await self.session.execute(
            delete(BM25CorpusTerm).where(BM25CorpusTerm.corpus_id == corpus.id)
        )
        await self.session.execute(
            delete(BM25CorpusDocument).where(BM25CorpusDocument.corpus_id == corpus.id)
        )

        result = await self.session.execute(
            select(Sentence.id, Sentence.content_tokens)
            .where(Sentence.corpus_id == corpus.id)
            .order_by(Sentence.id)
        )
        document_rows: list[dict[str, Any]] = []
        term_rows: list[dict[str, Any]] = []
        for sentence_id, content_tokens in result.all():
            term_frequencies = Counter(content_tokens)
            document_rows.append(
                {
                    "corpus_id": corpus.id,
                    "sentence_id": sentence_id,
                    "document_length": float(sum(term_frequencies.values())),
                }
            )
            for term, term_frequency in term_frequencies.items():
                term_rows.append(
                    {
                        "corpus_id": corpus.id,
                        "sentence_id": sentence_id,
                        "term": term,
                        "term_frequency": int(term_frequency),
                    }
                )

        await self._insert_batches(BM25CorpusDocument, document_rows)
        await self._insert_batches(BM25CorpusTerm, term_rows)
        await self.session.flush()

    async def rebuild_level(self, corpus: Corpus, top_k_allowed_words: int) -> BM25IndexLevel:
        await self.session.execute(
            delete(BM25IndexLevel).where(
                BM25IndexLevel.corpus_id == corpus.id,
                BM25IndexLevel.top_k_allowed_words == top_k_allowed_words,
                BM25IndexLevel.algorithm_version == BM25_ALGORITHM_VERSION,
            )
        )

        document_statement = (
            select(BM25CorpusDocument.document_length)
            .join(Sentence, Sentence.id == BM25CorpusDocument.sentence_id)
            .where(BM25CorpusDocument.corpus_id == corpus.id)
        )
        if top_k_allowed_words > 0:
            document_statement = document_statement.where(
                Sentence.max_content_word_rank <= top_k_allowed_words
            )
        document_lengths = list((await self.session.execute(document_statement)).scalars().all())
        document_count = len(document_lengths)
        average_document_length = (
            sum(document_lengths) / document_count if document_count else 1.0
        )

        level = BM25IndexLevel(
            corpus_id=corpus.id,
            top_k_allowed_words=top_k_allowed_words,
            algorithm_version=BM25_ALGORITHM_VERSION,
            document_count=document_count,
            average_document_length=average_document_length,
        )
        self.session.add(level)
        await self.session.flush()

        if document_count == 0:
            return level

        frequency_statement = (
            select(BM25CorpusTerm.term, func.count(BM25CorpusTerm.sentence_id))
            .join(Sentence, Sentence.id == BM25CorpusTerm.sentence_id)
            .where(BM25CorpusTerm.corpus_id == corpus.id)
            .group_by(BM25CorpusTerm.term)
        )
        if top_k_allowed_words > 0:
            frequency_statement = frequency_statement.where(
                Sentence.max_content_word_rank <= top_k_allowed_words
            )
        frequency_rows = (await self.session.execute(frequency_statement)).all()
        index_term_rows = [
            {
                "index_level_id": level.id,
                "term": term,
                "document_frequency": int(document_frequency),
                "idf": math.log(
                    1
                    + (document_count - int(document_frequency) + 0.5)
                    / (int(document_frequency) + 0.5)
                ),
            }
            for term, document_frequency in frequency_rows
        ]
        await self._insert_batches(BM25IndexTerm, index_term_rows)
        await self._insert_level_postings(corpus, level, top_k_allowed_words)
        await self.session.flush()
        return level

    async def ensure_preset_level(
        self, corpus: Corpus, top_k_allowed_words: int
    ) -> BM25IndexLevel:
        if not is_preset_top_k_allowed_words(top_k_allowed_words):
            raise ValueError(f"Not a BM25 preset top-k level: {top_k_allowed_words}")

        level = await self._get_level(corpus, top_k_allowed_words)
        if level is not None:
            if level.document_count == 0 or await self._has_level_postings(level):
                return level
            return await self.rebuild_level(corpus, top_k_allowed_words)

        has_documents = await self._has_corpus_documents(corpus)
        if not has_documents:
            await self.rebuild_corpus_terms(corpus, delete_levels=False)
        return await self.rebuild_level(corpus, top_k_allowed_words)

    async def _insert_level_postings(
        self,
        corpus: Corpus,
        level: BM25IndexLevel,
        top_k_allowed_words: int,
    ) -> None:
        posting_select = (
            select(
                literal(level.id),
                BM25CorpusTerm.sentence_id,
                BM25CorpusTerm.term,
                BM25CorpusTerm.term_frequency,
                BM25CorpusDocument.document_length,
                BM25IndexTerm.idf,
            )
            .join(
                BM25CorpusDocument,
                BM25CorpusDocument.sentence_id == BM25CorpusTerm.sentence_id,
            )
            .join(
                BM25IndexTerm,
                and_(
                    BM25IndexTerm.index_level_id == level.id,
                    BM25IndexTerm.term == BM25CorpusTerm.term,
                ),
            )
            .where(BM25CorpusTerm.corpus_id == corpus.id)
        )
        if top_k_allowed_words > 0:
            posting_select = posting_select.join(
                Sentence, Sentence.id == BM25CorpusTerm.sentence_id
            ).where(Sentence.max_content_word_rank <= top_k_allowed_words)

        await self.session.execute(
            insert(BM25IndexPosting).from_select(
                [
                    "index_level_id",
                    "sentence_id",
                    "term",
                    "term_frequency",
                    "document_length",
                    "idf",
                ],
                posting_select,
            )
        )

    async def _has_level_postings(self, level: BM25IndexLevel) -> bool:
        result = await self.session.execute(
            select(BM25IndexPosting.id)
            .where(BM25IndexPosting.index_level_id == level.id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def rank_preset_candidates(
        self,
        *,
        corpus: Corpus,
        query_terms: Sequence[WeightedQueryTerm],
        top_k_allowed_words: int,
        candidate_count: int,
    ) -> list[BM25RankedDocument]:
        if not query_terms or candidate_count <= 0:
            return []

        level = await self.ensure_preset_level(corpus, top_k_allowed_words)
        if level.document_count == 0:
            return []

        query_terms_by_word = {query_term.word: query_term for query_term in query_terms}
        query_term_values = (
            values(
                column("term", String()),
                column("weight", Float()),
                column("days_factor", Float()),
                name="query_terms",
            )
            .data(
                [
                    (
                        query_term.word,
                        float(query_term.weight),
                        float(max(query_term.days_until_due, 0) + 1),
                    )
                    for query_term in query_terms_by_word.values()
                ]
            )
            .cte("query_terms")
        )

        average_length = level.average_document_length or 1.0
        k1 = 1.5
        b = 0.75
        length_norm = 1 - b + b * (BM25IndexPosting.document_length / average_length)
        denominator = (
            BM25IndexPosting.term_frequency
            + k1 * length_norm * query_term_values.c.days_factor
        )
        term_score = (
            query_term_values.c.weight
            * BM25IndexPosting.idf
            * ((k1 + 1) * BM25IndexPosting.term_frequency)
            / denominator
        )
        score_sum = func.sum(term_score)
        scored_statement = (
            select(
                BM25IndexPosting.sentence_id.label("sentence_id"),
                score_sum.label("score"),
            )
            .select_from(query_term_values)
            .join(
                BM25IndexPosting,
                and_(
                    BM25IndexPosting.index_level_id == level.id,
                    BM25IndexPosting.term == query_term_values.c.term,
                ),
            )
            .group_by(BM25IndexPosting.sentence_id)
            .having(score_sum > 0)
            .order_by(score_sum.desc(), BM25IndexPosting.sentence_id.asc())
            .limit(candidate_count)
        )

        scored_documents = scored_statement.cte("scored_documents")
        statement = (
            select(
                Sentence.id,
                Sentence.public_id,
                Sentence.text,
                Sentence.content_tokens,
                scored_documents.c.score,
            )
            .join(scored_documents, scored_documents.c.sentence_id == Sentence.id)
            .order_by(scored_documents.c.score.desc(), Sentence.id.asc())
        )

        scored: dict[int, _ScoredDocument] = {}
        for sentence_id, public_id, text, content_tokens, score in (
            await self.session.execute(statement)
        ).all():
            scored[sentence_id] = _ScoredDocument(
                sentence_id=sentence_id,
                document_id=str(public_id),
                sentence=text,
                content_tokens=tuple(content_tokens),
                score=float(score),
            )

        ranked_documents = sorted(
            scored.values(),
            key=lambda document: (-document.score, document.sentence_id),
        )
        return [
            BM25RankedDocument(
                document_id=document.document_id,
                sentence=document.sentence,
                content_tokens=document.content_tokens,
                bm25_rank=rank,
                bm25_score=float(document.score),
            )
            for rank, document in enumerate(ranked_documents, start=1)
        ]

    async def _get_level(
        self, corpus: Corpus, top_k_allowed_words: int
    ) -> BM25IndexLevel | None:
        result = await self.session.execute(
            select(BM25IndexLevel).where(
                BM25IndexLevel.corpus_id == corpus.id,
                BM25IndexLevel.top_k_allowed_words == top_k_allowed_words,
                BM25IndexLevel.algorithm_version == BM25_ALGORITHM_VERSION,
            )
        )
        return result.scalar_one_or_none()

    async def _has_corpus_documents(self, corpus: Corpus) -> bool:
        result = await self.session.execute(
            select(BM25CorpusDocument.id)
            .where(BM25CorpusDocument.corpus_id == corpus.id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _insert_batches(self, model: type[Any], rows: list[dict[str, Any]]) -> None:
        for start in range(0, len(rows), self._BATCH_SIZE):
            await self.session.execute(insert(model), rows[start : start + self._BATCH_SIZE])


@dataclass
class _ScoredDocument:
    sentence_id: int
    document_id: str
    sentence: str
    content_tokens: tuple[str, ...]
    score: float


def is_preset_top_k_allowed_words(top_k_allowed_words: int) -> bool:
    return top_k_allowed_words in BM25_PRESET_TOP_K_ALLOWED_WORDS


def _weighted_bm25_term_score(
    *,
    term_frequency: int,
    document_length: float,
    average_document_length: float,
    idf: float,
    query_term: WeightedQueryTerm,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    days_factor = max(query_term.days_until_due, 0) + 1
    length_norm = 1 - b + b * (document_length / average_document_length)
    denominator = term_frequency + k1 * length_norm * days_factor
    return query_term.weight * idf * ((k1 + 1) * term_frequency) / denominator
