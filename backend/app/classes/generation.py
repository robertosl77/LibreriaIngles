"""Generación de clases.

1. El motor elige skills (prioriza débiles y no practicadas).
2. Se persiste la solicitud (GENERATING) ANTES de llamar a la IA.
3. La IA rellena el contenido; el backend valida y guarda en formato propio.
"""

import random

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.ai.models import utcnow
from app.ai.service import AIResult, NoAIAvailable, run_json_task
from app.classes.normalize import BLANK, normalize_answer, normalize_blank
from app.classes.prompts import GENERATION_SYSTEM, generation_user_prompt
from app.core.deps import StudyContext
from app.curriculum.service import Skill, get_level
from app.learning.models import (
    ClassSession,
    ClassSessionStatus,
    EvaluationMode,
    Exercise,
    SessionKind,
)
from app.progress.service import progress_by_skill

EXERCISES_PER_CLASS = 6

EVALUATION_MODE_BY_TYPE = {
    "multiple_choice": EvaluationMode.DETERMINISTIC,
    "reading_multiple_choice": EvaluationMode.DETERMINISTIC,
    "fill_blank": EvaluationMode.HYBRID,
    "rewrite": EvaluationMode.HYBRID,
    "short_writing": EvaluationMode.AI,
}


class GenerationFailed(Exception):
    pass


# ---------------------------------------------------------------- selección


def _weight(skill: Skill, progress) -> float:
    row = progress.get(skill.key)
    if row is None or row.attempt_count == 0:
        return 3.0
    if row.status == "MASTERED":
        return 0.4
    # Skills que el alumno viene resolviendo con lección/pista: reforzar (T-020).
    assisted_boost = min(1.5, 0.5 * (row.assisted_recent or 0))
    if row.status == "NEEDS_REVIEW":
        return 3.5 + assisted_boost
    return 0.5 + (100 - row.score) / 100 * 2.5 + assisted_boost


def select_slots(
    skills: list[Skill], progress: dict, count: int = EXERCISES_PER_CLASS, rng=None
) -> list[dict]:
    rng = rng or random.Random()
    pool = list(skills)
    chosen: list[Skill] = []
    while pool and len(chosen) < count:
        weights = [_weight(s, progress) for s in pool]
        pick = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    # Si la currícula tiene menos skills que ejercicios, se repiten las más débiles.
    while len(chosen) < count and skills:
        chosen.append(rng.choices(skills, weights=[_weight(s, progress) for s in skills])[0])

    # Balance mínimo: no todo gramática si existen otras áreas.
    areas = {s.area_key for s in skills}
    if len(areas) > 1 and all(s.area_key == "grammar" for s in chosen):
        others = [s for s in skills if s.area_key != "grammar"]
        chosen[-1] = rng.choices(others, weights=[_weight(s, progress) for s in others])[0]

    # Orden pedagógico: gramática y vocabulario primero, escritura al final.
    area_order = {"grammar": 0, "vocabulary": 1, "reading": 2, "writing": 3}
    chosen.sort(key=lambda s: area_order.get(s.area_key, 9))

    return [slot_for(skill, rng) for skill in chosen]


def slot_for(skill: Skill, rng) -> dict:
    """Pedido de un ejercicio para una skill (lo que la IA debe generar)."""
    # Preferir tipos con ejemplo semilla: sirve de guía a la IA (y al simulado).
    seeded = [t for t in skill.exercise_types if any(e.get("type") == t for e in skill.examples)]
    exercise_type = rng.choice(seeded or list(skill.exercise_types))
    example = next(
        (e for e in skill.examples if e.get("type") == exercise_type),
        skill.examples[0] if skill.examples else None,
    )
    return {
        "skillKey": skill.key,
        "area": skill.area_name,
        "topic": skill.topic_name,
        "skill": skill.name,
        "objectives": list(skill.objectives),
        "allowedTypes": [exercise_type],
        "example": example,
        # Solo para el proveedor simulado.
        "examples": [e for e in skill.examples if e.get("type") == exercise_type]
        or list(skill.examples),
    }


# ---------------------------------------------------------------- validación


class CommonErrorOut(BaseModel):
    answer: str
    feedback: str = ""
    conceptResults: list[dict] = []


class ExerciseOut(BaseModel):
    skillKey: str
    type: str
    instruction: str = ""
    question: str
    passage: str | None = None
    options: list[str] | None = None
    acceptedAnswers: list[str] = []
    commonErrors: list[CommonErrorOut] = []
    expectedConcepts: list[str] = []

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        value = normalize_blank(value.strip())
        if not value:
            raise ValueError("pregunta vacía")
        return value


