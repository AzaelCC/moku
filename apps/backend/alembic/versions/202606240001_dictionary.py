"""Add dictionary lookup tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202606240001"
down_revision = "202606230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dictionary_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("definition_language", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=120), nullable=True),
        sa.Column("license_name", sa.String(length=120), nullable=False),
        sa.Column("license_url", sa.String(length=255), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "source_key",
            "language",
            "definition_language",
            name="uq_dictionary_sources_source_language_definition",
        ),
    )
    op.create_index(
        "ix_dictionary_sources_language_definition",
        "dictionary_sources",
        ["language", "definition_language"],
    )
    op.create_index(
        op.f("ix_dictionary_sources_public_id"),
        "dictionary_sources",
        ["public_id"],
        unique=True,
    )

    op.create_table(
        "dictionary_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("dictionary_source_id", sa.Integer(), nullable=False),
        sa.Column("headword", sa.String(length=255), nullable=False),
        sa.Column("reading", sa.String(length=255), nullable=False),
        sa.Column("senses", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dictionary_source_id"],
            ["dictionary_sources.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_dictionary_entries_dictionary_source_id"),
        "dictionary_entries",
        ["dictionary_source_id"],
    )
    op.create_index(
        "ix_dictionary_entries_source_headword",
        "dictionary_entries",
        ["dictionary_source_id", "headword"],
    )
    op.create_index(
        op.f("ix_dictionary_entries_public_id"),
        "dictionary_entries",
        ["public_id"],
        unique=True,
    )

    op.create_table(
        "dictionary_entry_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("normalized_term", sa.String(length=255), nullable=False),
        sa.Column("term_kind", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["dictionary_entry_id"],
            ["dictionary_entries.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "dictionary_entry_id",
            "term_kind",
            "normalized_term",
            name="uq_dictionary_entry_terms_entry_kind_normalized",
        ),
    )
    op.create_index(
        op.f("ix_dictionary_entry_terms_dictionary_entry_id"),
        "dictionary_entry_terms",
        ["dictionary_entry_id"],
    )
    op.create_index(
        "ix_dictionary_entry_terms_normalized_term",
        "dictionary_entry_terms",
        ["normalized_term"],
    )


def downgrade() -> None:
    op.drop_index("ix_dictionary_entry_terms_normalized_term", table_name="dictionary_entry_terms")
    op.drop_index(
        op.f("ix_dictionary_entry_terms_dictionary_entry_id"),
        table_name="dictionary_entry_terms",
    )
    op.drop_table("dictionary_entry_terms")
    op.drop_index(op.f("ix_dictionary_entries_public_id"), table_name="dictionary_entries")
    op.drop_index("ix_dictionary_entries_source_headword", table_name="dictionary_entries")
    op.drop_index(
        op.f("ix_dictionary_entries_dictionary_source_id"),
        table_name="dictionary_entries",
    )
    op.drop_table("dictionary_entries")
    op.drop_index(op.f("ix_dictionary_sources_public_id"), table_name="dictionary_sources")
    op.drop_index("ix_dictionary_sources_language_definition", table_name="dictionary_sources")
    op.drop_table("dictionary_sources")
