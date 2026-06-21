"""Add sentence max content word rank."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "202606210001"
down_revision = "202606190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sentences",
        sa.Column("max_content_word_rank", sa.Integer(), nullable=True),
    )
    _backfill_max_content_word_rank()
    op.alter_column(
        "sentences",
        "max_content_word_rank",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_index(
        "ix_sentences_corpus_id_max_content_word_rank",
        "sentences",
        ["corpus_id", "max_content_word_rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sentences_corpus_id_max_content_word_rank", table_name="sentences")
    op.drop_column("sentences", "max_content_word_rank")


def _backfill_max_content_word_rank() -> None:
    bind = op.get_bind()
    corpus_ids = bind.execute(sa.text("SELECT id FROM corpora ORDER BY id")).scalars().all()
    for corpus_id in corpus_ids:
        rows = (
            bind.execute(
                sa.text(
                    """
                    SELECT id, content_tokens
                    FROM sentences
                    WHERE corpus_id = :corpus_id
                    ORDER BY id
                    """
                ),
                {"corpus_id": corpus_id},
            )
            .mappings()
            .all()
        )
        counts: Counter[str] = Counter()
        token_lists: list[tuple[int, Sequence[str]]] = []
        for row in rows:
            content_tokens = _content_tokens(row["content_tokens"])
            token_lists.append((row["id"], content_tokens))
            counts.update(content_tokens)

        word_ranks = {
            word: rank for rank, (word, _count) in enumerate(counts.most_common(), start=1)
        }
        updates = [
            {
                "sentence_id": sentence_id,
                "max_content_word_rank": max(
                    (word_ranks[word] for word in set(content_tokens)), default=0
                ),
            }
            for sentence_id, content_tokens in token_lists
        ]
        if updates:
            bind.execute(
                sa.text(
                    """
                    UPDATE sentences
                    SET max_content_word_rank = :max_content_word_rank
                    WHERE id = :sentence_id
                    """
                ),
                updates,
            )


def _content_tokens(value: Any) -> Sequence[str]:
    if isinstance(value, str):
        return json.loads(value)
    return value
