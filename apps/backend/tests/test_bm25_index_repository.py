from __future__ import annotations

from collections import Counter
from uuid import uuid4

import pytest
from moku_backend.persistence.models import BM25IndexLevel, Corpus
from moku_backend.persistence.repositories.bm25_index_repository import (
    BM25_ALGORITHM_VERSION,
    BM25IndexRepository,
)
from moku_core.indexing import BM25Document, build_bm25_index, weighted_bm25_scores
from moku_core.retrieval import ScheduleItem, due_query_terms


async def test_rebuild_level_matches_core_bm25_filtered_statistics() -> None:
    documents = [
        _FakeSentence(1, "Archive common.", ("archive", "common"), 2),
        _FakeSentence(2, "Archive rare.", ("archive", "rare"), 3),
        _FakeSentence(3, "Archive common common.", ("archive", "common", "common"), 2),
    ]
    session = _FakeRebuildSession(documents)
    repository = BM25IndexRepository(session)

    level = await repository.rebuild_level(
        Corpus(id=42, name="sample", source="sample", language="en"), 2
    )

    expected_documents = [
        BM25Document(str(document.id), document.text, document.content_tokens)
        for document in documents
        if document.max_content_word_rank <= 2
    ]
    expected_index = build_bm25_index(expected_documents)
    inserted_terms = {row["term"]: row for row in session.inserted_index_terms}
    inserted_postings = {
        (row["sentence_id"], row["term"]): row for row in session.inserted_index_postings
    }

    assert level.document_count == len(expected_documents)
    assert level.average_document_length == expected_index.average_document_length
    assert {
        term: row["document_frequency"] for term, row in inserted_terms.items()
    } == expected_index.document_frequencies
    assert inserted_terms["archive"]["idf"] == pytest.approx(expected_index.idf["archive"])
    assert inserted_terms["common"]["idf"] == pytest.approx(expected_index.idf["common"])
    assert set(inserted_postings) == {
        (1, "archive"),
        (1, "common"),
        (3, "archive"),
        (3, "common"),
    }
    assert inserted_postings[(1, "archive")]["term_frequency"] == 1
    assert inserted_postings[(3, "common")]["term_frequency"] == 2
    assert inserted_postings[(3, "common")]["document_length"] == 3.0
    assert inserted_postings[(3, "common")]["idf"] == pytest.approx(expected_index.idf["common"])


async def test_rank_preset_candidates_matches_core_bm25_scores() -> None:
    public_ids = [uuid4(), uuid4(), uuid4()]
    documents = [
        _FakeSentence(1, "Archive common.", ("archive", "common"), 2, public_ids[0]),
        _FakeSentence(2, "Archive rare.", ("archive", "rare"), 600, public_ids[1]),
        _FakeSentence(
            3, "Archive common common.", ("archive", "common", "common"), 2, public_ids[2]
        ),
    ]
    core_documents = [
        BM25Document(str(document.public_id), document.text, document.content_tokens)
        for document in documents
        if document.max_content_word_rank <= 500
    ]
    core_index = build_bm25_index(core_documents)
    query_terms = due_query_terms([ScheduleItem("archive", 0, 7)])
    expected_scores = weighted_bm25_scores(core_index, query_terms)
    level = BM25IndexLevel(
        id=7,
        corpus_id=42,
        top_k_allowed_words=500,
        algorithm_version=BM25_ALGORITHM_VERSION,
        document_count=len(core_documents),
        average_document_length=core_index.average_document_length,
    )
    session = _FakeRankSession(documents, core_index.idf, level)
    repository = BM25IndexRepository(session)

    ranked = await repository.rank_preset_candidates(
        corpus=Corpus(id=42, name="sample", source="sample", language="en"),
        query_terms=query_terms,
        top_k_allowed_words=500,
        candidate_count=5,
    )

    assert [document.document_id for document in ranked] == [
        core_documents[index].identifier
        for index in sorted(
            range(len(expected_scores)),
            key=lambda index: expected_scores[index],
            reverse=True,
        )
        if expected_scores[index] > 0
    ]
    assert [document.bm25_score for document in ranked] == pytest.approx(
        [score for score in sorted(expected_scores, reverse=True) if score > 0]
    )


