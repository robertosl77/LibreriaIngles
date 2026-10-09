"""T-220: lease y estado de las tareas periódicas del framework.

Revision ID: 0036_job_leases
Revises: 0035_ai_platform_limits
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_job_leases"
down_revision: Union[str, Sequence[str], None] = "0035_ai_platform_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_leases",
        sa.Column("name", sa.String(length=80), primary_key=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ok", sa.Boolean(), nullable=True),
        sa.Column("last_processed", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("job_leases")
