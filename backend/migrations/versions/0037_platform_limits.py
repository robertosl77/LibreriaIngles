"""T-220 (N-01): límites en un solo lugar.

- `ai_platform_limits` (T-217) pasa a ser `platform_limits`: valores de plataforma de cualquier
  límite declarado en el catálogo único (app/limits/registry.py). Los datos se conservan.
- `plans.limits`: valores propios de cada plan (clave ausente = hereda la plataforma).

Revision ID: 0037_platform_limits
Revises: 0036_job_leases
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_platform_limits"
down_revision: Union[str, Sequence[str], None] = "0036_job_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("ai_platform_limits", "platform_limits")
    with op.batch_alter_table("plans") as batch_op:
        batch_op.add_column(sa.Column("limits", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_column("limits")
    op.rename_table("platform_limits", "ai_platform_limits")
