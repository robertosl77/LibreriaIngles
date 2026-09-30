"""Initial schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_subject", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.Enum("PERSONAL", "CORPORATE", native_enum=False), nullable=False),
        sa.Column("auth_method", sa.Enum("GOOGLE", "LOCAL", native_enum=False), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING_VERIFICATION", "ACTIVE", "DISABLED", native_enum=False),
            nullable=False,
        ),
        sa.Column("platform_role", sa.Enum("PLATFORM_OWNER", native_enum=False), nullable=True),
        sa.Column("document_country", sa.String(length=2), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=True),
        sa.Column("document_number", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)
    op.create_index("ix_accounts_google_subject", "accounts", ["google_subject"], unique=True)
    op.create_index("ix_accounts_account_type", "accounts", ["account_type"], unique=False)
    op.create_index("ix_accounts_document_number", "accounts", ["document_number"], unique=False)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("logo_path", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "study_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "ARCHIVED", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("ai_source", sa.Enum("BYOK", "PLATFORM", "HYBRID", native_enum=False), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "STUDENT", native_enum=False), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "REVOKED", "SUSPENDED", native_enum=False), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["revoked_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "organization_id", name="uq_membership_account_org"),
    )
    op.create_index("ix_memberships_account_id", "memberships", ["account_id"], unique=False)
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"], unique=False)

    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("role", sa.Enum("ADMIN", "STUDENT", native_enum=False), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "ACCEPTED", "EXPIRED", "CANCELLED", native_enum=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"], unique=False)
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"], unique=False)
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_index(
        "uq_pending_invitation_org_email",
        "invitations",
        ["organization_id", "email"],
        unique=True,
        sqlite_where=sa.text("status = 'PENDING'"),
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "account_study_profiles",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "REVOKED", native_enum=False), nullable=False),
        sa.Column("link_method", sa.Enum("INITIAL", "EMAIL_CODE", native_enum=False), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.PrimaryKeyConstraint("account_id", "study_profile_id"),
    )

    op.create_table(
        "account_link_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "VERIFIED", "EXPIRED", "CANCELLED", native_enum=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "PAUSED", "CANCELLED", "EXPIRED", native_enum=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.Enum("PLATFORM", "ORGANIZATION", "ACCOUNT", native_enum=False), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("credentials_encrypted", sa.String(length=4000), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "AVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED", "INVALID_CREDENTIALS",
                "PROVIDER_DOWN", "NETWORK_ERROR", "UNKNOWN_ERROR", "DISABLED",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "class_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "GENERATING", "GENERATION_FAILED", "READY", "IN_PROGRESS",
                "SUBMITTED", "EVALUATION_PENDING", "COMPLETED",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("generation_request", sa.JSON(), nullable=True),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_session_id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("exercise_type", sa.String(length=80), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=False),
        sa.Column("evaluation_mode", sa.Enum("DETERMINISTIC", "HYBRID", "AI", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["class_session_id"], ["class_sessions.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("raw_answer", sa.Text(), nullable=False),
        sa.Column("normalized_answer", sa.Text(), nullable=False),
        sa.Column("evaluation_source", sa.Enum("RULE_MATCH", "COMMON_ERROR_MATCH", "AI", native_enum=False), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("evaluation_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "study_skill_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_profile_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("skill_key", sa.String(length=160), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_profile_id", "skill_key", "organization_id", name="uq_study_skill_progress_scope"),
    )

    op.create_table(
        "ai_evaluation_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("normalized_answer", sa.Text(), nullable=False),
        sa.Column("evaluation_result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_id", "normalized_answer", name="uq_ai_evaluation_cache_answer"),
    )


def downgrade() -> None:
    op.drop_table("ai_evaluation_cache")
    op.drop_table("study_skill_progress")
    op.drop_table("attempts")
    op.drop_table("exercises")
    op.drop_table("class_sessions")
    op.drop_table("ai_connections")
    op.drop_table("subscriptions")
    op.drop_table("account_link_verifications")
    op.drop_table("account_study_profiles")
    op.drop_index("uq_pending_invitation_org_email", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_memberships_organization_id", table_name="memberships")
    op.drop_index("ix_memberships_account_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("plans")
    op.drop_table("study_profiles")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("ix_accounts_document_number", table_name="accounts")
    op.drop_index("ix_accounts_account_type", table_name="accounts")
    op.drop_index("ix_accounts_google_subject", table_name="accounts")
    op.drop_index("ix_accounts_email", table_name="accounts")
    op.drop_table("accounts")