def _validate_exercise(raw: dict, slot: dict) -> ExerciseOut | None:
    try:
        item = ExerciseOut.model_validate(raw)
    except ValidationError:
        return None
    if item.skillKey != slot["skillKey"] or item.type not in slot["allowedTypes"]:
        return None
    item.acceptedAnswers = [a.strip() for a in item.acceptedAnswers if a and a.strip()]
    if item.type in ("multiple_choice", "reading_multiple_choice"):
        options = [o.strip() for o in item.options or [] if o and o.strip()]
        if len(options) < 2:
            return None
        normalized = {normalize_answer(o): o for o in options}
        correct = [normalized.get(normalize_answer(a)) for a in item.acceptedAnswers]
        correct = [c for c in correct if c]
        if len(correct) != 1:
            return None
        item.options, item.acceptedAnswers = options, correct
        if item.type == "reading_multiple_choice" and not (item.passage or "").strip():
            return None
    elif item.type == "fill_blank":
        if item.question.count(BLANK) != 1 or not item.acceptedAnswers:
            return None
    elif item.type == "rewrite":
        if not item.acceptedAnswers:
            return None
    elif item.type == "short_writing":
        item.acceptedAnswers = []
    if not item.expectedConcepts:
        item.expectedConcepts = ["task_completion"]
    return item


def _match_slots(exercises: list, slots: list[dict]) -> list[tuple[dict, ExerciseOut]]:
    """Empareja cada slot con un ejercicio válido de su skill (en orden)."""
    remaining = [e for e in exercises if isinstance(e, dict)]
    matched = []
    for slot in slots:
        for index, raw in enumerate(remaining):
            item = _validate_exercise(raw, slot)
            if item is not None:
                matched.append((slot, item))
                remaining.pop(index)
                break
    return matched


# ---------------------------------------------------------------- flujo


def _enough(session: ClassSession, slots: list[dict], matched: list) -> bool:
    """Una clase sirve con la mitad; un examen necesita casi todo y todas las áreas."""
    if session.kind != SessionKind.EXAM:
        return len(matched) >= max(1, len(slots) // 2)
    areas_requested = {s["skillKey"].split(".")[1] for s in slots}
    areas_matched = {slot["skillKey"].split(".")[1] for slot, _ in matched}
    return len(matched) * 4 >= len(slots) * 3 and areas_requested <= areas_matched


def create_class(
    db: Session, study: StudyContext
) -> tuple[ClassSession, AIResult | None]:
    level = study.profile.operational_level or study.profile.selected_level
    curriculum = get_level(level) if level else None
    if curriculum is None:
        raise GenerationFailed("Elegí un nivel disponible antes de pedir una clase.")

    slots = select_slots(list(curriculum.skills), progress_by_skill(db, study.profile.id))
    session = ClassSession(
        study_profile_id=study.profile.id,
        account_id=study.account.id,
        organization_id=study.organization_id,
        membership_id=study.membership_id,
        status=ClassSessionStatus.GENERATING,
        target_level=curriculum.level,
        generation_request={"level": curriculum.level, "slots": slots},
    )
    db.add(session)
    db.commit()  # persistir la solicitud antes de llamar a la IA
    result = generate_content(db, study, session)
    return session, result


def generate_content(
    db: Session, study: StudyContext, session: ClassSession
) -> AIResult | None:
    request = session.generation_request or {}
    slots = request.get("slots") or []
    public_slots = [{k: v for k, v in s.items() if k != "examples"} for s in slots]
    try:
        result = run_json_task(
            db,
            study.account,
            system=GENERATION_SYSTEM,
            user=generation_user_prompt(
                request.get("level", ""), public_slots, purpose=request.get("purpose", "class")
            ),
            task={"kind": "generate_class", "level": request.get("level"), "slots": slots},
        )
    except NoAIAvailable as exc:
        session.status = ClassSessionStatus.GENERATION_FAILED
        session.generation_error = "No hay conexiones de IA disponibles. " + "; ".join(exc.errors)
        db.commit()
        return None

    matched = _match_slots(result.data.get("exercises") or [], slots)
    if not _enough(session, slots, matched):
        session.status = ClassSessionStatus.GENERATION_FAILED
        session.generation_error = (
            f"La IA devolvió {len(matched)} ejercicios válidos de {len(slots)} pedidos."
        )
        if session.kind == SessionKind.EXAM:
            session.generation_error += " El examen necesita ejercicios de todas las áreas."
        session.generated_by_connection_id = result.connection.id
        db.commit()
        return None

    for position, (slot, item) in enumerate(matched):
        skill_key = slot["skillKey"]
        db.add(
            Exercise(
                class_session_id=session.id,
                study_profile_id=session.study_profile_id,
                organization_id=session.organization_id,
                membership_id=session.membership_id,
                position=position,
                level=request.get("level"),
                area=skill_key.split(".")[1],
                skill_key=skill_key,
                exercise_type=item.type,
                instruction=item.instruction,
                prompt=item.question,
                content={
                    k: v
                    for k, v in {"options": item.options, "passage": item.passage}.items()
                    if v
                },
                expected_concepts=item.expectedConcepts,
                answer_key={
                    "acceptedAnswers": item.acceptedAnswers,
                    "commonErrors": [e.model_dump() for e in item.commonErrors],
                },
                evaluation_mode=EVALUATION_MODE_BY_TYPE[item.type],
            )
        )
    title = str(result.data.get("title") or "").strip()[:200]
    if session.kind == SessionKind.EXAM:
        session.title = f"Examen de nivel {request.get('level')}"
    else:
        session.title = title or f"Clase {request.get('level')}"
    session.status = ClassSessionStatus.READY
    session.generation_error = None
    session.generated_at = utcnow()
    session.generated_by_connection_id = result.connection.id
    db.commit()
    return result
