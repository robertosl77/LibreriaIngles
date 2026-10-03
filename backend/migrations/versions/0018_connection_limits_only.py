"""Mover límites de pedidos completamente a conexiones de IA.

Revision ID: 0018_connection_limits_only
Revises: 0017_service_benefit_boundary
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_connection_limits_only"
down_revision: Union[str, Sequence[str], None] = "0017_service_benefit_boundary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Los límites total/per-user ya viven en ai_connections. El valor histórico de Plan no se
    # migra automáticamente porque no identifica a qué conexión debía aplicarse.
    with op.batch_alter_table("plans") as batch:
        batch.drop_column("daily_request_limit")


def downgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("daily_request_limit", sa.Integer(), nullable=True))
