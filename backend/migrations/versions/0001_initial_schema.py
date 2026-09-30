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
        sa.Column(
            "account_type",
            sa.Enum("PERSONAL", "CORPORATE", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "auth_method",
            sa.Enum("GOOGLE", "LOCAL", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING_VERIFICATION",
                "ACTIVE",
                "DISABLED",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("document_country", sa.String(length=2), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=True),
        sa.Column("document_number", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)
    op.create_index(
        "ix_accounts_google_subject",
        "accounts",
        ["google_subject"],
        unique=True,
    )
    op.create_index(
        "ix_accounts_account_type",
        "accounts",
        ["account_type"],
        unique=False,
    )
    op.create_index(
        "ix_accounts_document_number",
        "accounts",
        ["document_number"],
        unique=False,
    )

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
    op.create_index(
        "ix_organizations_slug",
        "organizations",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "study_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "ARCHIVED", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("OWNER", "STUDENT", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REVOKED", "SUSPENDED", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "organization_id",
            name="uq_membership_account_org",
        ),
    )
    op.create_index(
        "ix_memberships_account_id",
        "memberships",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_memberships_organization_id",
        "memberships",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column(
            "role",
            sa.Enum("OWNER", "STUDENT", native_enum=False),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "ACCEPTED",
                "EXPIRED",
                "CANCELLED",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invitations_email",
        "invitations",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_organization_id",
        "invitations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_token_hash",
        "invitations",
        ["token_hash"],
        unique=True,
    )
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
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("link_method", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["study_profile_id"], ["study_profiles.id"]),
        sa.PrimaryKeyConstraint("account_id", "study_profile_id"),
    )


def downgrade() -> None:
    op.drop_table("account_study_profiles")
    op.drop_index("uq_pending_invitation_org_email", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_memberships_organization_id", table_name="memberships")
    op.drop_index("ix_memberships_account_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("study_profiles")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("ix_accounts_document_number", table_name="accounts")
    op.drop_index("ix_accounts_account_type", table_name="accounts")
    op.drop_index("ix_accounts_google_subject", table_name="accounts")
    op.drop_index("ix_accounts_email", table_name="accounts")
    op.drop_table("accounts")
