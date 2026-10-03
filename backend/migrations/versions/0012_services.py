"""Servicios y suscripciones (T-004 etapa 1).

Enciende las tablas `plans` (servicios) y `subscriptions` de la migración inicial:
- plans: vínculo (PERSONAL/CORPORATE), duración, tope diario provisorio, descripción.
- subscriptions: vencimiento, origen y quién la otorgó.
- Siembra los servicios "Individual" (propias keys / plataforma / híbrido).

Revision ID: 0012_services
Revises: 0011_ai_credential_audit
Create Date: 2026-10-01
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_services"
down_revision: Union[str, Sequence[str], None] = "0011_ai_credential_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LINK = sa.Enum("PERSONAL", "CORPORATE", native_enum=False, name="servicelinktype")
ORIGIN = sa.Enum("MANUAL", "CAMPAIGN", "INVITATION", "PAYMENT", native_enum=False, name="subscriptionorigin")

SEED = [
    ("INDIVIDUAL_BYOK", "Individual · propias keys", "BYOK", "Usás tus propias API keys."),
    ("INDIVIDUAL_PLATFORM", "Individual · Plataforma", "PLATFORM", "Usás la IA de Librería Inglés."),
    ("INDIVIDUAL_HYBRID", "Individual · Híbrido", "HYBRID", "Tus API keys primero; si fallan, la IA de Librería Inglés."),
]


def upgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("link_type", LINK, nullable=False, server_default="PERSONAL"))
        batch.add_column(sa.Column("duration_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("daily_request_limit", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("description", sa.String(length=300), nullable=True))
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("origin", ORIGIN, nullable=False, server_default="MANUAL"))
        batch.add_column(sa.Column("granted_by_account_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("note", sa.String(length=200), nullable=True))
        batch.create_foreign_key(
            "fk_subscriptions_granted_by", "accounts", ["granted_by_account_id"], ["id"]
        )
        batch.create_index("ix_subscriptions_account_id", ["account_id"])

    plans = sa.table(
        "plans",
        sa.column("code", sa.String), sa.column("name", sa.String), sa.column("ai_source", sa.String),
        sa.column("active", sa.Boolean), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("link_type", sa.String), sa.column("description", sa.String),
    )
    existing = {row[0] for row in op.get_bind().execute(sa.text("SELECT code FROM plans"))}
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        plans,
        [
            {"code": code, "name": name, "ai_source": source, "active": True, "created_at": now,
             "link_type": "PERSONAL", "description": description}
            for code, name, source, description in SEED
            if code not in existing
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM plans WHERE code IN ('INDIVIDUAL_BYOK','INDIVIDUAL_PLATFORM','INDIVIDUAL_HYBRID')"))
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_index("ix_subscriptions_account_id")
        batch.drop_constraint("fk_subscriptions_granted_by", type_="foreignkey")
        batch.drop_column("note")
        batch.drop_column("granted_by_account_id")
        batch.drop_column("origin")
        batch.drop_column("expires_at")
    with op.batch_alter_table("plans") as batch:
        batch.drop_column("description")
        batch.drop_column("daily_request_limit")
        batch.drop_column("duration_days")
        batch.drop_column("link_type")
