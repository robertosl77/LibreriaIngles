"""Referencias humanas de clases y ejercicios.

Separado de service/evaluation para que Consumo y el evaluador puedan reutilizarlo
sin crear dependencias circulares.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning.models import Exercise


def exercise_display_number(db: Session, exercise: Exercise) -> int:
    """Número visible de una actividad dentro de la clase.

    Una conversación multi-turno cuenta como una sola actividad; los turnos
    posteriores comparten el mismo número.
    """
    exercises = list(
        db.scalars(
            select(Exercise)
            .where(Exercise.class_session_id == exercise.class_session_id)
            .order_by(Exercise.position, Exercise.id)
        ).all()
    )
    number = 0
    for item in exercises:
        conversation = (item.content or {}).get("conversation") or {}
        continuation = (
            item.exercise_type == "conversation"
            and int(conversation.get("turn") or 1) > 1
        )
        if not continuation:
            number += 1
        if item.id == exercise.id:
            return max(1, number)
    return max(1, exercise.position + 1)