async def test_ensure_preset_level_lazily_rebuilds_missing_index() -> None:
    repository = _TrackingBM25IndexRepository()
    corpus = Corpus(id=42, name="sample", source="sample", language="en")

    level = await repository.ensure_preset_level(corpus, 500)

    assert level.top_k_allowed_words == 500
    assert repository.rebuilt_corpus_terms is True
    assert repository.rebuilt_level == 500


async def test_ensure_preset_level_rebuilds_existing_level_without_postings() -> None:
    repository = _MissingPostingsBM25IndexRepository()
    corpus = Corpus(id=42, name="sample", source="sample", language="en")

    level = await repository.ensure_preset_level(corpus, 500)

    assert level.id == 100
    assert repository.rebuilt_level == 500


class _FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _FakeResult:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        scalars: list[object] | None = None,
        scalar: object | None = None,
    ) -> None:
        self.rows = rows or []
        self.scalar_values = scalars or []
        self.scalar_value = scalar

    def all(self) -> list[tuple[object, ...]]:
        return self.rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self.scalar_values)

    def scalar_one_or_none(self) -> object | None:
        return self.scalar_value


class _FakeSentence:
    def __init__(
        self,
        sentence_id: int,
        text: str,
        content_tokens: tuple[str, ...],
        max_content_word_rank: int,
        public_id: object | None = None,
    ) -> None:
        self.id = sentence_id
        self.public_id = public_id or uuid4()
        self.text = text
        self.content_tokens = content_tokens
        self.max_content_word_rank = max_content_word_rank


class _FakeRebuildSession:
    def __init__(self, documents: list[_FakeSentence]) -> None:
        self.documents = documents
        self.inserted_index_terms: list[dict[str, object]] = []
        self.inserted_index_postings: list[dict[str, object]] = []

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
        table = getattr(statement, "table", None)
        if getattr(table, "name", None) == "bm25_index_terms":
            self.inserted_index_terms.extend(params)
            return _FakeResult()
        if getattr(table, "name", None) == "bm25_index_postings":
            top_k_allowed_words = _top_k_allowed_words(statement)
            idf_by_term = {
                str(row["term"]): float(row["idf"]) for row in self.inserted_index_terms
            }
            for document in self._eligible_documents(top_k_allowed_words):
                term_frequencies = Counter(document.content_tokens)
                for term, term_frequency in term_frequencies.items():
                    self.inserted_index_postings.append(
                        {
                            "index_level_id": 99,
                            "sentence_id": document.id,
                            "term": term,
                            "term_frequency": int(term_frequency),
                            "document_length": float(len(document.content_tokens)),
                            "idf": idf_by_term[term],
                        }
                    )
            return _FakeResult()

        statement_text = str(statement)
        top_k_allowed_words = _top_k_allowed_words(statement)
        if statement_text.startswith("DELETE FROM bm25_index_levels"):
            return _FakeResult()
        if "SELECT bm25_corpus_documents.document_length" in statement_text:
            return _FakeResult(
                scalars=[
                    float(len(document.content_tokens))
                    for document in self._eligible_documents(top_k_allowed_words)
                ]
            )
        if "count(bm25_corpus_terms.sentence_id)" in statement_text:
            document_frequencies = Counter()
            for document in self._eligible_documents(top_k_allowed_words):
                document_frequencies.update(set(document.content_tokens))
            return _FakeResult(rows=list(document_frequencies.items()))
        raise AssertionError(f"Unexpected statement: {statement_text}")

    def add(self, level: BM25IndexLevel) -> None:
        level.id = 99

    async def flush(self) -> None:
        pass

    def _eligible_documents(self, top_k_allowed_words: int | None) -> list[_FakeSentence]:
        if top_k_allowed_words is None or top_k_allowed_words <= 0:
            return self.documents
        return [
            document
            for document in self.documents
            if document.max_content_word_rank <= top_k_allowed_words
        ]


