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
    batch_item_chars,
    evaluate_batch_with_ai,
    evaluate_with_ai,
    evaluate_without_ai,
)
from app.classes.normalize import normalize_answer
from app.ai.limits import batch_size
from app.classes.types import NO_APPEAL_TYPES
from app.core.config import settings
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

    if is_practice(session):
        # T-214: "Finalizar y comprobar". La tanda preparada que no se mostró se descarta
        # (sus ítems siguen en el banco) y no cuenta como vista.
        _drop_hidden_batches(db, session)
        practice = dict(session.generation_request.get("practice") or {})
        practice["finished"] = True
        session.generation_request = {**session.generation_request, "practice": practice}
    exercises = exercises_of(db, session)
    drafts = drafts_of(db, session)
    answered = _answered_ids(db, session)

    # 1) Persistir TODAS las respuestas antes de evaluar (documento funcional §2.4).
    for exercise in exercises:
        if exercise.id in answered:  # tanda ya entregada con "Continuar"
            continue
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

    def _apply(attempt: Attempt, exercise: Exercise, evaluation) -> None:
        apply_evaluation(attempt, evaluation)
        # El examen es independiente: no alimenta el progreso de las clases.
        if session.kind != SessionKind.EXAM:
            if exercise.skill_key:
                touched_skills.add(exercise.skill_key)
            touched_skills.update(secondary_skill_keys(attempt.evaluation_result))
        db.commit()

    # 1) Reglas, errores comunes, ortografía y caché: sin IA.
    needs_ai: list[tuple[Attempt, Exercise, bool]] = []
    for attempt in pending:
        exercise = db.get(Exercise, attempt.exercise_id)
        spoken = bool(attempt.response_mode and attempt.response_mode.value == "SPEAK")
        evaluation = evaluate_without_ai(db, exercise, attempt.raw_answer, spoken=spoken)
        if evaluation is None:
            needs_ai.append((attempt, exercise, spoken))
            continue
        _apply(attempt, exercise, evaluation)

    # 2) T-171: las que necesitan IA, en UNA llamada si son 2 o más.
    #    T-181: en tandas de hasta AI_BATCH_MAX_ITEMS (el examen puede traer muchas).
    batched = {}
    if settings.ai_batch_evaluation and len(needs_ai) >= 2:
        # T-191: el tamaño de tanda sigue al límite que aprieta (pedidos → más por llamada;
        # tokens → menos). Sin límites aprendidos, AI_BATCH_MAX_ITEMS como antes.
        size = batch_size(
            db, account, items=len(needs_ai),
            chars_per_item=batch_item_chars(db, [(exercise, attempt.raw_answer) for attempt, exercise, _ in needs_ai]),
        )
        for start in range(0, len(needs_ai), size):
            chunk = needs_ai[start:start + size]
            if len(chunk) < 2:
                break  # una sola: va por la corrección individual
            batched.update(
                evaluate_batch_with_ai(
                    db, account, session, [(exercise, attempt.raw_answer, spoken) for attempt, exercise, spoken in chunk]
                )
            )

    # 3) Lo que el lote no resolvió (o sin lote): una por una, como antes. Si no hay IA,
    #    evaluate devuelve None y el intento queda pendiente.
    for attempt, exercise, spoken in needs_ai:
        evaluation = batched.get(exercise.id) or evaluate(
            db, account, exercise, attempt.raw_answer, spoken=spoken
        )
        if evaluation is None:
            continue
        _apply(attempt, exercise, evaluation)

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
    if is_practice(session) and not practice_finished(session):
        complete = False  # T-214: la práctica termina recién con "Finalizar y comprobar"
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
    if exercise.exercise_type in NO_APPEAL_TYPES:
        raise ClassStateError("Este tipo de ejercicio se corrige de forma exacta y no se apela.")
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
        # T-216: el banco aprende la variante aceptada y cuenta el reclamo.
        from app.classes import bank

        bank.record_appeal(db, exercise, accepted=True,
                           variant=(attempt.raw_answer.strip()
                                    if new_score >= 100 and exercise.evaluation_mode.value != "AI" else None))
    else:
        attempt.evaluation_result = {
            **previous,
            "appeal": {"accepted": False, "feedback": result.get("feedback")},
        }
        from app.classes import bank

        bank.record_appeal(db, exercise, accepted=False, variant=None)
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


# ---------------------------------------------------------------- T-214 · práctica continua por tandas

import threading  # noqa: E402

