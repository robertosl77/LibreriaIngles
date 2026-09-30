"""Examen de nivel y certificados (T-024).

Revision ID: 0006_level_exams
Revises: 0005_assistance
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_level_exams"
down_revision: Union[str, Sequence[str], None] = "0005_assistance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("class_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.Enum("CLASS", "EXAM", name="sessionkind", native_enum=False, length=10),
                nullable=False,
                server_default="CLASS",
            )
        )
        batch_op.add_column(sa.Column("exam_result", sa.JSON(), nullable=True))

    op.create_table(
        "level_certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("exam_session_id", sa.Integer(), nullable=False),
        sa.Column("holder_name", sa.String(160), nullable=False),
        sa.Column("level", sa.String(2), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("area_scores", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["exam_session_id"], ["class_sessions.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_profile_id", "level", name="uq_level_certificates_profile_level"),
    )
    op.create_index("ix_level_certificates_code", "level_certificates", ["code"], unique=True)
    op.create_index(
        "ix_level_certificates_study_profile_id", "level_certificates", ["study_profile_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_level_certificates_study_profile_id", table_name="level_certificates")
    op.drop_index("ix_level_certificates_code", table_name="level_certificates")
    op.drop_table("level_certificates")
    with op.batch_alter_table("class_sessions") as batch_op:
        batch_op.drop_column("exam_result")
        batch_op.drop_column("kind")
