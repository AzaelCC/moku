"""Add FSRS learner card state."""

import sqlalchemy as sa
from alembic import op

revision = "202606190001"
down_revision = "202606180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learner_cards",
        sa.Column(
            "scheduling_algorithm",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column("learner_cards", sa.Column("fsrs_card", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE learner_cards "
        "SET scheduling_algorithm = 'anki' "
        "WHERE source_metadata ->> 'source' = 'anki'"
    )
    op.alter_column("learner_cards", "scheduling_algorithm", server_default=None)


def downgrade() -> None:
    op.drop_column("learner_cards", "fsrs_card")
    op.drop_column("learner_cards", "scheduling_algorithm")