_PRACTICE_LOCKS: dict[int, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _practice_lock(session_id: int) -> threading.Lock:
    with _LOCKS_GUARD:
        return _PRACTICE_LOCKS.setdefault(session_id, threading.Lock())


def is_practice(session: ClassSession) -> bool:
    return bool((session.generation_request or {}).get("practice"))


def practice_finished(session: ClassSession) -> bool:
    return bool(((session.generation_request or {}).get("practice") or {}).get("finished"))


def current_batch(session: ClassSession) -> int:
    return int(((session.generation_request or {}).get("practice") or {}).get("batch") or 1)


def _answered_ids(db: Session, session: ClassSession) -> set[int]:
    return {
        a.exercise_id
        for a in attempts_of(db, session)
        if a.attempt_number == session.current_attempt
    }


def _drop_hidden_batches(db: Session, session: ClassSession) -> None:
    for exercise in exercises_of(db, session):
        if exercise.batch > current_batch(session):
            db.delete(exercise)
    db.flush()


def _batch_exists(db: Session, session: ClassSession, batch: int) -> bool:
    return any(e.batch == batch for e in exercises_of(db, session))


def continue_practice(
    db: Session, study: StudyContext, session: ClassSession, answers: dict[int, str]
) -> None:
    """"Continuar": guarda la tanda actual (se corrige en segundo plano) y muestra la siguiente.
    La siguiente normalmente ya está preparada; si no, se arma ahora (banco primero)."""
    from app.classes import generation

    if not is_practice(session) or practice_finished(session):
        raise ClassStateError("Esta clase no es una práctica en curso.")
    if session.status not in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        raise ClassStateError("La clase no está disponible.")
    batch = current_batch(session)
    drafts = drafts_of(db, session)
    answered = _answered_ids(db, session)
    for exercise in exercises_of(db, session):
        if exercise.batch != batch or exercise.id in answered:
            continue
        if exercise.response_mode == ResponseMode.SPEAK and exercise.id in drafts:
            text = drafts[exercise.id].answer_text
        else:
            text = answers.get(exercise.id) or (drafts[exercise.id].answer_text if exercise.id in drafts else "")
        draft = drafts.get(exercise.id)
        db.add(Attempt(
            exercise_id=exercise.id,
            study_profile_id=session.study_profile_id,
            account_id=study.account.id,
            organization_id=session.organization_id,
            membership_id=session.membership_id,
            attempt_number=session.current_attempt,
            raw_answer=text,
            normalized_answer=normalize_answer(text),
            response_mode=exercise.response_mode,
            audio_duration_ms=draft.audio_duration_ms if draft else None,
            signals=draft.signals if draft else None,
            pronunciation_result=draft.pronunciation_result if draft else None,
            assistance=draft.assistance if draft else Assistance.NONE,
        ))
        if draft:
            db.delete(draft)
    db.commit()

    with _practice_lock(session.id):
        db.refresh(session)
        if not _batch_exists(db, session, batch + 1):
            try:
                generation.add_practice_batch(db, study, session, batch + 1)
            except generation.GenerationFailed as exc:
                raise ClassStateError(f"{exc} Tocá «Finalizar y comprobar» para ver tu resultado.")
        practice = dict(session.generation_request.get("practice") or {})
        practice["batch"] = batch + 1
        session.generation_request = {**session.generation_request, "practice": practice}
        session.status = ClassSessionStatus.IN_PROGRESS
        db.commit()


def practice_background(session_id: int, study: StudyContext) -> None:
    """Después de responder: corrige lo entregado y prepara la próxima tanda (sin que nadie espere)."""
    from app.classes import generation
    from app.db import SessionLocal

    with SessionLocal() as db:
        session = db.get(ClassSession, session_id)
        if session is None or not is_practice(session):
            return
        evaluate_pending(db, study.account, session)
        db.refresh(session)
        if practice_finished(session):
            return
        _note_mistakes(db, session, current_batch(session) - 1)
        with _practice_lock(session_id):
            db.refresh(session)
            following = current_batch(session) + 1
            if not _batch_exists(db, session, following):
                try:
                    generation.add_practice_batch(db, study, session, following)
                except generation.GenerationFailed:
                    pass  # al tocar "Continuar" se vuelve a intentar o se avisa


REINFORCE_BELOW = 70  # puntaje bajo el cual un ejercicio vuelve como refuerzo dirigido (T-215)


def _note_mistakes(db: Session, session: ClassSession, batch: int) -> None:
    """T-215: qué salió mal en la tanda corregida (tema, tipo y errores concretos), para que la
    próxima tanda que se prepare lo refuerce con ejercicios dirigidos."""
    if batch < 1:
        return
    exercises = {e.id: e for e in exercises_of(db, session) if e.batch == batch}
    targets: dict[str, dict] = {}
    for attempt in attempts_of(db, session):
        exercise = exercises.get(attempt.exercise_id)
        if exercise is None or attempt.attempt_number != session.current_attempt:
            continue
        if attempt.score is None or attempt.score >= REINFORCE_BELOW or not exercise.skill_key:
            continue
        mistakes = []
        for error in (attempt.evaluation_result or {}).get("errors") or []:
            text = " → ".join(x for x in (error.get("fragment"), error.get("correction")) if x)
            text = text or error.get("explanation") or ""
            if text:
                mistakes.append(text[:80])
        if not mistakes:
            mistakes.append(f'question "{(exercise.prompt or "")[:60]}" · answered "{(attempt.raw_answer or "")[:40]}"')
        target = targets.setdefault(
            exercise.skill_key, {"skillKey": exercise.skill_key, "type": exercise.exercise_type, "mistakes": []}
        )
        target["mistakes"] = (target["mistakes"] + mistakes)[:2]
    if not targets:
        return
    practice = dict(session.generation_request.get("practice") or {})
    practice["reinforce"] = list(targets.values())
    session.generation_request = {**session.generation_request, "practice": practice}
    db.commit()
