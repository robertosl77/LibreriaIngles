"""Trazabilidad de beneficios y baja lógica.

Revision ID: 0019_benefit_traceability
Revises: 0018_connection_limits_only
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_benefit_traceability"
down_revision: Union[str, Sequence[str], None] = "0018_connection_limits_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("benefits") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(sa.Column("benefit_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_subscriptions_benefit_id_benefits",
            "benefits",
            ["benefit_id"],
            ["id"],
        )
        batch.create_index("ix_subscriptions_benefit_id", ["benefit_id"])

    bind = op.get_bind()

    bind.execute(sa.text("""
        UPDATE subscriptions
        SET benefit_id = (
            SELECT i.benefit_id
            FROM invitation_redemptions r
            JOIN invitations i ON i.id = r.invitation_id
            WHERE r.subscription_id = subscriptions.id
            ORDER BY r.redeemed_at DESC
            LIMIT 1
        )
        WHERE benefit_id IS NULL
          AND EXISTS (
            SELECT 1 FROM invitation_redemptions r
            WHERE r.subscription_id = subscriptions.id
          )
    """))

    bind.execute(sa.text("""
        UPDATE subscriptions
        SET benefit_id = (
            SELECT c.benefit_id
            FROM campaign_grants g
            JOIN campaigns c ON c.id = g.campaign_id
            WHERE g.subscription_id = subscriptions.id
            ORDER BY g.applied_at DESC
            LIMIT 1
        )
        WHERE benefit_id IS NULL
          AND EXISTS (
            SELECT 1 FROM campaign_grants g
            WHERE g.subscription_id = subscriptions.id
          )
    """))

    benefit_ids = {
        int(row[0]) for row in bind.execute(sa.text("SELECT id FROM benefits")).fetchall()
    }
    rows = bind.execute(
        sa.text("SELECT id, note FROM subscriptions WHERE benefit_id IS NULL AND note IS NOT NULL")
    ).fetchall()
    for subscription_id, note in rows:
        marker = "beneficio #"
        if marker not in note:
            continue
        raw_id = note.split(marker, 1)[1].split(":", 1)[0].strip()
        if raw_id.isdigit() and int(raw_id) in benefit_ids:
            bind.execute(
                sa.text("UPDATE subscriptions SET benefit_id = :bid WHERE id = :sid"),
                {"bid": int(raw_id), "sid": int(subscription_id)},
            )

    bind.execute(sa.text("""
        UPDATE benefits
        SET name = 'Bienvenida'
        WHERE code = 'WELCOME_PLATFORM_3D'
          AND name = 'Plataforma · 3 días'
    """))


def downgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_index("ix_subscriptions_benefit_id")
        batch.drop_constraint("fk_subscriptions_benefit_id_benefits", type_="foreignkey")
        batch.drop_column("benefit_id")

    with op.batch_alter_table("benefits") as batch:
        batch.drop_column("deleted_at")
