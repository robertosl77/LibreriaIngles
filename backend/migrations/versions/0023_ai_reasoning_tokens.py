"""T-147: tokens de pensamiento/reasoning normalizados.

Revision ID: 0023_ai_reasoning_tokens
Revises: 0022_ai_usage_execution
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_ai_reasoning_tokens"
down_revision: Union[str, Sequence[str], None] = "0022_ai_usage_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_events") as batch:
        batch.add_column(sa.Column("reasoning_tokens", sa.Integer(), nullable=True))

    with op.batch_alter_table("ai_provider_usage_mappings") as batch:
        batch.add_column(
            sa.Column("reasoning_tokens_path", sa.String(length=200), nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE ai_provider_usage_mappings
            SET reasoning_tokens_path = 'usageMetadata.thoughtsTokenCount'
            WHERE provider = 'GEMINI'
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("ai_provider_usage_mappings") as batch:
        batch.drop_column("reasoning_tokens_path")

    with op.batch_alter_table("ai_usage_events") as batch:
        batch.drop_column("reasoning_tokens")
