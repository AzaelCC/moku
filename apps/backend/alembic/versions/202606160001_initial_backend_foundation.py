"""Initial backend foundation."""

import sqlalchemy as sa
from alembic import op

# ruff: noqa: E501

revision = "202606160001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpora",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", name="uq_corpora_name"),
    )
    op.create_index(op.f("ix_corpora_public_id"), "corpora", ["public_id"], unique=True)

    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("corpus_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("max_documents", sa.Integer(), nullable=True),
        sa.Column("max_sentences", sa.Integer(), nullable=True),
        sa.Column("sentence_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_import_runs_public_id"), "import_runs", ["public_id"], unique=True)

    op.create_table(
        "learners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("handle", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("handle", name="uq_learners_handle"),
    )
    op.create_index(op.f("ix_learners_public_id"), "learners", ["public_id"], unique=True)

    op.create_table(
        "sentences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.JSON(), nullable=False),
        sa.Column("content_tokens", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("corpus_id", "text", name="uq_sentences_corpus_text"),
    )
    op.create_index(op.f("ix_sentences_corpus_id"), "sentences", ["corpus_id"], unique=False)
    op.create_index(op.f("ix_sentences_public_id"), "sentences", ["public_id"], unique=True)

    op.create_table(
        "learner_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "learner_id", "word", "language", name="uq_learner_cards_word_language"
        ),
    )
    op.create_index(op.f("ix_learner_cards_due_at"), "learner_cards", ["due_at"], unique=False)
    op.create_index(
        op.f("ix_learner_cards_learner_id"), "learner_cards", ["learner_id"], unique=False
    )
    op.create_index(op.f("ix_learner_cards_public_id"), "learner_cards", ["public_id"], unique=True)
    op.create_index(op.f("ix_learner_cards_word"), "learner_cards", ["word"], unique=False)

    op.create_table(
        "review_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("learner_card_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["learner_card_id"], ["learner_cards.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_review_logs_learner_card_id"), "review_logs", ["learner_card_id"], unique=False
    )
    op.create_index(op.f("ix_review_logs_public_id"), "review_logs", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_logs_public_id"), table_name="review_logs")
    op.drop_index(op.f("ix_review_logs_learner_card_id"), table_name="review_logs")
    op.drop_table("review_logs")
    op.drop_index(op.f("ix_learner_cards_word"), table_name="learner_cards")
    op.drop_index(op.f("ix_learner_cards_public_id"), table_name="learner_cards")
    op.drop_index(op.f("ix_learner_cards_learner_id"), table_name="learner_cards")
    op.drop_index(op.f("ix_learner_cards_due_at"), table_name="learner_cards")
    op.drop_table("learner_cards")
    op.drop_index(op.f("ix_sentences_public_id"), table_name="sentences")
    op.drop_index(op.f("ix_sentences_corpus_id"), table_name="sentences")
    op.drop_table("sentences")
    op.drop_index(op.f("ix_learners_public_id"), table_name="learners")
    op.drop_table("learners")
    op.drop_index(op.f("ix_import_runs_public_id"), table_name="import_runs")
    op.drop_table("import_runs")
    op.drop_index(op.f("ix_corpora_public_id"), table_name="corpora")
    op.drop_table("corpora")
