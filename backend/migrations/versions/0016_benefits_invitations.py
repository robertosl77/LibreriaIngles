"""Beneficios reutilizables e invitaciones genéricas (T-004 etapa 3).

Revision ID: 0016_benefits_invitations
Revises: 0015_campaign_soft_delete
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_benefits_invitations"
down_revision: Union[str, Sequence[str], None] = "0015_campaign_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BENEFIT_POLICY = sa.Enum(
    "EXTEND_SAME_SERVICE", native_enum=False, name="benefitconflictpolicy"
)
RECIPIENT_MODE = sa.Enum("NAMED", "OPEN", native_enum=False, name="invitationrecipientmode")


def upgrade() -> None:
    op.create_table(
        "benefits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("conflict_policy", BENEFIT_POLICY, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_benefits_plan_id", "benefits", ["plan_id"], unique=False)
    op.create_index(
        "ix_benefits_organization_id", "benefits", ["organization_id"], unique=False
    )

    # Cada campaña existente conserva exactamente su servicio/duración, pero ahora mediante
    # una definición reusable. La bienvenida recibe un código estable para el seeding runtime.
    op.execute(
        sa.text(
            """
            INSERT INTO benefits
                (code, name, plan_id, organization_id, duration_days, conflict_policy,
                 active, created_by_account_id, created_at, updated_at)
            SELECT
                CASE
                    WHEN c.code = 'WELCOME_PLATFORM' THEN 'WELCOME_PLATFORM_3D'
                    ELSE 'MIGRATED_CAMPAIGN_' || CAST(c.id AS VARCHAR)
                END,
                CASE
                    WHEN c.code = 'WELCOME_PLATFORM' THEN 'Plataforma · 3 días'
                    ELSE c.name || ' · beneficio'
                END,
                c.plan_id,
                c.organization_id,
                c.grant_days,
                'EXTEND_SAME_SERVICE',
                TRUE,
                c.created_by_account_id,
                c.created_at,
                c.updated_at
            FROM campaigns c
            """
        )
    )

    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(sa.Column("benefit_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_campaigns_benefit_id_benefits",
            "benefits",
            ["benefit_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE campaigns
            SET benefit_id = (
                SELECT b.id
                FROM benefits b
                WHERE b.code = CASE
                    WHEN campaigns.code = 'WELCOME_PLATFORM' THEN 'WELCOME_PLATFORM_3D'
                    ELSE 'MIGRATED_CAMPAIGN_' || CAST(campaigns.id AS VARCHAR)
                END
            )
            """
        )
    )
    op.drop_index("ix_campaigns_plan_id", table_name="campaigns")
    with op.batch_alter_table("campaigns") as batch:
        batch.alter_column("benefit_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("grant_days")
        batch.drop_column("plan_id")
    op.create_index("ix_campaigns_benefit_id", "campaigns", ["benefit_id"], unique=False)

    # La tabla inicial de invitations era un boceto B2B sin uso. Se conserva la identidad/token
    # pero se migra de forma segura a CANCELLED porque no tenía servicio/beneficio asociado.
    op.drop_index("uq_pending_invitation_org_email", table_name="invitations")
    with op.batch_alter_table("invitations") as batch:
        batch.add_column(sa.Column("created_by_account_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("benefit_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("recipient_mode", RECIPIENT_MODE, nullable=True))
        batch.add_column(sa.Column("token_encrypted", sa.String(length=4000), nullable=True))
        batch.add_column(sa.Column("max_redemptions", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("email_status", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_invitations_created_by_accounts",
            "accounts",
            ["created_by_account_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_invitations_benefit_id_benefits",
            "benefits",
            ["benefit_id"],
            ["id"],
        )
        batch.alter_column(
            "organization_id", existing_type=sa.Integer(), nullable=True
        )
        batch.alter_column(
            "email", existing_type=sa.String(length=320), nullable=True
        )
        batch.alter_column(
            "expires_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )

    op.execute(
        sa.text(
            """
            UPDATE invitations
            SET name = COALESCE(email, 'Invitación migrada #' || CAST(id AS VARCHAR)),
                recipient_mode = 'NAMED',
                max_redemptions = 1,
                status = 'CANCELLED',
                updated_at = created_at
            """
        )
    )

    with op.batch_alter_table("invitations") as batch:
        batch.alter_column("name", existing_type=sa.String(length=120), nullable=False)
        batch.alter_column("recipient_mode", existing_type=RECIPIENT_MODE, nullable=False)
        batch.alter_column("max_redemptions", existing_type=sa.Integer(), nullable=False)
        batch.alter_column(
            "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch.drop_column("accepted_at")
        batch.drop_column("role")

    op.create_index("ix_invitations_benefit_id", "invitations", ["benefit_id"], unique=False)
    op.create_index("ix_invitations_status", "invitations", ["status"], unique=False)

    op.create_table(
        "invitation_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invitation_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("benefit_summary", sa.String(length=300), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invitation_id",
            "account_id",
            name="uq_invitation_redemption_account",
        ),
    )
    op.create_index(
        "ix_invitation_redemptions_invitation_id",
        "invitation_redemptions",
        ["invitation_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitation_redemptions_account_id",
        "invitation_redemptions",
        ["account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invitation_redemptions_account_id",
        table_name="invitation_redemptions",
    )
    op.drop_index(
        "ix_invitation_redemptions_invitation_id",
        table_name="invitation_redemptions",
    )
    op.drop_table("invitation_redemptions")

    # El esquema anterior no puede representar links abiertos ni beneficios; un downgrade
    # descarta invitaciones creadas por esta versión.
    op.execute(sa.text("DELETE FROM invitations"))
    op.drop_index("ix_invitations_status", table_name="invitations")
    op.drop_index("ix_invitations_benefit_id", table_name="invitations")

    OLD_ROLE = sa.Enum("ADMIN", "STUDENT", native_enum=False, name="membershiprole")
    with op.batch_alter_table("invitations") as batch:
        batch.drop_constraint(
            "fk_invitations_benefit_id_benefits", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_invitations_created_by_accounts", type_="foreignkey"
        )
        batch.add_column(sa.Column("role", OLD_ROLE, nullable=True))
        batch.add_column(
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.alter_column(
            "organization_id", existing_type=sa.Integer(), nullable=False
        )
        batch.alter_column(
            "email", existing_type=sa.String(length=320), nullable=False
        )
        batch.alter_column(
            "expires_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch.drop_column("updated_at")
        batch.drop_column("cancelled_at")
        batch.drop_column("email_status")
        batch.drop_column("max_redemptions")
        batch.drop_column("token_encrypted")
        batch.drop_column("recipient_mode")
        batch.drop_column("name")
        batch.drop_column("benefit_id")
        batch.drop_column("created_by_account_id")

    with op.batch_alter_table("invitations") as batch:
        batch.alter_column("role", existing_type=OLD_ROLE, nullable=False)

    op.create_index(
        "uq_pending_invitation_org_email",
        "invitations",
        ["organization_id", "email"],
        unique=True,
        sqlite_where=sa.text("status = 'PENDING'"),
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.drop_index("ix_campaigns_benefit_id", table_name="campaigns")
    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("grant_days", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_campaigns_plan_id_plans",
            "plans",
            ["plan_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE campaigns
            SET plan_id = (
                    SELECT b.plan_id FROM benefits b WHERE b.id = campaigns.benefit_id
                ),
                grant_days = (
                    SELECT b.duration_days FROM benefits b WHERE b.id = campaigns.benefit_id
                )
            """
        )
    )

    with op.batch_alter_table("campaigns") as batch:
        batch.alter_column("plan_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint(
            "fk_campaigns_benefit_id_benefits", type_="foreignkey"
        )
        batch.drop_column("benefit_id")
    op.create_index("ix_campaigns_plan_id", "campaigns", ["plan_id"], unique=False)

    op.drop_index("ix_benefits_organization_id", table_name="benefits")
    op.drop_index("ix_benefits_plan_id", table_name="benefits")
    op.drop_table("benefits")
