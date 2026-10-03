"""Metadatos de respuestas habladas (T-026).

El audio es temporal y nunca se persiste. Solo se conserva su duración junto
con la transcripción textual.

Revision ID: 0008_speaking_audio
Revises: 0007_modalities
Create Date: 2026-09-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_speaking_audio"
down_revision: Union[str, Sequence[str], None] = "0007_modalities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("draft_answers") as batch_op:
        batch_op.add_column(sa.Column("audio_duration_ms", sa.Integer(), nullable=True))
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(sa.Column("audio_duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_column("audio_duration_ms")
    with op.batch_alter_table("draft_answers") as batch_op:
        batch_op.drop_column("audio_duration_ms")
