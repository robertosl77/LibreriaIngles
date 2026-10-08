"""T-203: las clases/exámenes que no se pudieron generar dejan de existir como clase.

Desde T-203 una clase solo se guarda si la IA respondió bien. Las que quedaron en
GENERATION_FAILED (sin ejercicios) se borran; sus intentos de IA siguen en Consumo, sin número de
clase ("Clase · no generada" / "Examen · no generado"), para no perder el gasto ni la regla de
campañas CLASSES_GENERATION_FAILED.

Revision ID: 0031_drop_failed_class_sessions
Revises: 0030_owner_connections_to_platform
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_drop_failed_class_sessions"
down_revision: Union[str, Sequence[str], None] = "0030_owner_connections_to_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LABELS = {"CLASS": ("CLASS_NOT_GENERATED", "Clase · no generada"), "EXAM": ("EXAM_NOT_GENERATED", "Examen · no generado")}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT s.id, s.kind FROM class_sessions s WHERE s.status = 'GENERATION_FAILED' "
        "AND NOT EXISTS (SELECT 1 FROM exercises e WHERE e.class_session_id = s.id) "
        "AND NOT EXISTS (SELECT 1 FROM draft_answers d WHERE d.class_session_id = s.id)"
    )).all()
    for session_id, kind in rows:
        subject_type, label = LABELS.get(kind, LABELS["CLASS"])
        bind.execute(
            sa.text(
                "UPDATE ai_usage_events SET subject_type = :t, subject_id = NULL, subject_label = :l, "
                "subject_route = NULL WHERE subject_type = :k AND subject_id = :id"
            ),
            {"t": subject_type, "l": label, "k": kind, "id": session_id},
        )
        bind.execute(sa.text("DELETE FROM class_sessions WHERE id = :id"), {"id": session_id})


def downgrade() -> None:
    # Las clases borradas no tenían contenido: no se recrean.
    pass
