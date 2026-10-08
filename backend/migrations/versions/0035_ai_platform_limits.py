"""T-217: límite diario de la IA de plataforma por persona (todas las conexiones sumadas).

Revision ID: 0035_ai_platform_limits
Revises: 0034_exercise_reports
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_ai_platform_limits"
down_revision: Union[str, Sequence[str], None] = "0034_exercise_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_platform_limits",
        sa.Column("key", sa.String(length=60), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_platform_limits")
