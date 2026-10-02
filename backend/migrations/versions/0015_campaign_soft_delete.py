"""Borrado lógico de campañas con historial.

Revision ID: 0015_campaign_soft_delete
Revises: 0014_campaign_activation
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_campaign_soft_delete"
down_revision: Union[str, Sequence[str], None] = "0014_campaign_activation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "campaign_seed_markers",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.execute(
        sa.text(
            "INSERT INTO campaign_seed_markers (code, seeded_at) "
            "SELECT 'WELCOME_PLATFORM', CURRENT_TIMESTAMP "
            "WHERE EXISTS (SELECT 1 FROM campaigns WHERE code = 'WELCOME_PLATFORM')"
        )
    )

def downgrade() -> None:
    op.drop_table("campaign_seed_markers")
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("deleted_at")
