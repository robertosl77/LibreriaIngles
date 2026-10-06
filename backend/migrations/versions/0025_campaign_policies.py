"""T-141: motor genérico de políticas globales de Campaigns.

Revision ID: 0025_campaign_policies
Revises: 0024_ai_usage_diagnostics
Create Date: 2026-10-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_campaign_policies"
down_revision: Union[str, Sequence[str], None] = "0024_ai_usage_diagnostics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("source_policy_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("effect", sa.String(length=24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("applies_to", sa.JSON(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_policy_id"], ["campaign_policies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_campaign_policies_organization_id"),
        "campaign_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policies_source_policy_id"),
        "campaign_policies",
        ["source_policy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policies_kind"),
        "campaign_policies",
        ["kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policies_enabled"),
        "campaign_policies",
        ["enabled"],
        unique=False,
    )

    op.create_table(
        "campaign_policy_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("policy_kind", sa.String(length=40), nullable=False),
        sa.Column("policy_name", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("rule_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["campaign_policies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_campaign_policy_blocks_policy_id"),
        "campaign_policy_blocks",
        ["policy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policy_blocks_campaign_id"),
        "campaign_policy_blocks",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policy_blocks_account_id"),
        "campaign_policy_blocks",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_policy_blocks_created_at"),
        "campaign_policy_blocks",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_campaign_policy_blocks_created_at"), table_name="campaign_policy_blocks")
    op.drop_index(op.f("ix_campaign_policy_blocks_account_id"), table_name="campaign_policy_blocks")
    op.drop_index(op.f("ix_campaign_policy_blocks_campaign_id"), table_name="campaign_policy_blocks")
    op.drop_index(op.f("ix_campaign_policy_blocks_policy_id"), table_name="campaign_policy_blocks")
    op.drop_table("campaign_policy_blocks")

    op.drop_index(op.f("ix_campaign_policies_enabled"), table_name="campaign_policies")
    op.drop_index(op.f("ix_campaign_policies_kind"), table_name="campaign_policies")
    op.drop_index(op.f("ix_campaign_policies_source_policy_id"), table_name="campaign_policies")
    op.drop_index(op.f("ix_campaign_policies_organization_id"), table_name="campaign_policies")
    op.drop_table("campaign_policies")
