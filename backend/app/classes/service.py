"""Ciclo de vida de una clase: autoguardado, envío, evaluación, pendientes, rehacer y apelación."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import utcnow
from app.ai.service import NoAIAvailable
from app.classes.evaluation import (
    Evaluation,
    ai_score,
    apply_evaluation,
    evaluate,
    evaluate_with_ai,
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
    ResponseMode,
    SessionKind,
    stronger_assistance,
)
from app.progress.service import recompute_skill, secondary_skill_keys


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


def exercise_display_number(db: Session, exercise: Exercise) -> int:
    """Número humano dentro de la clase.

    Una conversación multi-turno es una sola actividad visible: sus turnos comparten
    número. Esto evita exponer el PK interno de Exercise en auditorías/Consumo.
    """
    session = db.get(ClassSession, exercise.class_session_id)
    if session is None:
        return max(1, exercise.position + 1)

    number = 0
    for item in exercises_of(db, session):
        conversation = (item.content or {}).get("conversation") or {}
        is_continuation = (
            item.exercise_type == "conversation"
            and int(conversation.get("turn") or 1) > 1
        )
        if not is_continuation:
            number += 1
        if item.id == exercise.id:
            return max(1, number)
    return max(1, exercise.position + 1)


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
    db: Session,
    study: StudyContext,
    session: ClassSession,
    exercise_id: int,
    answer: str,
    *,
    audio_duration_ms: int | None = None,
    pronunciation_result: dict | None = None,
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
    draft.audio_duration_ms = audio_duration_ms
    draft.pronunciation_result = pronunciation_result
    # Las señales (escuchas, prácticas) se conservan al guardar la respuesta.
    draft.account_id = study.account.id
    draft.updated_at = utcnow()
    session.status = ClassSessionStatus.IN_PROGRESS
    db.commit()
    return draft


MAX_SIGNAL_COUNT = 50
MAX_PRACTICE_TRIALS = 20


def record_signals(
    db: Session,
    study: StudyContext,
    session: ClassSession,
    exercise_id: int,
    *,
    listen_play: bool = False,
    slow: bool = False,
    practice_score: int | None = None,
    retake: bool = False,
) -> dict:
    """Acumula señales de la respuesta en curso (T-034): escuchas, lento, prácticas y
    regrabaciones de la respuesta hablada (T-046 v2).

    Solo con la clase abierta: una vez enviada, la evidencia ya no cambia.
    """
    if session.status not in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        raise ClassStateError("La clase ya fue enviada.")
    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.class_session_id != session.id:
        raise ClassStateError("El ejercicio no pertenece a la clase.")

    draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
    if draft is None:
        draft = DraftAnswer(class_session_id=session.id, exercise_id=exercise_id, answer_text="")
        db.add(draft)
    signals = dict(draft.signals or {})
    if listen_play:
        signals["listenPlays"] = min(MAX_SIGNAL_COUNT, int(signals.get("listenPlays", 0)) + 1)
        if slow:
            signals["listenSlowPlays"] = min(
                MAX_SIGNAL_COUNT, int(signals.get("listenSlowPlays", 0)) + 1
            )
    if practice_score is not None:
        trials = list(signals.get("practiceScores") or [])
        trials.append(max(0, min(100, int(practice_score))))
        signals["practiceScores"] = trials[-MAX_PRACTICE_TRIALS:]
    if retake:
        signals["speakRetakes"] = min(MAX_SIGNAL_COUNT, int(signals.get("speakRetakes", 0)) + 1)
    draft.signals = signals
    draft.account_id = study.account.id
    draft.updated_at = utcnow()
    session.status = ClassSessionStatus.IN_PROGRESS
    db.commit()
    return signals


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
    if session.kind == SessionKind.EXAM:
        raise ClassStateError("En el examen de nivel no hay lecciones.")
    # Mientras se corrige no se toca nada; corregida, la lección se puede consultar (solo lectura).
    if session.status not in (
        ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS, ClassSessionStatus.COMPLETED
    ):
        raise ClassStateError("La clase se está corrigiendo. Esperá el resultado.")
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
        # SPEAK se procesa al enviar la clase: la transcripción válida vive en
        # el borrador creado desde el audio confirmado, no en el payload textual.
        if exercise.response_mode == ResponseMode.SPEAK and exercise.id in drafts:
            text = drafts[exercise.id].answer_text
        elif exercise.id in answers:
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
                response_mode=exercise.response_mode,
                audio_duration_ms=(
                    drafts[exercise.id].audio_duration_ms if exercise.id in drafts else None
                ),
                signals=(drafts[exercise.id].signals if exercise.id in drafts else None),
                pronunciation_result=(
                    drafts[exercise.id].pronunciation_result if exercise.id in drafts else None
                ),
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
        spoken = bool(attempt.response_mode and attempt.response_mode.value == "SPEAK")
        evaluation = evaluate(db, account, exercise, attempt.raw_answer, spoken=spoken)
        if evaluation is None:
            continue
        apply_evaluation(attempt, evaluation)
        # El examen es independiente: no alimenta el progreso de las clases.
        if session.kind != SessionKind.EXAM:
            if exercise.skill_key:
                touched_skills.add(exercise.skill_key)
            touched_skills.update(secondary_skill_keys(attempt.evaluation_result))
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
    if complete and session.kind == SessionKind.EXAM:
        from app.exams.service import finalize_exam

        finalize_exam(db, session)
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
    if session.kind == SessionKind.EXAM:
        raise ClassStateError("El examen de nivel no se rehace: se rinde uno nuevo.")
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
    # Ortografía sola no llega a 100: así una palabra mal escrita nunca entra como aceptada.
    new_score = ai_score(exercise, result)
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
    if session.kind != SessionKind.EXAM:
        touched = ({exercise.skill_key} if exercise.skill_key else set()) | secondary_skill_keys(
            attempt.evaluation_result
        )
        for skill_key in touched:
            recompute_skill(db, study_profile_id=session.study_profile_id, skill_key=skill_key)
            if session.organization_id is not None:
                recompute_skill(
                    db,
                    study_profile_id=session.study_profile_id,
                    skill_key=skill_key,
                    organization_id=session.organization_id,
                )
    db.commit()
    if session.kind == SessionKind.EXAM and session.status == ClassSessionStatus.COMPLETED:
        from app.exams.service import finalize_exam

        finalize_exam(db, session)
    return attempt
