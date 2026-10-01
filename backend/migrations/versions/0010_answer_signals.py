"""Señales por respuesta para las evidencias por habilidad (T-034).

Revision ID: 0010_answer_signals
Revises: 0009_pronunciation_result
Create Date: 2026-10-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_answer_signals"
down_revision: Union[str, Sequence[str], None] = "0009_pronunciation_result"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("draft_answers", "attempts"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("signals", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in ("attempts", "draft_answers"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("signals")