class _FakeRankSession:
    def __init__(
        self,
        documents: list[_FakeSentence],
        idf: dict[str, float],
        level: BM25IndexLevel,
    ) -> None:
        self.documents = documents
        self.idf = idf
        self.level = level

    async def execute(self, statement: object) -> _FakeResult:
        statement_text = str(statement)
        if "FROM bm25_index_levels" in statement_text:
            return _FakeResult(scalar=self.level)
        if "SELECT bm25_index_postings.id" in statement_text:
            return _FakeResult(scalar=1)
        if "scored_documents" in statement_text and "bm25_index_postings" in statement_text:
            query_terms = _query_terms(statement)
            rows = []
            for document in self._eligible_documents(self.level.top_k_allowed_words):
                term_frequencies = Counter(document.content_tokens)
                score = 0.0
                for term, weight, days_factor in query_terms:
                    idf = self.idf.get(term)
                    if idf is None or term not in term_frequencies:
                        continue
                    term_frequency = term_frequencies[term]
                    length_norm = 1 - 0.75 + 0.75 * (
                        len(document.content_tokens) / self.level.average_document_length
                    )
                    denominator = term_frequency + 1.5 * length_norm * days_factor
                    score += weight * idf * ((1.5 + 1) * term_frequency) / denominator
                if score > 0:
                    rows.append(
                        (
                            document.id,
                            document.public_id,
                            document.text,
                            list(document.content_tokens),
                            score,
                        )
                    )
            return _FakeResult(
                rows=sorted(rows, key=lambda row: (-float(row[4]), int(row[0])))
            )
        raise AssertionError(f"Unexpected statement: {statement_text}")

    def _eligible_documents(self, top_k_allowed_words: int | None) -> list[_FakeSentence]:
        if top_k_allowed_words is None or top_k_allowed_words <= 0:
            return self.documents
        return [
            document
            for document in self.documents
            if document.max_content_word_rank <= top_k_allowed_words
        ]


class _TrackingBM25IndexRepository(BM25IndexRepository):
    def __init__(self) -> None:
        self.rebuilt_corpus_terms = False
        self.rebuilt_level: int | None = None

    async def _get_level(self, corpus: Corpus, top_k_allowed_words: int) -> BM25IndexLevel | None:
        return None

    async def _has_corpus_documents(self, corpus: Corpus) -> bool:
        return False

    async def rebuild_corpus_terms(self, corpus: Corpus, *, delete_levels: bool = True) -> None:
        self.rebuilt_corpus_terms = True

    async def rebuild_level(self, corpus: Corpus, top_k_allowed_words: int) -> BM25IndexLevel:
        self.rebuilt_level = top_k_allowed_words
        return BM25IndexLevel(
            corpus_id=corpus.id,
            top_k_allowed_words=top_k_allowed_words,
            algorithm_version=BM25_ALGORITHM_VERSION,
            document_count=0,
            average_document_length=1.0,
        )


class _MissingPostingsBM25IndexRepository(BM25IndexRepository):
    def __init__(self) -> None:
        self.rebuilt_level: int | None = None

    async def _get_level(self, corpus: Corpus, top_k_allowed_words: int) -> BM25IndexLevel | None:
        return BM25IndexLevel(
            id=99,
            corpus_id=corpus.id,
            top_k_allowed_words=top_k_allowed_words,
            algorithm_version=BM25_ALGORITHM_VERSION,
            document_count=1,
            average_document_length=1.0,
        )

    async def _has_level_postings(self, level: BM25IndexLevel) -> bool:
        return False

    async def rebuild_level(self, corpus: Corpus, top_k_allowed_words: int) -> BM25IndexLevel:
        self.rebuilt_level = top_k_allowed_words
        return BM25IndexLevel(
            id=100,
            corpus_id=corpus.id,
            top_k_allowed_words=top_k_allowed_words,
            algorithm_version=BM25_ALGORITHM_VERSION,
            document_count=1,
            average_document_length=1.0,
        )


def _top_k_allowed_words(statement: object) -> int | None:
    for key, value in statement.compile().params.items():
        if "max_content_word_rank" in key:
            return int(value)
    return None


def _query_terms(statement: object) -> tuple[tuple[str, float, float], ...]:
    values = list(statement.compile().params.values())
    query_terms: list[tuple[str, float, float]] = []
    index = 0
    while index <= len(values) - 3:
        term = values[index]
        weight = values[index + 1]
        days_factor = values[index + 2]
        if isinstance(term, str) and isinstance(weight, float) and isinstance(days_factor, float):
            query_terms.append((term, weight, days_factor))
            index += 3
            continue
        index += 1
    return tuple(query_terms)
