"""Dictionary persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from moku_backend.db.metadata import Base


class DictionarySource(Base):
    __tablename__ = "dictionary_sources"
    __table_args__ = (
        UniqueConstraint(
            "source_key",
            "language",
            "definition_language",
            name="uq_dictionary_sources_source_language_definition",
        ),
        Index("ix_dictionary_sources_language_definition", "language", "definition_language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_language: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str | None] = mapped_column(String(120))
    license_name: Mapped[str] = mapped_column(String(120), nullable=False)
    license_url: Mapped[str] = mapped_column(String(255), nullable=False)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entries: Mapped[list[DictionaryEntry]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"
    __table_args__ = (
        Index("ix_dictionary_entries_source_headword", "dictionary_source_id", "headword"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    dictionary_source_id: Mapped[int] = mapped_column(
        ForeignKey("dictionary_sources.id", ondelete="CASCADE"), index=True
    )
    headword: Mapped[str] = mapped_column(String(255), nullable=False)
    reading: Mapped[str] = mapped_column(String(255), nullable=False)
    senses: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[DictionarySource] = relationship(back_populates="entries")
    terms: Mapped[list[DictionaryEntryTerm]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class DictionaryEntryTerm(Base):
    __tablename__ = "dictionary_entry_terms"
    __table_args__ = (
        UniqueConstraint(
            "dictionary_entry_id",
            "term_kind",
            "normalized_term",
            name="uq_dictionary_entry_terms_entry_kind_normalized",
        ),
        Index("ix_dictionary_entry_terms_normalized_term", "normalized_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dictionary_entry_id: Mapped[int] = mapped_column(
        ForeignKey("dictionary_entries.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False)
    term_kind: Mapped[str] = mapped_column(String(32), nullable=False)

    entry: Mapped[DictionaryEntry] = relationship(back_populates="terms")
