"""Add BM25 preset index tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202606210002"
down_revision = "202606210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bm25_corpus_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corpus_id", sa.Integer(), nullable=False),
        sa.Column("sentence_id", sa.Integer(), nullable=False),
        sa.Column("document_length", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sentence_id"], ["sentences.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("sentence_id", name="uq_bm25_corpus_documents_sentence_id"),
    )
    op.create_index(
        "ix_bm25_corpus_documents_corpus_id",
        "bm25_corpus_documents",
        ["corpus_id"],
        unique=False,
    )

    op.create_table(
        "bm25_corpus_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corpus_id", sa.Integer(), nullable=False),
        sa.Column("sentence_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("term_frequency", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sentence_id"], ["sentences.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("sentence_id", "term", name="uq_bm25_corpus_terms_sentence_term"),
    )
    op.create_index(
        "ix_bm25_corpus_terms_corpus_id_term",
        "bm25_corpus_terms",
        ["corpus_id", "term"],
        unique=False,
    )
    op.create_index(
        "ix_bm25_corpus_terms_sentence_id",
        "bm25_corpus_terms",
        ["sentence_id"],
        unique=False,
    )

    op.create_table(
        "bm25_index_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corpus_id", sa.Integer(), nullable=False),
        sa.Column("top_k_allowed_words", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("average_document_length", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "corpus_id",
            "top_k_allowed_words",
            "algorithm_version",
            name="uq_bm25_index_levels_corpus_top_k_algorithm",
        ),
    )
    op.create_index(
        "ix_bm25_index_levels_corpus_id_top_k",
        "bm25_index_levels",
        ["corpus_id", "top_k_allowed_words"],
        unique=False,
    )

    op.create_table(
        "bm25_index_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("index_level_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("document_frequency", sa.Integer(), nullable=False),
        sa.Column("idf", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["index_level_id"], ["bm25_index_levels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("index_level_id", "term", name="uq_bm25_index_terms_level_term"),
    )
    op.create_index(
        "ix_bm25_index_terms_level_term",
        "bm25_index_terms",
        ["index_level_id", "term"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bm25_index_terms_level_term", table_name="bm25_index_terms")
    op.drop_table("bm25_index_terms")
    op.drop_index("ix_bm25_index_levels_corpus_id_top_k", table_name="bm25_index_levels")
    op.drop_table("bm25_index_levels")
    op.drop_index("ix_bm25_corpus_terms_sentence_id", table_name="bm25_corpus_terms")
    op.drop_index("ix_bm25_corpus_terms_corpus_id_term", table_name="bm25_corpus_terms")
    op.drop_table("bm25_corpus_terms")
    op.drop_index("ix_bm25_corpus_documents_corpus_id", table_name="bm25_corpus_documents")
    op.drop_table("bm25_corpus_documents")
