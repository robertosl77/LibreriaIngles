"""T-212: banco de ejercicios compartido (épica T-210 #299).

Revision ID: 0032_exercise_bank
Revises: 0031_drop_failed_class_sessions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_exercise_bank"
down_revision: Union[str, Sequence[str], None] = "0031_drop_failed_class_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRESENTATION = sa.Enum("READ", "LISTEN", name="presentationmode", native_enum=False, length=10)
RESPONSE = sa.Enum("WRITE", "SPEAK", "SELECT", name="responsemode", native_enum=False, length=10)
STATUS = sa.Enum("ACTIVE", "RETIRED", name="bankitemstatus", native_enum=False, length=10)


def upgrade() -> None:
    evaluation = sa.Enum("DETERMINISTIC", "HYBRID", "AI", name="evaluationmode", native_enum=False)
    op.create_table(
        "exercise_bank_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, unique=True),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.Column("area", sa.String(length=40), nullable=True),
        sa.Column("skill_key", sa.String(length=160), nullable=False),
        sa.Column("exercise_type", sa.String(length=80), nullable=False),
        sa.Column("presentation_mode", PRESENTATION, nullable=False),
        sa.Column("response_mode", RESPONSE, nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("expected_concepts", sa.JSON(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=False),
        sa.Column("evaluation_mode", evaluation, nullable=False),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("retired_reason", sa.String(length=200), nullable=True),
        sa.Column("source_provider", sa.String(length=80), nullable=True),
        sa.Column("source_model", sa.String(length=120), nullable=True),
        sa.Column("source_session_id", sa.Integer(), nullable=True),
        sa.Column("times_served", sa.Integer(), nullable=False),
        sa.Column("appeals", sa.Integer(), nullable=False),
        sa.Column("appeals_accepted", sa.Integer(), nullable=False),
        sa.Column("repeat_reports", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_exercise_bank_items_pick", "exercise_bank_items",
                    ["level", "skill_key", "exercise_type", "status"])
    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("bank_item_id", sa.Integer(), nullable=True))
        batch.create_index("ix_exercises_bank_item_id", ["bank_item_id"])
        batch.create_foreign_key("fk_exercises_bank_item_id", "exercise_bank_items",
                                 ["bank_item_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.drop_constraint("fk_exercises_bank_item_id", type_="foreignkey")
        batch.drop_index("ix_exercises_bank_item_id")
        batch.drop_column("bank_item_id")
    op.drop_index("ix_exercise_bank_items_pick", table_name="exercise_bank_items")
    op.drop_table("exercise_bank_items")
