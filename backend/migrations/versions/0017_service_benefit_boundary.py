"""Separar Servicio de Beneficio: la duración vive solo en Benefit.

Revision ID: 0017_service_benefit_boundary
Revises: 0016_benefits_invitations
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_service_benefit_boundary"
down_revision: Union[str, Sequence[str], None] = "0016_benefits_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # En 0016, duration_days=NULL significaba "usar duración del plan". Materializamos ese valor
    # antes de borrar la columna para conservar exactamente los futuros otorgamientos existentes.
    op.execute(
        sa.text(
            """
            UPDATE benefits
            SET duration_days = (
                SELECT p.duration_days
                FROM plans p
                WHERE p.id = benefits.plan_id
            )
            WHERE duration_days IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM plans p
                  WHERE p.id = benefits.plan_id
                    AND p.duration_days IS NOT NULL
              )
            """
        )
    )

    # Si existía un servicio con duración propia pero nunca se había creado un Benefit para él,
    # preservamos esa configuración como un beneficio explícito.
    op.execute(
        sa.text(
            """
            INSERT INTO benefits
                (code, name, plan_id, organization_id, duration_days, conflict_policy,
                 active, created_by_account_id, created_at, updated_at)
            SELECT
                'MIGRATED_PLAN_' || CAST(p.id AS VARCHAR),
                p.name || ' · ' || CAST(p.duration_days AS VARCHAR) || ' días',
                p.id,
                NULL,
                p.duration_days,
                'EXTEND_SAME_SERVICE',
                p.active,
                NULL,
                p.created_at,
                p.created_at
            FROM plans p
            WHERE p.duration_days IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM benefits b WHERE b.plan_id = p.id
              )
            """
        )
    )

    with op.batch_alter_table("plans") as batch:
        batch.drop_column("duration_days")


def downgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("duration_days", sa.Integer(), nullable=True))

    # Solo puede recuperarse una duración de plan sin ambigüedad si todos sus beneficios con
    # duración comparten el mismo valor. En otro caso se deja NULL (sin default implícito).
    op.execute(
        sa.text(
            """
            UPDATE plans
            SET duration_days = (
                SELECT MIN(b.duration_days)
                FROM benefits b
                WHERE b.plan_id = plans.id
                  AND b.duration_days IS NOT NULL
            )
            WHERE (
                SELECT COUNT(DISTINCT b.duration_days)
                FROM benefits b
                WHERE b.plan_id = plans.id
                  AND b.duration_days IS NOT NULL
            ) = 1
            """
        )
    )
