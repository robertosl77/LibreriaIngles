"""Ciclo de vida de una clase: autoguardado, envío, evaluación, pendientes, rehacer y apelación."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import utcnow
from app.ai.service import NoAIAvailable
from app.classes.evaluation import (
    Evaluation,
    apply_evaluation,
    evaluate,
    evaluate_with_ai,
    score_from_result,
)
from app.classes.normalize import normalize_answer
from app.core.deps import StudyContext
from app.curriculum.lessons import lesson_payload
from app.learning.models import (
    Assistance,
    Attempt,
    ClassSession,
    ClassSessionStatus,
    DraftAnswer,
    EvaluationSource,
    Exercise,
    stronger_assistance,
)
from app.progress.service import recompute_skill


class ClassStateError(Exception):
    pass


def exercises_of(db: Session, session: ClassSession) -> list[Exercise]:
    return list(
        db.scalars(
            select(Exercise)
            .where(Exercise.class_session_id == session.id)
            .order_by(Exercise.position, Exercise.id)
        )
    )


def drafts_of(db: Session, session: ClassSession) -> dict[int, DraftAnswer]:
    rows = db.scalars(select(DraftAnswer).where(DraftAnswer.class_session_id == session.id))
    return {row.exercise_id: row for row in rows}


def attempts_of(db: Session, session: ClassSession) -> list[Attempt]:
    return list(
        db.scalars(
            select(Attempt)
            .join(Exercise, Exercise.id == Attempt.exercise_id)
            .where(Exercise.class_session_id == session.id)
            .order_by(Attempt.attempt_number, Exercise.position)
        )
    )


def save_draft(
    db: Session, study: StudyContext, session: ClassSession, exercise_id: int, answer: str
) -> DraftAnswer:
    if session.status not in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        raise ClassStateError("La clase ya fue enviada.")
    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.class_session_id != session.id:
        raise ClassStateError("El ejercicio no pertenece a la clase.")

    draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
    if draft is None:
        draft = DraftAnswer(class_session_id=session.id, exercise_id=exercise_id)
        db.add(draft)
    draft.answer_text = answer
    draft.account_id = study.account.id
    draft.updated_at = utcnow()
    session.status = ClassSessionStatus.IN_PROGRESS
    db.commit()
    return draft


def open_lesson(
    db: Session, study: StudyContext, session: ClassSession, exercise_id: int
) -> dict:
    """Lección del tema del ejercicio, sin salir de la clase (T-020).

    Mientras la clase está abierta, queda registrado que el ejercicio se responde
    con lección. Consultarla después de la corrección no cambia nada.
    """
    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.class_session_id != session.id:
        raise ClassStateError("El ejercicio no pertenece a la clase.")
    lesson = lesson_payload(exercise.skill_key) if exercise.skill_key else None
    if lesson is None:
        raise ClassStateError("Todavía no hay lección para este tema.")

    registered = False
    if session.status in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
        if draft is None:
            draft = DraftAnswer(
                class_session_id=session.id, exercise_id=exercise_id, answer_text=""
            )
            db.add(draft)
        draft.assistance = stronger_assistance(draft.assistance, Assistance.LESSON)
        draft.account_id = study.account.id
        draft.updated_at = utcnow()
        session.status = ClassSessionStatus.IN_PROGRESS
        db.commit()
        registered = True
    return {"exerciseId": exercise_id, "registered": registered, "lesson": lesson}


def submit(
    db: Session, study: StudyContext, session: ClassSession, answers: dict[int, str]
) -> None:
    if session.status not in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        raise ClassStateError("La clase no está disponible para enviar.")

    exercises = exercises_of(db, session)
    drafts = drafts_of(db, session)

    # 1) Persistir TODAS las respuestas antes de evaluar (documento funcional §2.4).
    for exercise in exercises:
        if exercise.id in answers:
            text = answers[exercise.id]
        elif exercise.id in drafts:
            text = drafts[exercise.id].answer_text
        else:
            text = ""
        db.add(
            Attempt(
                exercise_id=exercise.id,
                study_profile_id=session.study_profile_id,
                account_id=study.account.id,
                organization_id=session.organization_id,
                membership_id=session.membership_id,
                attempt_number=session.current_attempt,
                raw_answer=text,
                normalized_answer=normalize_answer(text),
                assistance=(
                    drafts[exercise.id].assistance if exercise.id in drafts else Assistance.NONE
                ),
            )
        )
    for draft in drafts.values():
        db.delete(draft)
    session.status = ClassSessionStatus.AWAITING_EVALUATION
    session.submitted_at = utcnow()
    db.commit()

    # 2) Recién ahora evaluar. Si falla la IA, las respuestas ya están guardadas.
    evaluate_pending(db, study.account, session)


def evaluate_pending(db: Session, account: Account, session: ClassSession) -> bool:
    """Evalúa los intentos sin evaluación de la ronda actual. True si la clase quedó completa."""
    pending = [
        a
        for a in attempts_of(db, session)
        if a.attempt_number == session.current_attempt and a.score is None
    ]
    touched_skills: set[str] = set()
    for attempt in pending:
        exercise = db.get(Exercise, attempt.exercise_id)
        # Si hace falta IA y no hay ninguna, evaluate devuelve None y el intento
        # queda pendiente; los que se resuelven por reglas se evalúan igual.
        evaluation = evaluate(db, account, exercise, attempt.raw_answer)
        if evaluation is None:
            continue
        apply_evaluation(attempt, evaluation)
        if exercise.skill_key:
            touched_skills.add(exercise.skill_key)
        db.commit()

    for skill_key in touched_skills:
        recompute_skill(db, study_profile_id=session.study_profile_id, skill_key=skill_key)
        if session.organization_id is not None:
            recompute_skill(
                db,
                study_profile_id=session.study_profile_id,
                skill_key=skill_key,
                organization_id=session.organization_id,
            )

    current = [a for a in attempts_of(db, session) if a.attempt_number == session.current_attempt]
    complete = bool(current) and all(a.score is not None for a in current)
    if complete:
        session.score = round(sum(a.score for a in current) / len(current), 1)
        session.status = ClassSessionStatus.COMPLETED
        session.evaluated_at = utcnow()
    db.commit()
    return complete


def process_pending(db: Session, study: StudyContext) -> dict:
    """Reintenta las clases que esperan corrección (documento funcional §27)."""
    sessions = db.scalars(
        select(ClassSession).where(
            ClassSession.study_profile_id == study.profile.id,
            ClassSession.status == ClassSessionStatus.AWAITING_EVALUATION,
        )
    ).all()
    completed = 0
    for session in sessions:
        if evaluate_pending(db, study.account, session):
            completed += 1
    return {"pending": len(sessions), "completed": completed}


def retake(db: Session, session: ClassSession) -> None:
    if session.status != ClassSessionStatus.COMPLETED:
        raise ClassStateError("Solo se puede rehacer una clase completada.")
    session.current_attempt += 1
    session.status = ClassSessionStatus.READY
    session.score = None
    session.submitted_at = None
    session.evaluated_at = None
    db.commit()


def appeal(db: Session, study: StudyContext, session: ClassSession, exercise_id: int) -> Attempt:
    """"Creo que mi respuesta es correcta": re-evaluación con IA (documento funcional §11)."""
    attempt = db.scalar(
        select(Attempt).where(
            Attempt.exercise_id == exercise_id,
            Attempt.attempt_number == session.current_attempt,
        )
    )
    exercise = db.get(Exercise, exercise_id)
    if attempt is None or exercise is None or exercise.class_session_id != session.id:
        raise ClassStateError("No hay un intento para apelar.")
    if attempt.score is None or attempt.score >= 100:
        raise ClassStateError("Ese intento no se puede apelar.")
    if attempt.appealed_at is not None:
        raise ClassStateError("Ese intento ya fue apelado.")
    if not attempt.normalized_answer:
        raise ClassStateError("No hay respuesta para revisar.")

    try:
        result = evaluate_with_ai(db, study.account, exercise, attempt.raw_answer)
    except NoAIAvailable as exc:
        raise ClassStateError("No hay conexiones de IA disponibles para revisar la respuesta.") from exc

    attempt.appealed_at = utcnow()
    new_score = score_from_result(result)
    previous = attempt.evaluation_result or {}
    if new_score > (attempt.score or 0):
        apply_evaluation(attempt, Evaluation(EvaluationSource.AI, result, new_score))
        attempt.evaluation_result = {
            **attempt.evaluation_result,
            "appeal": {"accepted": True, "previousScore": previous.get("score")},
        }
        if new_score >= 100 and exercise.evaluation_mode.value != "AI":
            # La variante aceptada pasa a la answer key del ejercicio.
            accepted = list(exercise.answer_key.get("acceptedAnswers") or [])
            if attempt.raw_answer.strip() not in accepted:
                accepted.append(attempt.raw_answer.strip())
            exercise.answer_key = {**exercise.answer_key, "acceptedAnswers": accepted}
    else:
        attempt.evaluation_result = {
            **previous,
            "appeal": {"accepted": False, "feedback": result.get("feedback")},
        }
    db.commit()

    current = [a for a in attempts_of(db, session) if a.attempt_number == session.current_attempt]
    if current and all(a.score is not None for a in current):
        session.score = round(sum(a.score for a in current) / len(current), 1)
    if exercise.skill_key:
        recompute_skill(db, study_profile_id=session.study_profile_id, skill_key=exercise.skill_key)
    db.commit()
    return attempt
