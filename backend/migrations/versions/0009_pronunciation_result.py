"""Resultado de pronunciación para respuestas habladas (T-027).

Revision ID: 0009_pronunciation_result
Revises: 0008_speaking_audio
Create Date: 2026-10-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_pronunciation_result"
down_revision: Union[str, Sequence[str], None] = "0008_speaking_audio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("draft_answers") as batch_op:
        batch_op.add_column(sa.Column("pronunciation_result", sa.JSON(), nullable=True))
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(sa.Column("pronunciation_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_column("pronunciation_result")
    with op.batch_alter_table("draft_answers") as batch_op:
        batch_op.drop_column("pronunciation_result")
