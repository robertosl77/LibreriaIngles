"""T-200: las conexiones "propias" de sr.macros pasan a ser las de la plataforma.

sr.macros (PLATFORM_OWNER) tenía dos listas: IA → "Tus conexiones" (dueño = su cuenta) y
Plataforma → "Conexiones de la plataforma". Desde T-200 hay una sola, en el menú IA, y es la de la
plataforma (la usa él y la heredan los servicios Plataforma). Esta migración mueve sus conexiones
de cuenta a la plataforma; si el nombre ya existe en la plataforma, se agrega " (2)", " (3)"…

Revision ID: 0030_owner_connections_to_platform
Revises: 0029_ai_quota_limits
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_owner_connections_to_platform"
down_revision: Union[str, Sequence[str], None] = "0029_ai_quota_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _key(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def upgrade() -> None:
    bind = op.get_bind()
    owners = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM accounts WHERE platform_role = 'PLATFORM_OWNER'"
    ))]
    if not owners:
        return
    taken = {_key(row[0]) for row in bind.execute(sa.text(
        "SELECT name FROM ai_connections WHERE owner_type = 'PLATFORM'"
    ))}
    rows = bind.execute(
        sa.text(
            "SELECT id, name FROM ai_connections WHERE owner_type = 'ACCOUNT' "
            "AND owner_id IN :owners ORDER BY id"
        ).bindparams(sa.bindparam("owners", expanding=True)),
        {"owners": owners},
    ).all()
    for connection_id, name in rows:
        new_name, n = name, 2
        while _key(new_name) in taken:
            new_name, n = f"{name} ({n})", n + 1
        taken.add(_key(new_name))
        bind.execute(
            sa.text(
                "UPDATE ai_connections SET owner_type = 'PLATFORM', owner_id = NULL, name = :name "
                "WHERE id = :id"
            ),
            {"name": new_name, "id": connection_id},
        )


def downgrade() -> None:
    # No se puede saber cuáles eran "propias": quedan como conexiones de la plataforma.
    pass
