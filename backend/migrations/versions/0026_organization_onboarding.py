"""P01: solicitud previa de alta corporativa.

Revision ID: 0026_organization_onboarding
Revises: 0025_campaign_policies
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_organization_onboarding"
down_revision: Union[str, Sequence[str], None] = "0025_campaign_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_onboardings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("tax_id_type", sa.String(length=32), nullable=False),
        sa.Column("tax_id", sa.String(length=64), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("legal_entity_type", sa.String(length=120), nullable=True),
        sa.Column("registry_jurisdiction", sa.String(length=160), nullable=True),
        sa.Column("registry_number", sa.String(length=120), nullable=True),
        sa.Column("fiscal_address", sa.String(length=500), nullable=True),
        sa.Column("legal_address", sa.String(length=500), nullable=True),
        sa.Column("primary_activity", sa.String(length=300), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("contact_first_name", sa.String(length=100), nullable=False),
        sa.Column("contact_last_name", sa.String(length=100), nullable=False),
        sa.Column("contact_email", sa.String(length=320), nullable=False),
        sa.Column("contact_job_title", sa.String(length=160), nullable=False),
        sa.Column("contact_phone", sa.String(length=64), nullable=False),
        sa.Column("acting_capacity", sa.String(length=40), nullable=False),
        sa.Column("authority_declared", sa.Boolean(), nullable=False),
        sa.Column("verification_source", sa.String(length=80), nullable=True),
        sa.Column("verification_message", sa.String(length=500), nullable=True),
        sa.Column("verification_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("official_data", sa.JSON(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        op.f("ix_organization_onboardings_public_id"),
        "organization_onboardings",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_organization_onboardings_status"),
        "organization_onboardings",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_onboardings_country"),
        "organization_onboardings",
        ["country"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_onboardings_tax_id"),
        "organization_onboardings",
        ["tax_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_onboardings_contact_email"),
        "organization_onboardings",
        ["contact_email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organization_onboardings_contact_email"),
        table_name="organization_onboardings",
    )
    op.drop_index(
        op.f("ix_organization_onboardings_tax_id"),
        table_name="organization_onboardings",
    )
    op.drop_index(
        op.f("ix_organization_onboardings_country"),
        table_name="organization_onboardings",
    )
    op.drop_index(
        op.f("ix_organization_onboardings_status"),
        table_name="organization_onboardings",
    )
    op.drop_index(
        op.f("ix_organization_onboardings_public_id"),
        table_name="organization_onboardings",
    )
    op.drop_table("organization_onboardings")
