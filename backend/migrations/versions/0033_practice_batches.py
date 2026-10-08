"""T-214: tanda de cada ejercicio en la práctica continua.

Revision ID: 0033_practice_batches
Revises: 0032_exercise_bank
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_practice_batches"
down_revision: Union[str, Sequence[str], None] = "0032_exercise_bank"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("batch", sa.Integer(), nullable=False, server_default=sa.text("1")))


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.drop_column("batch")
