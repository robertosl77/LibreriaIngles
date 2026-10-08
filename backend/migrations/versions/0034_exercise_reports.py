"""T-216: reportes de ejercicios y calidad del banco.

Revision ID: 0034_exercise_reports
Revises: 0033_practice_batches
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_exercise_reports"
down_revision: Union[str, Sequence[str], None] = "0033_practice_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_bank_items") as batch:
        batch.add_column(sa.Column("wrong_reports", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.create_table(
        "exercise_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("bank_item_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Enum("REPEATED", "WRONG", name="exercisereportreason", native_enum=False, length=10),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE",
                                name="fk_exercise_reports_exercise_id"),
        sa.UniqueConstraint("exercise_id", "study_profile_id", "reason", name="uq_exercise_reports_once"),
    )
    op.create_index("ix_exercise_reports_exercise_id", "exercise_reports", ["exercise_id"])
    op.create_index("ix_exercise_reports_bank_item_id", "exercise_reports", ["bank_item_id"])


def downgrade() -> None:
    op.drop_index("ix_exercise_reports_bank_item_id", table_name="exercise_reports")
    op.drop_index("ix_exercise_reports_exercise_id", table_name="exercise_reports")
    op.drop_table("exercise_reports")
    with op.batch_alter_table("exercise_bank_items") as batch:
        batch.drop_column("wrong_reports")
