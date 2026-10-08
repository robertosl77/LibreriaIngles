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


# ---------------------------------------------------------------- T-213: elegir del banco


def seen_item_ids(db: Session, study_profile_id: int, *, days: int) -> set[int]:
    """Ítems del banco que el alumno ya vio dentro de la ventana de no-repetición (#282)."""
    from datetime import timedelta

    from app.ai.models import utcnow

    since = utcnow() - timedelta(days=days)
    rows = db.scalars(
        select(Exercise.bank_item_id).where(
            Exercise.study_profile_id == study_profile_id,
            Exercise.bank_item_id.is_not(None),
            Exercise.created_at >= since,
        )
    ).all()
    return set(rows)


def pick(db: Session, slot: dict, level: str, *, exclude: set[int]) -> ExerciseBankItem | None:
    """Un ítem ACTIVO del banco para el pedido: mismo nivel, tema, tipo y modalidades; no visto.
    Prefiere los menos servidos (reparte el uso y da datos de calidad de todos)."""
    types = [t for t in slot.get("allowedTypes") or [] if t not in NOT_BANKED_TYPES]
    if not types or slot.get("conversationGroup"):
        return None
    query = (
        select(ExerciseBankItem)
        .where(
            ExerciseBankItem.level == level,
            ExerciseBankItem.skill_key == slot.get("skillKey"),
            ExerciseBankItem.exercise_type.in_(types),
            ExerciseBankItem.status == BankItemStatus.ACTIVE,
            ExerciseBankItem.presentation_mode == slot.get("presentation", "READ"),
            ExerciseBankItem.response_mode == slot.get("response", "WRITE"),
        )
        .order_by(ExerciseBankItem.times_served, ExerciseBankItem.id)
    )
    if exclude:
        query = query.where(ExerciseBankItem.id.not_in(exclude))
    return db.scalars(query.limit(1)).first()


def assign(db: Session, slots: list[dict], level: str, study_profile_id: int, *, days: int) -> int:
    """Marca en cada slot el ítem del banco que lo cubre (`bankItemId`). Devuelve cuántos cubrió."""
    exclude = seen_item_ids(db, study_profile_id, days=days)
    covered = 0
    for slot in slots:
        item = pick(db, slot, level, exclude=exclude)
        if item is not None:
            slot["bankItemId"] = item.id
            exclude.add(item.id)
            covered += 1
    return covered


def exercise_from_item(item: ExerciseBankItem, **fields) -> Exercise:
    """Ejercicio de la clase armado desde el banco (sin IA)."""
    item.times_served = (item.times_served or 0) + 1
    return Exercise(
        level=item.level,
        area=item.area,
        skill_key=item.skill_key,
        exercise_type=item.exercise_type,
        instruction=item.instruction,
        prompt=item.prompt,
        content=dict(item.content or {}),
        expected_concepts=list(item.expected_concepts or []),
        answer_key=dict(item.answer_key or {}),
        presentation_mode=item.presentation_mode,
        response_mode=item.response_mode,
        evaluation_mode=item.evaluation_mode,
        bank_item_id=item.id,
        **fields,
    )


def recent_prompts(db: Session, study_profile_id: int, skill_key: str, *, days: int, limit: int = 3) -> list[str]:
    """T-215: últimas consignas que el alumno vio de ese tema (para pedirle a la IA que no las repita)."""
    from datetime import timedelta

    from app.ai.models import utcnow

    rows = db.scalars(
        select(Exercise.prompt)
        .where(
            Exercise.study_profile_id == study_profile_id,
            Exercise.skill_key == skill_key,
            Exercise.created_at >= utcnow() - timedelta(days=days),
        )
        .order_by(Exercise.id.desc())
        .limit(limit)
    ).all()
    return [p[:90] for p in rows if p]
