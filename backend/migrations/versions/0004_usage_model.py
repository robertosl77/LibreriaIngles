"""Modelo usado en cada llamada de IA (edición de conexiones, T-006).

Revision ID: 0004_usage_model
Revises: 0003_platform_ai_usage
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_usage_model"
down_revision: Union[str, Sequence[str], None] = "0003_platform_ai_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch_op:
        batch_op.add_column(sa.Column("model", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch_op:
        batch_op.drop_column("model")
