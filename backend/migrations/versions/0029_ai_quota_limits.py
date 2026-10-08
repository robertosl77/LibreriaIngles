"""T-191: capa proveedor + capa normalizada de límites de IA.

Revision ID: 0029_ai_quota_limits
Revises: 0028_email_verification_challenges
Create Date: 2026-10-07
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_ai_quota_limits"
down_revision: Union[str, Sequence[str], None] = "0028_email_verification_challenges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reglas iniciales congeladas (no importar código de la app desde una migración).
INITIAL_LIMIT_MAPPINGS = {'GEMINI': {'violations': {'items': 'error.details[].violations[]',
                           'id': 'quotaId',
                           'value': 'quotaValue',
                           'model': 'quotaDimensions.model'},
            'retryDelay': 'error.details[].retryDelay',
            'keywords': {'window': [['PerMinute', 'MINUTE'], ['PerDay', 'DAY']],
                         'dimension': [['InputTokens', 'INPUT_TOKENS'],
                                       ['OutputTokens', 'OUTPUT_TOKENS'],
                                       ['Tokens', 'TOKENS'],
                                       ['Requests', 'REQUESTS']],
                         'tier': [['FreeTier', 'free']]},
            'headers': [],
            'retryAfterHeader': 'retry-after',
            'dayResetTimezone': 'America/Los_Angeles',
            'classify': [{'contains': ['prepayment',
                                       'credits are depleted',
                                       'billing account',
                                       'billing details are'],
                          'kind': 'EXHAUSTED'}],
            'renewableStatuses': [429]},
 'OPENAI': {'headers': [{'dimension': 'REQUESTS',
                         'window': 'MINUTE',
                         'limit': 'x-ratelimit-limit-requests',
                         'remaining': 'x-ratelimit-remaining-requests',
                         'reset': 'x-ratelimit-reset-requests'},
                        {'dimension': 'TOKENS',
                         'window': 'MINUTE',
                         'limit': 'x-ratelimit-limit-tokens',
                         'remaining': 'x-ratelimit-remaining-tokens',
                         'reset': 'x-ratelimit-reset-tokens'}],
            'retryAfterHeader': 'retry-after',
            'classify': [{'contains': ['insufficient_quota'], 'kind': 'EXHAUSTED'}],
            'renewableStatuses': [429]},
 'ANTHROPIC': {'headers': [{'dimension': 'REQUESTS',
                            'window': 'MINUTE',
                            'limit': 'anthropic-ratelimit-requests-limit',
                            'remaining': 'anthropic-ratelimit-requests-remaining',
                            'reset': 'anthropic-ratelimit-requests-reset'},
                           {'dimension': 'TOKENS',
                            'window': 'MINUTE',
                            'limit': 'anthropic-ratelimit-tokens-limit',
                            'remaining': 'anthropic-ratelimit-tokens-remaining',
                            'reset': 'anthropic-ratelimit-tokens-reset'},
                           {'dimension': 'INPUT_TOKENS',
                            'window': 'MINUTE',
                            'limit': 'anthropic-ratelimit-input-tokens-limit',
                            'remaining': 'anthropic-ratelimit-input-tokens-remaining',
                            'reset': 'anthropic-ratelimit-input-tokens-reset'},
                           {'dimension': 'OUTPUT_TOKENS',
                            'window': 'MINUTE',
                            'limit': 'anthropic-ratelimit-output-tokens-limit',
                            'remaining': 'anthropic-ratelimit-output-tokens-remaining',
                            'reset': 'anthropic-ratelimit-output-tokens-reset'}],
               'retryAfterHeader': 'retry-after',
               'classify': [{'contains': ['enforced_spend_limit_reached',
                                          'credit balance',
                                          'specified api usage limits'],
                             'kind': 'EXHAUSTED'}],
               'renewableStatuses': [429]},
 'MOCK': {'violations': {'items': 'error.details[].violations[]',
                         'id': 'quotaId',
                         'value': 'quotaValue',
                         'model': 'quotaDimensions.model'},
          'retryDelay': 'error.details[].retryDelay',
          'keywords': {'window': [['PerMinute', 'MINUTE'], ['PerDay', 'DAY']],
                       'dimension': [['InputTokens', 'INPUT_TOKENS'],
                                     ['OutputTokens', 'OUTPUT_TOKENS'],
                                     ['Tokens', 'TOKENS'],
                                     ['Requests', 'REQUESTS']],
                       'tier': [['FreeTier', 'free']]},
          'headers': [{'dimension': 'REQUESTS',
                       'window': 'MINUTE',
                       'limit': 'x-ratelimit-limit-requests',
                       'remaining': 'x-ratelimit-remaining-requests',
                       'reset': 'x-ratelimit-reset-requests'},
                      {'dimension': 'TOKENS',
                       'window': 'MINUTE',
                       'limit': 'x-ratelimit-limit-tokens',
                       'remaining': 'x-ratelimit-remaining-tokens',
                       'reset': 'x-ratelimit-reset-tokens'}],
          'retryAfterHeader': 'retry-after',
          'dayResetTimezone': 'America/Los_Angeles',
          'classify': [{'contains': ['insufficient_quota', 'credits are depleted'],
                        'kind': 'EXHAUSTED'}],
          'renewableStatuses': [429]}}


def upgrade() -> None:
    mappings = op.create_table(
        "ai_provider_limit_mappings",
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_table(
        "ai_quota_limits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("dimension", sa.String(length=20), nullable=False),
        sa.Column("window", sa.String(length=10), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("remaining", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["ai_connections.id"],
            name="fk_ai_quota_limits_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_ai_quota_limits_key",
        "ai_quota_limits",
        ["connection_id", "model", "dimension", "window"],
        unique=True,
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        mappings,
        [
            {"provider": provider, "rules": rules, "active": True, "created_at": now}
            for provider, rules in INITIAL_LIMIT_MAPPINGS.items()
        ],
    )


def downgrade() -> None:
    op.drop_index("ux_ai_quota_limits_key", table_name="ai_quota_limits")
    op.drop_table("ai_quota_limits")
    op.drop_table("ai_provider_limit_mappings")
