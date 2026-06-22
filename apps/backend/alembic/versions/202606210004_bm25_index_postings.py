"""Add materialized BM25 index postings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202606210004"
down_revision = "202606210003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bm25_index_postings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("index_level_id", sa.Integer(), nullable=False),
        sa.Column("sentence_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("term_frequency", sa.Integer(), nullable=False),
        sa.Column("document_length", sa.Float(), nullable=False),
        sa.Column("idf", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["index_level_id"], ["bm25_index_levels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sentence_id"], ["sentences.id"], ondelete="CASCADE"),
    )
    op.execute(
        """
        INSERT INTO bm25_index_postings (
            index_level_id,
            sentence_id,
            term,
            term_frequency,
            document_length,
            idf
        )
        SELECT
            levels.id,
            corpus_terms.sentence_id,
            corpus_terms.term,
            corpus_terms.term_frequency,
            corpus_documents.document_length,
            index_terms.idf
        FROM bm25_index_levels AS levels
        JOIN bm25_index_terms AS index_terms
          ON index_terms.index_level_id = levels.id
        JOIN bm25_corpus_terms AS corpus_terms
          ON corpus_terms.corpus_id = levels.corpus_id
         AND corpus_terms.term = index_terms.term
        JOIN bm25_corpus_documents AS corpus_documents
          ON corpus_documents.sentence_id = corpus_terms.sentence_id
        JOIN sentences
          ON sentences.id = corpus_terms.sentence_id
        WHERE levels.algorithm_version = 'bm25_v1'
          AND (
            levels.top_k_allowed_words = 0
            OR sentences.max_content_word_rank <= levels.top_k_allowed_words
          )
        """
    )
    op.create_index(
        "ix_bm25_index_postings_level_term_sentence",
        "bm25_index_postings",
        ["index_level_id", "term", "sentence_id"],
        unique=True,
        postgresql_include=["term_frequency", "document_length", "idf"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bm25_index_postings_level_term_sentence",
        table_name="bm25_index_postings",
    )
    op.drop_table("bm25_index_postings")
