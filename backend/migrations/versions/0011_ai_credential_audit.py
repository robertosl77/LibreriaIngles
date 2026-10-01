"""Auditoría de revelado/copia de API keys por PLATFORM_OWNER (T-042).

Revision ID: 0011_ai_credential_audit
Revises: 0010_answer_signals
Create Date: 2026-10-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_ai_credential_audit"
down_revision: Union[str, Sequence[str], None] = "0010_answer_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_credential_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("connection_name", sa.String(length=120), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_ai_credential_audit_account_id",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["ai_connections.id"],
            name="fk_ai_credential_audit_connection_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_credential_audit_events_created_at",
        "ai_credential_audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_credential_audit_connection_created",
        "ai_credential_audit_events",
        ["connection_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_credential_audit_account_created",
        "ai_credential_audit_events",
        ["account_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_credential_audit_account_created",
        table_name="ai_credential_audit_events",
    )
    op.drop_index(
        "ix_ai_credential_audit_connection_created",
        table_name="ai_credential_audit_events",
    )
    op.drop_index(
        "ix_ai_credential_audit_events_created_at",
        table_name="ai_credential_audit_events",
    )
    op.drop_table("ai_credential_audit_events")
