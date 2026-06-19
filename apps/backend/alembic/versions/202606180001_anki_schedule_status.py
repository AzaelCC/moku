"""Add learner card schedule status."""

import sqlalchemy as sa
from alembic import op

revision = "202606180001"
down_revision = "202606170001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learner_cards",
        sa.Column(
            "schedule_status",
            sa.String(length=32),
            server_default="scheduled",
            nullable=False,
        ),
    )
    op.alter_column("learner_cards", "schedule_status", server_default=None)
    op.alter_column(
        "learner_cards",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "learner_cards",
        "interval_days",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE learner_cards SET due_at = now() WHERE due_at IS NULL")
    op.execute("UPDATE learner_cards SET interval_days = 1 WHERE interval_days IS NULL")
    op.alter_column(
        "learner_cards",
        "interval_days",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "learner_cards",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("learner_cards", "schedule_status")
