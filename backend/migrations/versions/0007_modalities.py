"""Modalidades de presentación y respuesta (T-025).

Listening/Speaking no son tipos de ejercicio: el mismo tipo (fill_blank,
multiple_choice, rewrite...) puede presentarse READ/LISTEN y responderse
WRITE/SELECT/SPEAK.

Revision ID: 0007_modalities
Revises: 0006_level_exams
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_modalities"
down_revision: Union[str, Sequence[str], None] = "0006_level_exams"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _presentation() -> sa.Enum:
    return sa.Enum("READ", "LISTEN", name="presentationmode", native_enum=False, length=10)


def _response() -> sa.Enum:
    return sa.Enum("WRITE", "SELECT", "SPEAK", name="responsemode", native_enum=False, length=10)


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column("presentation_mode", _presentation(), nullable=False, server_default="READ")
        )
        batch_op.add_column(
            sa.Column("response_mode", _response(), nullable=False, server_default="WRITE")
        )
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(
            sa.Column("response_mode", _response(), nullable=False, server_default="WRITE")
        )
    # Los ejercicios de opción múltiple existentes se responden seleccionando.
    op.execute(
        "UPDATE exercises SET response_mode = 'SELECT' "
        "WHERE exercise_type IN ('multiple_choice', 'reading_multiple_choice')"
    )
    op.execute(
        "UPDATE attempts SET response_mode = 'SELECT' WHERE exercise_id IN ("
        "SELECT id FROM exercises WHERE response_mode = 'SELECT')"
    )


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_column("response_mode")
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_column("response_mode")
        batch_op.drop_column("presentation_mode")
