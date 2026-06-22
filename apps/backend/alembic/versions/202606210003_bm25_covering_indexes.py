"""Add covering indexes for BM25 candidate ranking."""

from __future__ import annotations

from alembic import op

revision = "202606210003"
down_revision = "202606210002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_bm25_corpus_terms_corpus_id_term",
            table_name="bm25_corpus_terms",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_bm25_corpus_terms_corpus_id_term",
            "bm25_corpus_terms",
            ["corpus_id", "term", "sentence_id"],
            unique=False,
            postgresql_include=["term_frequency"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_bm25_corpus_documents_sentence_id_cover",
            "bm25_corpus_documents",
            ["sentence_id"],
            unique=False,
            postgresql_include=["document_length"],
            postgresql_concurrently=True,
        )

        op.drop_index(
            "ix_bm25_index_terms_level_term",
            table_name="bm25_index_terms",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_bm25_index_terms_level_term",
            "bm25_index_terms",
            ["index_level_id", "term"],
            unique=False,
            postgresql_include=["idf"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_bm25_index_terms_level_term",
            table_name="bm25_index_terms",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_bm25_index_terms_level_term",
            "bm25_index_terms",
            ["index_level_id", "term"],
            unique=False,
            postgresql_concurrently=True,
        )

        op.drop_index(
            "ix_bm25_corpus_documents_sentence_id_cover",
            table_name="bm25_corpus_documents",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_bm25_corpus_terms_corpus_id_term",
            table_name="bm25_corpus_terms",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_bm25_corpus_terms_corpus_id_term",
            "bm25_corpus_terms",
            ["corpus_id", "term"],
            unique=False,
            postgresql_concurrently=True,
        )
