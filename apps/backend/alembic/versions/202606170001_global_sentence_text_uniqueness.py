"""Make sentence text globally unique."""

from alembic import op

revision = "202606170001"
down_revision = "202606160001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM sentences
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (PARTITION BY text ORDER BY id) AS duplicate_rank
                FROM sentences
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.drop_constraint("uq_sentences_corpus_text", "sentences", type_="unique")
    op.create_unique_constraint("uq_sentences_text", "sentences", ["text"])


def downgrade() -> None:
    op.drop_constraint("uq_sentences_text", "sentences", type_="unique")
    op.create_unique_constraint(
        "uq_sentences_corpus_text", "sentences", ["corpus_id", "text"]
    )
