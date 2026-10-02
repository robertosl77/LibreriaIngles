"""Persistir momento de activación de campañas.

Revision ID: 0014_campaign_activation
Revises: 0013_campaigns
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_campaign_activation"
down_revision: Union[str, Sequence[str], None] = "0013_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE campaigns "
            "SET activated_at = updated_at "
            "WHERE status = 'ACTIVE' AND activated_at IS NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("activated_at")
