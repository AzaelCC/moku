"""Minimal learner and review persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from moku_backend.db.metadata import Base


class Learner(Base):
    __tablename__ = "learners"
    __table_args__ = (UniqueConstraint("handle", name="uq_learners_handle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    handle: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cards: Mapped[list[LearnerCard]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class LearnerCard(Base):
    __tablename__ = "learner_cards"
    __table_args__ = (
        UniqueConstraint("learner_id", "word", "language", name="uq_learner_cards_word_language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    interval_days: Mapped[int | None] = mapped_column(Integer)
    schedule_status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)
    scheduling_algorithm: Mapped[str] = mapped_column(String(32), default="legacy", nullable=False)
    fsrs_card: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    learner: Mapped[Learner] = relationship(back_populates="cards")
    review_logs: Mapped[list[ReviewLog]] = relationship(
        back_populates="learner_card", cascade="all, delete-orphan"
    )


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    learner_card_id: Mapped[int] = mapped_column(
        ForeignKey("learner_cards.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    learner_card: Mapped[LearnerCard] = relationship(back_populates="review_logs")
