"""T-135: correlación de intentos y failover de IA.

Revision ID: 0022_ai_usage_execution
Revises: 0021_ai_consumption
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_ai_usage_execution"
down_revision: Union[str, Sequence[str], None] = "0021_ai_consumption"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.add_column(sa.Column("execution_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("attempt_index", sa.Integer(), nullable=True))

    op.create_index(
        "ix_ai_usage_events_execution",
        "ai_usage_events",
        ["execution_id", "attempt_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_execution", table_name="ai_usage_events")
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.drop_column("attempt_index")
        batch.drop_column("execution_id")
