"""P02: verificación de email reutilizable y delivery desacoplado.

Revision ID: 0028_email_verification_challenges
Revises: 0027_job_titles
Create Date: 2026-10-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028_email_verification_challenges"
down_revision: Union[str, Sequence[str], None] = "0027_job_titles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("organization_onboardings") as batch:
        batch.add_column(sa.Column("continuation_token_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("contact_email_verified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "notification_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("subject_template", sa.String(length=300), nullable=False),
        sa.Column("body_template", sa.String(length=4000), nullable=False),
        sa.Column("sender_profile", sa.String(length=120), nullable=False),
        sa.Column("platform_only", sa.Boolean(), nullable=False),
        sa.Column("organization_override_allowed", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_cases_code"), "notification_cases", ["code"], unique=True)
    op.create_index(op.f("ix_notification_cases_active"), "notification_cases", ["active"], unique=False)

    op.create_table(
        "verification_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("context_type", sa.String(length=80), nullable=False),
        sa.Column("context_id", sa.String(length=120), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("code_digest", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_challenges_public_id"), "verification_challenges", ["public_id"], unique=True)
    op.create_index(op.f("ix_verification_challenges_purpose"), "verification_challenges", ["purpose"], unique=False)
    op.create_index(op.f("ix_verification_challenges_context_type"), "verification_challenges", ["context_type"], unique=False)
    op.create_index(op.f("ix_verification_challenges_context_id"), "verification_challenges", ["context_id"], unique=False)
    op.create_index(op.f("ix_verification_challenges_destination"), "verification_challenges", ["destination"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_verification_challenges_destination"), table_name="verification_challenges")
    op.drop_index(op.f("ix_verification_challenges_context_id"), table_name="verification_challenges")
    op.drop_index(op.f("ix_verification_challenges_context_type"), table_name="verification_challenges")
    op.drop_index(op.f("ix_verification_challenges_purpose"), table_name="verification_challenges")
    op.drop_index(op.f("ix_verification_challenges_public_id"), table_name="verification_challenges")
    op.drop_table("verification_challenges")

    op.drop_index(op.f("ix_notification_cases_active"), table_name="notification_cases")
    op.drop_index(op.f("ix_notification_cases_code"), table_name="notification_cases")
    op.drop_table("notification_cases")

    with op.batch_alter_table("organization_onboardings") as batch:
        batch.drop_column("contact_email_verified_at")
        batch.drop_column("continuation_token_hash")
