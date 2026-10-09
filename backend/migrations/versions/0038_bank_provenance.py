"""T-220 (N-02): procedencia de los ítems del banco de ejercicios.

Quién pagó la generación (dueño de la conexión) y en qué empresa se generó. Solo se registra:
la política de qué se comparte entre empresas o cuentas BYOK queda a decisión.

Revision ID: 0038_bank_provenance
Revises: 0037_platform_limits
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_bank_provenance"
down_revision: Union[str, Sequence[str], None] = "0037_platform_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_bank_items") as batch_op:
        batch_op.add_column(sa.Column("source_owner_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("source_owner_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_organization_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_exercise_bank_items_source_organization_id", ["source_organization_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("exercise_bank_items") as batch_op:
        batch_op.drop_index("ix_exercise_bank_items_source_organization_id")
        batch_op.drop_column("source_organization_id")
        batch_op.drop_column("source_owner_id")
        batch_op.drop_column("source_owner_type")
