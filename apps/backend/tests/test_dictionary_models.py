from __future__ import annotations

from moku_backend.persistence.models import (
    DictionaryEntry,
    DictionaryEntryTerm,
    DictionarySource,
)
from sqlalchemy import UniqueConstraint


def test_dictionary_source_has_language_source_uniqueness() -> None:
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in DictionarySource.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints["uq_dictionary_sources_source_language_definition"] == {
        "source_key",
        "language",
        "definition_language",
    }


def test_dictionary_entry_term_has_lookup_index() -> None:
    indexes = {
        index.name: {column.name for column in index.columns}
        for index in DictionaryEntryTerm.__table__.indexes
    }

    assert indexes["ix_dictionary_entry_terms_normalized_term"] == {"normalized_term"}
    assert DictionaryEntry.__table__.c.senses.nullable is False
