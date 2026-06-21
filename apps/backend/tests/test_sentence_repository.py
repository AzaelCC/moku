from __future__ import annotations

from typing import Any

from moku_backend.persistence.models import Corpus, Sentence
from moku_backend.persistence.repositories.sentence_repository import SentenceRepository
from moku_core.corpus import CorpusSentence
from moku_core.corpus.utils import sentence_record
from sqlalchemy import UniqueConstraint


class FakeScalarResult:
    def __init__(self, values: set[str]) -> None:
        self.values = values

    def all(self) -> list[str]:
        return list(self.values)


class FakeResult:
    def __init__(
        self,
        values: set[str] | None = None,
        rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.rows = rows or []
        self.values = values

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.values or set())

    def all(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeSession:
    def __init__(self, existing_texts: set[str]) -> None:
        self.existing_texts = existing_texts
        self.added: list[Sentence] = []
        self.executed: list[Any] = []
        self.flush_count = 0

    async def execute(self, statement: Any) -> FakeResult:
        self.executed.append(statement)
        if len(self.executed) == 1:
            return FakeResult(set())
        return FakeResult(self.existing_texts)

    def add_all(self, sentences: list[Sentence]) -> None:
        self.added.extend(sentences)

    async def flush(self) -> None:
        self.flush_count += 1


def test_sentence_text_has_global_unique_constraint() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in Sentence.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints["uq_sentences_text"] == {"text"}
    assert "uq_sentences_corpus_text" not in unique_constraints


def test_sentence_has_corpus_rank_filter_index() -> None:
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in Sentence.__table__.indexes
    }

    assert indexes["ix_sentences_corpus_id_max_content_word_rank"] == {
        "corpus_id",
        "max_content_word_rank",
    }


async def test_replace_sentences_skips_text_existing_in_another_corpus() -> None:
    existing = sentence_record(
        text="The museum opened tonight.",
        source="sample",
        language="en",
    )
    fresh = sentence_record(
        text="Visitors waited outside.",
        source="sample",
        language="en",
    )
    repeated_input = sentence_record(
        text="The museum opened tonight.",
        source="sample",
        language="en",
    )
    corpus = Corpus(id=42, name="sample-en", source="sample", language="en")
    session = FakeSession(existing_texts={existing.text})
    repository = SentenceRepository(session)

    persisted = await repository.replace_sentences(
        corpus=corpus,
        sentences=[existing, fresh, repeated_input],
    )

    assert [sentence.text for sentence in persisted] == [fresh.text]
    assert [sentence.text for sentence in session.added] == [fresh.text]
    assert session.flush_count == 1


async def test_replace_sentences_persists_max_content_word_rank() -> None:
    corpus = Corpus(id=42, name="sample-en", source="sample", language="en")
    session = FakeSession(existing_texts=set())
    repository = SentenceRepository(session)
    sentences = [
        _corpus_sentence("Common phrase.", ("common", "phrase")),
        _corpus_sentence("Common rare.", ("common", "rare")),
        _corpus_sentence("Common common.", ("common", "common")),
        _corpus_sentence("Empty.", ()),
    ]

    await repository.replace_sentences(corpus=corpus, sentences=sentences)

    assert [
        sentence.max_content_word_rank for sentence in session.added
    ] == [2, 3, 1, 0]


async def test_list_documents_filters_by_max_content_word_rank() -> None:
    corpus = Corpus(id=42, name="sample-en", source="sample", language="en")
    session = FakeSession(existing_texts=set())
    repository = SentenceRepository(session)

    await repository.list_documents(corpus, top_k_allowed_words=2)

    assert "sentences.max_content_word_rank <= " in str(session.executed[0])


async def test_list_documents_top_k_zero_disables_rank_filter() -> None:
    corpus = Corpus(id=42, name="sample-en", source="sample", language="en")
    session = FakeSession(existing_texts=set())
    repository = SentenceRepository(session)

    await repository.list_documents(corpus, top_k_allowed_words=0)

    assert "max_content_word_rank" not in str(session.executed[0])


def _corpus_sentence(text: str, content_tokens: tuple[str, ...]) -> CorpusSentence:
    return CorpusSentence(
        source="sample",
        language="en",
        text=text,
        tokens=content_tokens,
        content_tokens=content_tokens,
    )
