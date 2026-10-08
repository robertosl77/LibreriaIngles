"""T-212 · Banco de ejercicios (épica T-210 #299).

El banco se llena con el uso: cada ejercicio de práctica que la IA genera y pasa la validación se
guarda acá, compartido por nivel · tema · tipo. Más adelante (T-213) las clases se arman primero
desde el banco y solo lo que falte se pide a la IA.

Quedan afuera por ahora:
- Exámenes: sus ítems no se mezclan con la práctica (no se practica el examen).
- Conversación: los turnos dependen del par y del cierre; se reusan como par en otra etapa.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.normalize import normalize_answer
from app.learning.models import BankItemStatus, ExerciseBankItem, Exercise

NOT_BANKED_TYPES = {"conversation"}
# Campos del contenido que dependen de la clase concreta y no del ejercicio.
_VOLATILE_CONTENT = {"conversation"}


def fingerprint(exercise: Exercise) -> str:
    content = {k: v for k, v in (exercise.content or {}).items() if k not in _VOLATILE_CONTENT}
    raw = "|".join(
        [
            exercise.level or "",
            exercise.skill_key or "",
            exercise.exercise_type,
            normalize_answer(exercise.instruction or ""),
            normalize_answer(exercise.prompt or ""),
            json.dumps(content, sort_keys=True, ensure_ascii=False),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bankable(exercise: Exercise) -> bool:
    return bool(exercise.level and exercise.skill_key) and exercise.exercise_type not in NOT_BANKED_TYPES


def store(db: Session, exercise: Exercise, *, provider: str | None, model: str | None,
          session_id: int | None) -> ExerciseBankItem | None:
    """Guarda (o reconoce) el ejercicio en el banco y lo vincula. Devuelve el ítem."""
    if not bankable(exercise):
        return None
    key = fingerprint(exercise)
    item = db.scalar(select(ExerciseBankItem).where(ExerciseBankItem.fingerprint == key))
    if item is None:
        item = ExerciseBankItem(
            fingerprint=key,
            level=exercise.level,
            area=exercise.area,
            skill_key=exercise.skill_key,
            exercise_type=exercise.exercise_type,
            presentation_mode=exercise.presentation_mode,
            response_mode=exercise.response_mode,
            instruction=exercise.instruction,
            prompt=exercise.prompt,
            content={k: v for k, v in (exercise.content or {}).items() if k not in _VOLATILE_CONTENT},
            expected_concepts=list(exercise.expected_concepts or []),
            answer_key=dict(exercise.answer_key or {}),
            evaluation_mode=exercise.evaluation_mode,
            status=BankItemStatus.ACTIVE,
            source_provider=provider,
            source_model=model,
            source_session_id=session_id,
            times_served=1,
        )
        db.add(item)
        db.flush()
    else:
        item.times_served = (item.times_served or 0) + 1
    exercise.bank_item_id = item.id
    return item
