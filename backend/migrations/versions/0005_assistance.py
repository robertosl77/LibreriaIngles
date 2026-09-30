"""Ayuda usada al responder (lección / pista) y refuerzo en el progreso (T-020).

Revision ID: 0005_assistance
Revises: 0004_usage_model
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_assistance"
down_revision: Union[str, Sequence[str], None] = "0004_usage_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assistance() -> sa.Enum:
    return sa.Enum("NONE", "HINT", "LESSON", name="assistance", native_enum=False, length=20)


def upgrade() -> None:
    for table in ("draft_answers", "attempts"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column("assistance", _assistance(), nullable=False, server_default="NONE")
            )
    with op.batch_alter_table("study_skill_progress") as batch_op:
        batch_op.add_column(
            sa.Column("assisted_recent", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("study_skill_progress") as batch_op:
        batch_op.drop_column("assisted_recent")
    for table in ("attempts", "draft_answers"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("assistance")
