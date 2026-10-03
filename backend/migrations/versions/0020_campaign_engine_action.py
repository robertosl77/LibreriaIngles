"""Evolución del motor de campañas: acción explícita.

Revision ID: 0020_campaign_engine_action
Revises: 0019_benefit_traceability
Create Date: 2026-10-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_campaign_engine_action"
down_revision: Union[str, Sequence[str], None] = "0019_benefit_traceability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(
            sa.Column(
                "action",
                sa.String(length=40),
                nullable=False,
                server_default="GRANT_BENEFIT",
            )
        )
        batch.add_column(sa.Column("action_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("action_config")
        batch.drop_column("action")
