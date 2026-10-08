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


# ---------------------------------------------------------------- T-216: calidad del banco


def _reports_today(db: Session, study_profile_id: int) -> int:
    from datetime import timedelta

    from sqlalchemy import func

    from app.ai.models import utcnow
    from app.learning.models import ExerciseReport

    return db.scalar(select(func.count(ExerciseReport.id)).where(
        ExerciseReport.study_profile_id == study_profile_id,
        ExerciseReport.created_at >= utcnow() - timedelta(days=1),
    )) or 0


def report(db: Session, exercise: Exercise, study_profile_id: int, reason: str) -> bool:
    """Registra el reporte del alumno (una vez por ejercicio y motivo). True si es nuevo."""
    from app.learning.models import ExerciseReport, ExerciseReportReason

    kind = ExerciseReportReason(reason)
    exists = db.scalar(select(ExerciseReport).where(
        ExerciseReport.exercise_id == exercise.id,
        ExerciseReport.study_profile_id == study_profile_id,
        ExerciseReport.reason == kind,
    ))
    if exists:
        return False
    from app.core.config import settings

    suspends = _reports_today(db, study_profile_id) < settings.bank_reports_per_day
    db.add(ExerciseReport(exercise_id=exercise.id, study_profile_id=study_profile_id,
                          bank_item_id=exercise.bank_item_id, reason=kind))
    item = db.get(ExerciseBankItem, exercise.bank_item_id) if exercise.bank_item_id else None
    if item is not None:
        if kind == ExerciseReportReason.WRONG:
            item.wrong_reports = (item.wrong_reports or 0) + 1
        else:
            item.repeat_reports = (item.repeat_reports or 0) + 1
        # Un reporte alcanza para dejar de servirlo; decide SrMacros (dentro del tope diario).
        if suspends and item.status == BankItemStatus.ACTIVE:
            item.status = BankItemStatus.REVIEW
    return True


def record_appeal(db: Session, exercise: Exercise, *, accepted: bool, variant: str | None) -> None:
    """Un reclamo sobre un ejercicio del banco: cuenta para la calidad; si se aceptó una variante,
    se suma a la clave del ítem (así no le vuelve a pasar a otro alumno)."""
    item = db.get(ExerciseBankItem, exercise.bank_item_id) if exercise.bank_item_id else None
    if item is None:
        return
    item.appeals = (item.appeals or 0) + 1
    if accepted:
        item.appeals_accepted = (item.appeals_accepted or 0) + 1
        if variant:
            accepted_answers = list((item.answer_key or {}).get("acceptedAnswers") or [])
            if variant not in accepted_answers:
                item.answer_key = {**(item.answer_key or {}), "acceptedAnswers": accepted_answers + [variant]}


# ---------------------------------------------------------------- T-216: decisión de SrMacros


def review_queue(db: Session) -> list[dict]:
    """Ítems en revisión, los más reportados primero, con sus reportes y quién los hizo."""
    from sqlalchemy import func

    from app.accounts.models import Account
    from app.learning.models import ExerciseReport
    from app.learning.models import ClassSession

    items = db.scalars(select(ExerciseBankItem).where(ExerciseBankItem.status == BankItemStatus.REVIEW)).all()
    totals = dict(db.execute(
        select(ExerciseReport.study_profile_id, func.count(ExerciseReport.id)).group_by(ExerciseReport.study_profile_id)
    ).all())
    queue = []
    for item in items:
        reports = db.scalars(
            select(ExerciseReport).where(ExerciseReport.bank_item_id == item.id).order_by(ExerciseReport.created_at)
        ).all()
        rows = []
        for r in reports:
            reported_exercise = db.get(Exercise, r.exercise_id)
            session = db.get(ClassSession, reported_exercise.class_session_id) if reported_exercise else None
            account = db.get(Account, session.account_id) if session and session.account_id else None
            rows.append({
                "reason": r.reason.value,
                "at": r.created_at,
                "email": account.email if account else None,
                "reporterTotal": totals.get(r.study_profile_id, 0),
            })
        queue.append({
            "id": item.id,
            "level": item.level,
            "skillKey": item.skill_key,
            "type": item.exercise_type,
            "instruction": item.instruction,
            "prompt": item.prompt,
            "options": (item.content or {}).get("options"),
            "acceptedAnswers": (item.answer_key or {}).get("acceptedAnswers") or [],
            "wrongReports": item.wrong_reports or 0,
            "repeatReports": item.repeat_reports or 0,
            "appeals": item.appeals or 0,
            "appealsAccepted": item.appeals_accepted or 0,
            "timesServed": item.times_served or 0,
            "reports": rows,
        })
    queue.sort(key=lambda q: (-(q["wrongReports"] + q["repeatReports"]), q["id"]))
    return queue


def decide(db: Session, item_id: int, action: str, accepted_answers: list[str] | None = None) -> ExerciseBankItem:
    item = db.get(ExerciseBankItem, item_id)
    if item is None:
        raise ValueError("Ítem inexistente.")
    if action == "RETIRE":
        item.status = BankItemStatus.RETIRED
        item.retired_reason = "Retirado por SrMacros tras revisión"
    elif action in ("ACTIVATE", "FIX"):
        if action == "FIX":
            answers = [a.strip() for a in (accepted_answers or []) if a and a.strip()]
            if not answers:
                raise ValueError("Indicá al menos una respuesta correcta.")
            item.answer_key = {**(item.answer_key or {}), "acceptedAnswers": answers}
        item.status = BankItemStatus.ACTIVE
        item.retired_reason = None
        item.wrong_reports = 0
        item.repeat_reports = 0
    else:
        raise ValueError("Acción inválida.")
    return item
