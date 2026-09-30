"""T-006: límites de consumo y registro de uso de IA.

Revision ID: 0003_platform_ai_usage
Revises: 0002_learning_flow
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_platform_ai_usage"
down_revision: Union[str, Sequence[str], None] = "0002_learning_flow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_connections") as batch_op:
        batch_op.add_column(sa.Column("daily_request_limit", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("per_account_daily_limit", sa.Integer(), nullable=True))

    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column(
            "owner_type",
            sa.Enum("PLATFORM", "ORGANIZATION", "ACCOUNT", name="aiconnectionownertype", native_enum=False),
            nullable=False,
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["ai_connections.id"],
            name="fk_ai_usage_events_connection_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_ai_usage_events_account_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_events_created_at", "ai_usage_events", ["created_at"])
    op.create_index(
        "ix_ai_usage_events_connection_created",
        "ai_usage_events",
        ["connection_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_events_account_created",
        "ai_usage_events",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_account_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_connection_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_created_at", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")

    with op.batch_alter_table("ai_connections") as batch_op:
        batch_op.drop_column("per_account_daily_limit")
        batch_op.drop_column("daily_request_limit")
