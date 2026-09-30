"""Flujo de aprendizaje: niveles, clases, autoguardado, progreso y conexiones IA.

Revision ID: 0002_learning_flow
Revises: 0001_initial_schema
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_learning_flow"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLASS_STATUS_NEW = sa.Enum(
    "GENERATING",
    "GENERATION_FAILED",
    "READY",
    "IN_PROGRESS",
    "AWAITING_EVALUATION",
    "COMPLETED",
    name="classsessionstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "draft_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["class_session_id"], ["class_sessions.id"]),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_id", name="uq_draft_answers_exercise"),
    )
    op.create_index(
        "ix_draft_answers_class_session_id",
        "draft_answers",
        ["class_session_id"],
    )

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(sa.Column("display_name", sa.String(160), nullable=True))

    with op.batch_alter_table("study_profiles") as batch_op:
        batch_op.add_column(sa.Column("selected_level", sa.String(2), nullable=True))
        batch_op.add_column(sa.Column("estimated_level", sa.String(2), nullable=True))
        batch_op.add_column(sa.Column("operational_level", sa.String(2), nullable=True))

    with op.batch_alter_table("ai_connections") as batch_op:
        batch_op.add_column(sa.Column("model", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("credential_hint", sa.String(32), nullable=True))
        batch_op.add_column(
            sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("last_error_code", sa.String(40), nullable=True))
        batch_op.add_column(
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_ai_connections_owner", ["owner_type", "owner_id"])
        batch_op.create_check_constraint(
            "ck_ai_connections_owner",
            "(owner_type = 'PLATFORM' AND owner_id IS NULL) "
            "OR (owner_type <> 'PLATFORM' AND owner_id IS NOT NULL)",
        )

    # Estados anteriores de clase → conjunto unificado.
    op.execute(
        "UPDATE class_sessions SET status = 'AWAITING_EVALUATION' "
        "WHERE status IN ('SUBMITTED', 'EVALUATION_PENDING')"
    )

    with op.batch_alter_table("class_sessions") as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("target_level", sa.String(2), nullable=True))
        batch_op.add_column(sa.Column("title", sa.String(200), nullable=True))
        batch_op.add_column(
            sa.Column(
                "current_attempt", sa.Integer(), nullable=False, server_default="1"
            )
        )
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("generated_by_connection_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.VARCHAR(length=18),
            type_=CLASS_STATUS_NEW,
            existing_nullable=False,
        )
        batch_op.create_index(
            "ix_class_sessions_study_profile_id", ["study_profile_id"]
        )
        batch_op.create_foreign_key(
            "fk_class_sessions_account_id", "accounts", ["account_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_class_sessions_generated_by_connection_id",
            "ai_connections",
            ["generated_by_connection_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column("position", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("level", sa.String(2), nullable=True))
        batch_op.add_column(sa.Column("area", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("skill_key", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("instruction", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("content", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column(
                "expected_concepts", sa.JSON(), nullable=False, server_default="[]"
            )
        )
        batch_op.create_index("ix_exercises_class_session_id", ["class_session_id"])

    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "attempt_number", sa.Integer(), nullable=False, server_default="1"
            )
        )
        batch_op.add_column(
            sa.Column("appealed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_attempts_exercise_id", ["exercise_id"])
        batch_op.create_unique_constraint(
            "uq_attempts_exercise_number", ["exercise_id", "attempt_number"]
        )
        batch_op.create_foreign_key(
            "fk_attempts_account_id", "accounts", ["account_id"], ["id"]
        )

    with op.batch_alter_table("study_skill_progress") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status", sa.String(20), nullable=False, server_default="LEARNING"
            )
        )
        batch_op.add_column(
            sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True)
        )
        # NULL en organization_id no se considera duplicado en un UNIQUE normal:
        # se reemplaza por dos índices únicos parciales.
        batch_op.drop_constraint("uq_study_skill_progress_scope", type_="unique")
        batch_op.create_index(
            "uq_study_skill_progress_global",
            ["study_profile_id", "skill_key"],
            unique=True,
            sqlite_where=sa.text("organization_id IS NULL"),
            postgresql_where=sa.text("organization_id IS NULL"),
        )
        batch_op.create_index(
            "uq_study_skill_progress_org",
            ["study_profile_id", "skill_key", "organization_id"],
            unique=True,
            sqlite_where=sa.text("organization_id IS NOT NULL"),
            postgresql_where=sa.text("organization_id IS NOT NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("study_skill_progress") as batch_op:
        batch_op.drop_index("uq_study_skill_progress_org")
        batch_op.drop_index("uq_study_skill_progress_global")
        batch_op.create_unique_constraint(
            "uq_study_skill_progress_scope",
            ["study_profile_id", "skill_key", "organization_id"],
        )
        batch_op.drop_column("last_practiced_at")
        batch_op.drop_column("status")

    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_constraint("fk_attempts_account_id", type_="foreignkey")
        batch_op.drop_constraint("uq_attempts_exercise_number", type_="unique")
        batch_op.drop_index("ix_attempts_exercise_id")
        batch_op.drop_column("evaluated_at")
        batch_op.drop_column("appealed_at")
        batch_op.drop_column("attempt_number")
        batch_op.drop_column("account_id")

    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_index("ix_exercises_class_session_id")
        for column in (
            "expected_concepts",
            "content",
            "instruction",
            "skill_key",
            "area",
            "level",
            "position",
        ):
            batch_op.drop_column(column)

    op.execute(
        "UPDATE class_sessions SET status = 'EVALUATION_PENDING' "
        "WHERE status = 'AWAITING_EVALUATION'"
    )

    with op.batch_alter_table("class_sessions") as batch_op:
        batch_op.drop_constraint(
            "fk_class_sessions_generated_by_connection_id", type_="foreignkey"
        )
        batch_op.drop_constraint("fk_class_sessions_account_id", type_="foreignkey")
        batch_op.drop_index("ix_class_sessions_study_profile_id")
        batch_op.alter_column(
            "status",
            existing_type=CLASS_STATUS_NEW,
            type_=sa.VARCHAR(length=18),
            existing_nullable=False,
        )
        for column in (
            "evaluated_at",
            "submitted_at",
            "generated_by_connection_id",
            "score",
            "current_attempt",
            "title",
            "target_level",
            "account_id",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("ai_connections") as batch_op:
        batch_op.drop_constraint("ck_ai_connections_owner", type_="check")
        batch_op.drop_index("ix_ai_connections_owner")
        for column in (
            "last_error_at",
            "last_error_code",
            "last_used_at",
            "last_check_at",
            "credential_hint",
            "model",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("study_profiles") as batch_op:
        batch_op.drop_column("operational_level")
        batch_op.drop_column("estimated_level")
        batch_op.drop_column("selected_level")

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("display_name")

    op.drop_index("ix_draft_answers_class_session_id", table_name="draft_answers")
    op.drop_table("draft_answers")
