"""T-153: huella diagnostica estructurada por llamada de IA.

Revision ID: 0024_ai_usage_diagnostics
Revises: 0023_ai_reasoning_tokens
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024_ai_usage_diagnostics"
down_revision: Union[str, Sequence[str], None] = "0023_ai_reasoning_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.add_column(sa.Column("diagnostic_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.drop_column("diagnostic_snapshot")
