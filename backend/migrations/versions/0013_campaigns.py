"""Campañas configurables (T-004 etapa 2).

- campañas: trigger, condiciones, prioridad/acumulabilidad, vigencia, límites y notificación.
- campaign_grants: historial idempotente (nunca_recibió(campaña)).
- accounts: primer/último login para eventos y futuras condiciones temporales.

Revision ID: 0013_campaigns
Revises: 0012_services
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_campaigns"
down_revision: Union[str, Sequence[str], None] = "0012_services"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS = sa.Enum("DRAFT", "ACTIVE", "PAUSED", "ENDED", native_enum=False, name="campaignstatus")
TRIGGER = sa.Enum("FIRST_LOGIN", "LOGIN", "SCHEDULED", native_enum=False, name="campaigntrigger")
NOTIFICATION = sa.Enum(
    "NONE", "IN_APP", "EMAIL", "IN_APP_EMAIL", native_enum=False, name="campaignnotification"
)


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("first_login_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # Las cuentas preexistentes no deben ser consideradas "primer login" después de migrar.
    op.execute(sa.text("UPDATE accounts SET first_login_at = created_at, last_login_at = created_at"))

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("trigger", TRIGGER, nullable=False),
        sa.Column("eligibility", sa.JSON(), nullable=False),
        sa.Column("grant_days", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("stackable", sa.Boolean(), nullable=False),
        sa.Column("max_recipients", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification", NOTIFICATION, nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_campaigns_plan_id", "campaigns", ["plan_id"], unique=False)
    op.create_index("ix_campaigns_organization_id", "campaigns", ["organization_id"], unique=False)
    op.create_index("ix_campaigns_status", "campaigns", ["status"], unique=False)
    op.create_index("ix_campaigns_trigger", "campaigns", ["trigger"], unique=False)
    op.create_index("ix_campaigns_priority", "campaigns", ["priority"], unique=False)

    op.create_table(
        "campaign_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("benefit_summary", sa.String(length=300), nullable=False),
        sa.Column("notification_message", sa.String(length=500), nullable=True),
        sa.Column("in_app_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.String(length=24), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "account_id", name="uq_campaign_grant_account"),
    )
    op.create_index("ix_campaign_grants_campaign_id", "campaign_grants", ["campaign_id"], unique=False)
    op.create_index("ix_campaign_grants_account_id", "campaign_grants", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_campaign_grants_account_id", table_name="campaign_grants")
    op.drop_index("ix_campaign_grants_campaign_id", table_name="campaign_grants")
    op.drop_table("campaign_grants")
    op.drop_index("ix_campaigns_priority", table_name="campaigns")
    op.drop_index("ix_campaigns_trigger", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_organization_id", table_name="campaigns")
    op.drop_index("ix_campaigns_plan_id", table_name="campaigns")
    op.drop_table("campaigns")
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("first_login_at")
