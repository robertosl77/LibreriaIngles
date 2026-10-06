"""P01: catálogo reutilizable de cargos/funciones.

Revision ID: 0027_job_titles
Revises: 0026_organization_onboarding
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0027_job_titles"
down_revision: Union[str, Sequence[str], None] = "0026_organization_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_titles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_titles_normalized_name"),
        "job_titles",
        ["normalized_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_job_titles_active"),
        "job_titles",
        ["active"],
        unique=False,
    )

    with op.batch_alter_table("organization_onboardings") as batch:
        batch.add_column(sa.Column("contact_job_title_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_org_onboarding_job_title",
            "job_titles",
            ["contact_job_title_id"],
            ["id"],
        )
        batch.create_index(
            op.f("ix_organization_onboardings_contact_job_title_id"),
            ["contact_job_title_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("organization_onboardings") as batch:
        batch.drop_index(op.f("ix_organization_onboardings_contact_job_title_id"))
        batch.drop_constraint("fk_org_onboarding_job_title", type_="foreignkey")
        batch.drop_column("contact_job_title_id")

    op.drop_index(op.f("ix_job_titles_active"), table_name="job_titles")
    op.drop_index(op.f("ix_job_titles_normalized_name"), table_name="job_titles")
    op.drop_table("job_titles")
