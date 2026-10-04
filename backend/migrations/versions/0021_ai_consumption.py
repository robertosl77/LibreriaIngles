"""T-049: tokens normalizados y trazabilidad del consumo de IA.

Revision ID: 0021_ai_consumption
Revises: 0020_campaign_engine_action
Create Date: 2026-10-04
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_ai_consumption"
down_revision: Union[str, Sequence[str], None] = "0020_campaign_engine_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.add_column(sa.Column("connection_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("membership_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("service_source", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("subject_type", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("subject_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("subject_label", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("subject_route", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("total_tokens", sa.Integer(), nullable=True))
        batch.alter_column(
            "operation",
            existing_type=sa.String(length=40),
            type_=sa.String(length=80),
            existing_nullable=False,
        )
        batch.create_foreign_key(
            "fk_ai_usage_events_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_ai_usage_events_membership_id",
            "memberships",
            ["membership_id"],
            ["id"],
        )

    op.create_index(
        "ix_ai_usage_events_organization_created",
        "ai_usage_events",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_events_subject",
        "ai_usage_events",
        ["subject_type", "subject_id"],
        unique=False,
    )

    mappings = op.create_table(
        "ai_provider_usage_mappings",
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("input_tokens_path", sa.String(length=200), nullable=True),
        sa.Column("output_tokens_path", sa.String(length=200), nullable=True),
        sa.Column("total_tokens_path", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        mappings,
        [
            {
                "provider": "OPENAI",
                "input_tokens_path": "usage.prompt_tokens",
                "output_tokens_path": "usage.completion_tokens",
                "total_tokens_path": "usage.total_tokens",
                "active": True,
                "created_at": now,
            },
            {
                "provider": "GEMINI",
                "input_tokens_path": "usageMetadata.promptTokenCount",
                "output_tokens_path": "usageMetadata.candidatesTokenCount",
                "total_tokens_path": "usageMetadata.totalTokenCount",
                "active": True,
                "created_at": now,
            },
            {
                "provider": "ANTHROPIC",
                "input_tokens_path": "usage.input_tokens",
                "output_tokens_path": "usage.output_tokens",
                "total_tokens_path": None,
                "active": True,
                "created_at": now,
            },
            {
                "provider": "MOCK",
                "input_tokens_path": "usage.input_tokens",
                "output_tokens_path": "usage.output_tokens",
                "total_tokens_path": "usage.total_tokens",
                "active": True,
                "created_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_provider_usage_mappings")
    op.drop_index("ix_ai_usage_events_subject", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_organization_created", table_name="ai_usage_events")

    with op.batch_alter_table("ai_usage_events") as batch:
        batch.drop_constraint("fk_ai_usage_events_membership_id", type_="foreignkey")
        batch.drop_constraint("fk_ai_usage_events_organization_id", type_="foreignkey")
        batch.alter_column(
            "operation",
            existing_type=sa.String(length=80),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
        batch.drop_column("total_tokens")
        batch.drop_column("output_tokens")
        batch.drop_column("input_tokens")
        batch.drop_column("subject_route")
        batch.drop_column("subject_label")
        batch.drop_column("subject_id")
        batch.drop_column("subject_type")
        batch.drop_column("service_source")
        batch.drop_column("membership_id")
        batch.drop_column("organization_id")
        batch.drop_column("connection_name")
