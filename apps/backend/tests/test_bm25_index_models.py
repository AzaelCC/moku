from __future__ import annotations

from moku_backend.persistence.models import (
    BM25CorpusDocument,
    BM25CorpusTerm,
    BM25IndexLevel,
    BM25IndexPosting,
    BM25IndexTerm,
)
from sqlalchemy import UniqueConstraint


def test_bm25_document_has_sentence_unique_constraint_and_corpus_index() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in BM25CorpusDocument.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in BM25CorpusDocument.__table__.indexes
    }
    index_by_name = {index.name: index for index in BM25CorpusDocument.__table__.indexes}

    assert unique_constraints["uq_bm25_corpus_documents_sentence_id"] == {"sentence_id"}
    assert indexes["ix_bm25_corpus_documents_corpus_id"] == {"corpus_id"}
    assert indexes["ix_bm25_corpus_documents_sentence_id_cover"] == {"sentence_id"}
    assert _postgresql_include(
        index_by_name["ix_bm25_corpus_documents_sentence_id_cover"]
    ) == {"document_length"}


def test_bm25_corpus_terms_have_sentence_term_constraint_and_lookup_indexes() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in BM25CorpusTerm.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in BM25CorpusTerm.__table__.indexes
    }
    index_by_name = {index.name: index for index in BM25CorpusTerm.__table__.indexes}

    assert unique_constraints["uq_bm25_corpus_terms_sentence_term"] == {"sentence_id", "term"}
    assert indexes["ix_bm25_corpus_terms_corpus_id_term"] == {
        "corpus_id",
        "term",
        "sentence_id",
    }
    assert _postgresql_include(index_by_name["ix_bm25_corpus_terms_corpus_id_term"]) == {
        "term_frequency"
    }
    assert indexes["ix_bm25_corpus_terms_sentence_id"] == {"sentence_id"}


def test_bm25_index_levels_are_unique_per_corpus_top_k_algorithm() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in BM25IndexLevel.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in BM25IndexLevel.__table__.indexes
    }

    assert unique_constraints["uq_bm25_index_levels_corpus_top_k_algorithm"] == {
        "corpus_id",
        "top_k_allowed_words",
        "algorithm_version",
    }
    assert indexes["ix_bm25_index_levels_corpus_id_top_k"] == {
        "corpus_id",
        "top_k_allowed_words",
    }


def test_bm25_index_terms_are_unique_per_level_term() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in BM25IndexTerm.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in BM25IndexTerm.__table__.indexes
    }
    index_by_name = {index.name: index for index in BM25IndexTerm.__table__.indexes}

    assert unique_constraints["uq_bm25_index_terms_level_term"] == {"index_level_id", "term"}
    assert indexes["ix_bm25_index_terms_level_term"] == {"index_level_id", "term"}
    assert _postgresql_include(index_by_name["ix_bm25_index_terms_level_term"]) == {"idf"}


def test_bm25_index_postings_have_covering_lookup_index() -> None:
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in BM25IndexPosting.__table__.indexes
    }
    index_by_name = {index.name: index for index in BM25IndexPosting.__table__.indexes}

    assert indexes["ix_bm25_index_postings_level_term_sentence"] == {
        "index_level_id",
        "term",
        "sentence_id",
    }
    assert index_by_name["ix_bm25_index_postings_level_term_sentence"].unique is True
    assert _postgresql_include(
        index_by_name["ix_bm25_index_postings_level_term_sentence"]
    ) == {
        "term_frequency",
        "document_length",
        "idf",
    }


def _postgresql_include(index: object) -> set[str]:
    return set(index.dialect_options["postgresql"]["include"] or [])
