"""Corpus persistence models."""

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


class Corpus(Base):
    __tablename__ = "corpora"
    __table_args__ = (UniqueConstraint("name", name="uq_corpora_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sentences: Mapped[list[Sentence]] = relationship(
        back_populates="corpus", cascade="all, delete-orphan"
    )


class Sentence(Base):
    __tablename__ = "sentences"
    __table_args__ = (
        UniqueConstraint("text", name="uq_sentences_text"),
        Index(
            "ix_sentences_corpus_id_max_content_word_rank",
            "corpus_id",
            "max_content_word_rank",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    corpus_id: Mapped[int] = mapped_column(ForeignKey("corpora.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_tokens: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    max_content_word_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    corpus: Mapped[Corpus] = relationship(back_populates="sentences")


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    corpus_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    max_documents: Mapped[int | None] = mapped_column(Integer)
    max_sentences: Mapped[int | None] = mapped_column(Integer)
    sentence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
