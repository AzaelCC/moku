"""Separate learner notes from learner cards."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "202606230001"
down_revision = "202606210004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("note_key", sa.String(length=512), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "learner_id",
            "language",
            "note_key",
            name="uq_learner_notes_learner_language_key",
        ),
    )
    op.create_index(op.f("ix_learner_notes_learner_id"), "learner_notes", ["learner_id"])
    op.create_index(op.f("ix_learner_notes_public_id"), "learner_notes", ["public_id"], unique=True)
    op.create_index(op.f("ix_learner_notes_word"), "learner_notes", ["word"])

    op.add_column("learner_cards", sa.Column("learner_note_id", sa.Integer(), nullable=True))
    op.add_column(
        "learner_cards",
        sa.Column("card_type", sa.String(length=120), server_default="default", nullable=False),
    )

    _backfill_legacy_notes()

    op.alter_column("learner_cards", "learner_note_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("learner_cards", "card_type", server_default=None)
    op.create_index(
        op.f("ix_learner_cards_learner_note_id"),
        "learner_cards",
        ["learner_note_id"],
    )
    op.create_foreign_key(
        "fk_learner_cards_learner_note_id",
        "learner_cards",
        "learner_notes",
        ["learner_note_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_learner_cards_note_card_type",
        "learner_cards",
        ["learner_note_id", "card_type"],
    )

    op.drop_constraint("uq_learner_cards_word_language", "learner_cards", type_="unique")
    op.drop_constraint("learner_cards_learner_id_fkey", "learner_cards", type_="foreignkey")
    op.drop_index(op.f("ix_learner_cards_learner_id"), table_name="learner_cards")
    op.drop_index(op.f("ix_learner_cards_word"), table_name="learner_cards")
    op.drop_column("learner_cards", "language")
    op.drop_column("learner_cards", "word")
    op.drop_column("learner_cards", "learner_id")


def downgrade() -> None:
    op.add_column("learner_cards", sa.Column("learner_id", sa.Integer(), nullable=True))
    op.add_column("learner_cards", sa.Column("word", sa.String(length=255), nullable=True))
    op.add_column("learner_cards", sa.Column("language", sa.String(length=32), nullable=True))
    op.execute(
        """
        UPDATE learner_cards AS card
        SET learner_id = note.learner_id,
            word = note.word,
            language = note.language
        FROM learner_notes AS note
        WHERE card.learner_note_id = note.id
        """
    )
    op.execute(
        """
        DELETE FROM learner_cards
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY learner_id, word, language
                           ORDER BY id
                       ) AS duplicate_rank
                FROM learner_cards
            ) ranked_cards
            WHERE duplicate_rank > 1
        )
        """
    )
    op.alter_column("learner_cards", "learner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column(
        "learner_cards",
        "word",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "learner_cards",
        "language",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.create_index(op.f("ix_learner_cards_learner_id"), "learner_cards", ["learner_id"])
    op.create_index(op.f("ix_learner_cards_word"), "learner_cards", ["word"])
    op.create_foreign_key(
        "learner_cards_learner_id_fkey",
        "learner_cards",
        "learners",
        ["learner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_learner_cards_word_language",
        "learner_cards",
        ["learner_id", "word", "language"],
    )

    op.drop_constraint("uq_learner_cards_note_card_type", "learner_cards", type_="unique")
    op.drop_constraint("fk_learner_cards_learner_note_id", "learner_cards", type_="foreignkey")
    op.drop_index(op.f("ix_learner_cards_learner_note_id"), table_name="learner_cards")
    op.drop_column("learner_cards", "card_type")
    op.drop_column("learner_cards", "learner_note_id")
    op.drop_index(op.f("ix_learner_notes_word"), table_name="learner_notes")
    op.drop_index(op.f("ix_learner_notes_public_id"), table_name="learner_notes")
    op.drop_index(op.f("ix_learner_notes_learner_id"), table_name="learner_notes")
    op.drop_table("learner_notes")


def _backfill_legacy_notes() -> None:
    connection = op.get_bind()
    legacy_cards = sa.table(
        "learner_cards",
        sa.column("id", sa.Integer()),
        sa.column("learner_id", sa.Integer()),
        sa.column("word", sa.String(length=255)),
        sa.column("language", sa.String(length=32)),
        sa.column("learner_note_id", sa.Integer()),
        sa.column("source_metadata", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    learner_notes = sa.table(
        "learner_notes",
        sa.column("id", sa.Integer()),
        sa.column("public_id", sa.Uuid()),
        sa.column("learner_id", sa.Integer()),
        sa.column("word", sa.String(length=255)),
        sa.column("language", sa.String(length=32)),
        sa.column("note_key", sa.String(length=512)),
        sa.column("source_metadata", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    rows = connection.execute(
        sa.select(
            legacy_cards.c.id,
            legacy_cards.c.learner_id,
            legacy_cards.c.word,
            legacy_cards.c.language,
            legacy_cards.c.source_metadata,
            legacy_cards.c.created_at,
        )
    ).mappings()
    for row in rows:
        note_id = connection.execute(
            learner_notes.insert()
            .values(
                public_id=uuid.uuid4(),
                learner_id=row["learner_id"],
                word=row["word"],
                language=row["language"],
                note_key=f"legacy:{row['id']}",
                source_metadata=row["source_metadata"] or {},
                created_at=row["created_at"],
            )
            .returning(learner_notes.c.id)
        ).scalar_one()
        connection.execute(
            legacy_cards.update()
            .where(legacy_cards.c.id == row["id"])
            .values(learner_note_id=note_id)
        )
