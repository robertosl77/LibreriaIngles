from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.accounts.models import Account
from app.ai.models import AIConnection
from app.ai.service import (
    NoAIAvailable,
    connection_snapshot,
    public_trace,
    transcribe_audio,
)
from app.ai.usage import AIUsageContext
from app.classes import generation, service
from app.pronunciation import normalize_ai_pronunciation
from app.core.deps import CurrentStudy, DbSession
from app.curriculum.lessons import get_lesson
from app.learning.models import (
    Attempt,
    ClassSession,
    ClassSessionStatus,
    DraftAnswer,
    Exercise,
    SessionKind,
)
from app.progress.service import skill_name

router = APIRouter(prefix="/classes", tags=["classes"])

SWITCH_NOTICE = "Se cambió automáticamente el proveedor de IA."
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 65_000


class AnswerRequest(BaseModel):
    answer: str = Field(default="", max_length=4000)


class SignalRequest(BaseModel):
    """Señal de la respuesta en curso (T-034)."""

    kind: str = Field(pattern="^(listen|practice|retake)$")
    slow: bool = False
    score: int | None = Field(default=None, ge=0, le=100)


class SubmitRequest(BaseModel):
    answers: dict[int, str] = Field(default_factory=dict)


def _get_class(db, study, class_id: int) -> ClassSession:
    session = db.get(ClassSession, class_id)
    if session is None or session.study_profile_id != study.profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clase inexistente.")
    return session


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _result_payload(db, attempt: Attempt, exercise: Exercise, viewer) -> dict | None:
    if attempt.score is None:
        return None
    result = attempt.evaluation_result or {}
    return {
        "score": attempt.score,
        "result": result.get("result"),
        "feedback": result.get("feedback"),
        "correctAnswer": result.get("correctAnswer"),
        "errors": result.get("errors") or [],
        "suggestions": result.get("suggestions") or [],
        "conceptResults": result.get("conceptResults") or [],
        "secondarySkillResults": result.get("secondarySkillResults") or [],
        "evaluationSource": attempt.evaluation_source.value if attempt.evaluation_source else None,
        "ai": public_trace(db, result.get("ai"), viewer),
        "appeal": result.get("appeal"),
        "canAppeal": attempt.score < 100
        and attempt.appealed_at is None
        and bool(attempt.normalized_answer),
    }


def _stimulus(exercise: Exercise) -> dict | None:
    """Estímulo del ejercicio según la presentación (T-025).

    LISTEN: el frontend sintetiza la voz con este texto y lo muestra recién después de la
    corrección. READ: el pasaje (si hay) se muestra escrito, como siempre.
    """
    content = exercise.content or {}
    if exercise.presentation_mode.value == "LISTEN" and content.get("stimulus"):
        return {
            "mode": "LISTEN",
            "text": content["stimulus"],
            "lang": content.get("stimulusLang", "en-US"),
            "rate": content.get("stimulusRate", 1.0),
        }
    if content.get("passage"):
        return {"mode": "READ", "text": content["passage"], "lang": "en-US", "rate": 1.0}
    return None


def _detail(db, session: ClassSession, notice: str | None = None) -> dict:
    # Quien ve la clase es su dueño: se le ocultan los datos de conexiones de plataforma (T-055).
    viewer = db.get(Account, session.account_id) if session.account_id else None
    exercises = service.exercises_of(db, session)
    drafts = service.drafts_of(db, session)
    attempts = service.attempts_of(db, session)
    current = {a.exercise_id: a for a in attempts if a.attempt_number == session.current_attempt}

    rounds: dict[int, list[float]] = {}
    for attempt in attempts:
        if attempt.score is not None:
            rounds.setdefault(attempt.attempt_number, []).append(attempt.score)

    items = []
    for exercise in exercises:
        attempt = current.get(exercise.id)
        draft = drafts.get(exercise.id)
        items.append(
            {
                "id": exercise.id,
                "position": exercise.position,
                "type": exercise.exercise_type,
                "area": exercise.area,
                "skillKey": exercise.skill_key,
                "skillName": skill_name(exercise.skill_key),
                "instruction": exercise.instruction,
                "question": exercise.prompt,
                "passage": (exercise.content or {}).get("passage"),
                "presentation": exercise.presentation_mode.value,
                "response": exercise.response_mode.value,
                "stimulus": _stimulus(exercise),
                "options": (exercise.content or {}).get("options"),
                "conversation": (exercise.content or {}).get("conversation"),
                "answer": attempt.raw_answer if attempt else (draft.answer_text if draft else ""),
                "audioDurationMs": (
                    attempt.audio_duration_ms
                    if attempt
                    else (draft.audio_duration_ms if draft else None)
                ),
                "pronunciationResult": (
                    public_trace(db, attempt.pronunciation_result, viewer)
                    if attempt and attempt.score is not None
                    else None
                ),
                "signals": (
                    attempt.signals if attempt else (draft.signals if draft else None)
                ) or {},
                "assistance": (
                    attempt.assistance.value
                    if attempt
                    else (draft.assistance.value if draft else "NONE")
                ),
                "hasLesson": session.kind == SessionKind.CLASS
                and get_lesson(exercise.skill_key) is not None,
                "result": _result_payload(db, attempt, exercise, viewer) if attempt else None,
            }
        )

    connection = (
        db.get(AIConnection, session.generated_by_connection_id)
        if session.generated_by_connection_id
        else None
    )
    generation_ai = (session.generation_request or {}).get("ai")
    if generation_ai is None and connection is not None:
        # Compatibilidad con clases previas a T-041: no es histórico, pero al
        # menos muestra la configuración actual de la conexión si sigue viva.
        generation_ai = connection_snapshot(connection)
    generation_ai = public_trace(db, generation_ai, viewer)

    return {
        "id": session.id,
        "kind": session.kind.value,
        "title": session.title,
        "status": session.status.value,
        "targetLevel": session.target_level,
        "currentAttempt": session.current_attempt,
        "score": session.score,
        "createdAt": session.created_at,
        "submittedAt": session.submitted_at,
        "evaluatedAt": session.evaluated_at,
        "generationError": session.generation_error,
        "generatedBy": (
            generation_ai.get("connection")
            if generation_ai
            else (connection.name if connection else None)
        ),
        "generationAi": generation_ai,
        "exercises": items,
        "answered": sum(1 for i in items if (i["answer"] or "").strip()),
        "history": [
            {"attempt": number, "score": round(sum(scores) / len(scores), 1)}
            for number, scores in sorted(rounds.items())
            if number != session.current_attempt or session.status == ClassSessionStatus.COMPLETED
        ],
        "examResult": session.exam_result,
        # Balanceo por habilidad (T-034): qué refuerza esta clase y por qué.
        "focus": (session.generation_request or {}).get("focus") or [],
        "certificateCode": _certificate_code(db, session),
        "notice": notice,
    }


def _certificate_code(db, session: ClassSession) -> str | None:
    if session.kind != SessionKind.EXAM or not (session.exam_result or {}).get("passed"):
        return None
    from app.exams.models import LevelCertificate

    return db.scalar(
        select(LevelCertificate.code).where(LevelCertificate.exam_session_id == session.id)
    )


@router.get("")
def list_classes(study: CurrentStudy, db: DbSession, limit: int = 50) -> list[dict]:
    sessions = db.scalars(
        select(ClassSession)
        .where(ClassSession.study_profile_id == study.profile.id)
        .order_by(ClassSession.created_at.desc(), ClassSession.id.desc())
        .limit(min(limit, 200))
    ).all()
    ids = [s.id for s in sessions]
    totals = dict(
        db.execute(
            select(Exercise.class_session_id, func.count())
            .where(Exercise.class_session_id.in_(ids))
            .group_by(Exercise.class_session_id)
        ).all()
    ) if ids else {}
    answered = dict(
        db.execute(
            select(DraftAnswer.class_session_id, func.count())
            .where(DraftAnswer.class_session_id.in_(ids), DraftAnswer.answer_text != "")
            .group_by(DraftAnswer.class_session_id)
        ).all()
    ) if ids else {}
    return [
        {
            "id": s.id,
            "kind": s.kind.value,
            "title": s.title,
            "status": s.status.value,
            "targetLevel": s.target_level,
            "score": s.score,
            "currentAttempt": s.current_attempt,
            "createdAt": s.created_at,
            "total": totals.get(s.id, 0),
            "answered": answered.get(s.id, 0),
        }
        for s in sessions
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_class(study: CurrentStudy, db: DbSession) -> dict:
    try:
        session, result = generation.create_class(db, study)
    except generation.GenerationFailed as exc:
        raise HTTPException(422, str(exc))
    notice = SWITCH_NOTICE if result and result.switched else None
    return _detail(db, session, notice)


@router.post("/process-pending")
def process_pending(study: CurrentStudy, db: DbSession) -> dict:
    return service.process_pending(db, study)


@router.get("/{class_id}")
def get_class(class_id: int, study: CurrentStudy, db: DbSession) -> dict:
    return _detail(db, _get_class(db, study, class_id))


@router.post("/{class_id}/retry-generation")
def retry_generation(class_id: int, study: CurrentStudy, db: DbSession) -> dict:
    session = _get_class(db, study, class_id)
    if session.status != ClassSessionStatus.GENERATION_FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, "La clase no falló al generarse.")
    session.status = ClassSessionStatus.GENERATING
    db.commit()
    result = generation.generate_content(db, study, session)
    notice = SWITCH_NOTICE if result and result.switched else None
    return _detail(db, session, notice)


@router.put("/{class_id}/answers/{exercise_id}")
def save_answer(
    class_id: int, exercise_id: int, payload: AnswerRequest, study: CurrentStudy, db: DbSession
) -> dict:
    session = _get_class(db, study, class_id)
    try:
        draft = service.save_draft(db, study, session, exercise_id, payload.answer)
    except service.ClassStateError as exc:
        raise _conflict(exc)
    return {"exerciseId": exercise_id, "savedAt": draft.updated_at, "status": session.status.value}


@router.post("/{class_id}/answers/{exercise_id}/transcribe")
async def transcribe_answer_audio(
    class_id: int,
    exercise_id: int,
    request: Request,
    study: CurrentStudy,
    db: DbSession,
) -> dict:
    """SPEAK final: audio temporal -> STT + fonética -> borrador. El audio se descarta."""
    session = _get_class(db, study, class_id)
    if session.status not in (ClassSessionStatus.READY, ClassSessionStatus.IN_PROGRESS):
        raise HTTPException(status.HTTP_409_CONFLICT, "La clase ya fue enviada.")

    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.class_session_id != session.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejercicio inexistente.")
    if exercise.response_mode.value != "SPEAK":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este ejercicio no se responde hablando.")

    audio = await request.body()
    if not audio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La grabación está vacía.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La grabación supera 6 MB.")

    mime_type = (request.headers.get("content-type") or "audio/webm").split(";", 1)[0].strip()
    if not mime_type.startswith("audio/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Formato de audio no soportado.")

    duration_header = request.headers.get("x-audio-duration-ms")
    try:
        duration_ms = int(duration_header) if duration_header else None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duración de audio inválida.")
    if duration_ms is not None and not (1 <= duration_ms <= MAX_AUDIO_DURATION_MS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La grabación supera 60 segundos.")

    try:
        result = transcribe_audio(
            db,
            study.account,
            audio=audio,
            mime_type=mime_type,
            usage_context=AIUsageContext(
                organization_id=exercise.organization_id,
                membership_id=exercise.membership_id,
                subject_type="EXERCISE",
                subject_id=exercise.id,
                subject_label=(
                    f"{'Examen' if session.kind == SessionKind.EXAM else 'Clase'} "
                    f"#{session.id} · Ejercicio {service.exercise_display_number(db, exercise)}"
                ),
                subject_route=f"/app/clase/{session.id}",
            ),
        )
    except NoAIAvailable as exc:
        detail = "No hay una conexión disponible que pueda transcribir audio."
        if exc.errors:
            detail += " " + "; ".join(exc.errors)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)

    raw_ai = connection_snapshot(result.connection)
    ai = public_trace(db, raw_ai, study.account)
    pronunciation_result = normalize_ai_pronunciation(
        result.pronunciation,
        result.text,
        raw_ai["provider"],
        model=raw_ai["model"],
        connection=raw_ai["connection"],
        provider_label=raw_ai["providerLabel"],
    )
    if pronunciation_result is not None:
        # T-055: se guarda el origen para poder ocultar la conexión de plataforma al mostrarla.
        pronunciation_result["ownerType"] = raw_ai["ownerType"]

    try:
        draft = service.save_draft(
            db,
            study,
            session,
            exercise_id,
            result.text,
            audio_duration_ms=duration_ms,
            pronunciation_result=pronunciation_result,
        )
    except service.ClassStateError as exc:
        raise _conflict(exc)

    return {
        "exerciseId": exercise_id,
        "transcript": result.text,
        "durationMs": duration_ms,
        "savedAt": draft.updated_at,
        "provider": ai["connection"],
        "ai": ai,
        "switched": result.switched,
        "pronunciationResult": public_trace(db, pronunciation_result, study.account),
    }


@router.post("/{class_id}/submit")
def submit_class(
    class_id: int, payload: SubmitRequest, study: CurrentStudy, db: DbSession
) -> dict:
    session = _get_class(db, study, class_id)
    try:
        service.submit(db, study, session, payload.answers)
    except service.ClassStateError as exc:
        raise _conflict(exc)
    notice = None
    if session.status == ClassSessionStatus.AWAITING_EVALUATION:
        notice = (
            "Tus respuestas están guardadas. La corrección está pendiente porque "
            "no hay conexiones de IA disponibles; se reintentará automáticamente."
        )
    return _detail(db, session, notice)


@router.post("/{class_id}/retake")
def retake_class(class_id: int, study: CurrentStudy, db: DbSession) -> dict:
    session = _get_class(db, study, class_id)
    try:
        service.retake(db, session)
    except service.ClassStateError as exc:
        raise _conflict(exc)
    return _detail(db, session)


@router.post("/{class_id}/exercises/{exercise_id}/signals")
def record_signal(
    class_id: int, exercise_id: int, payload: SignalRequest, study: CurrentStudy, db: DbSession
) -> dict:
    """Registra una escucha (y si fue lenta) o un intento de práctica de pronunciación."""
    session = _get_class(db, study, class_id)
    if payload.kind == "practice" and payload.score is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta el puntaje de la práctica.")
    try:
        signals = service.record_signals(
            db,
            study,
            session,
            exercise_id,
            listen_play=payload.kind == "listen",
            slow=payload.slow,
            practice_score=payload.score if payload.kind == "practice" else None,
            retake=payload.kind == "retake",
        )
    except service.ClassStateError as exc:
        raise _conflict(exc)
    return {"exerciseId": exercise_id, "signals": signals}


@router.post("/{class_id}/exercises/{exercise_id}/lesson")
def open_lesson(class_id: int, exercise_id: int, study: CurrentStudy, db: DbSession) -> dict:
    """"Necesito lección": devuelve la lección del tema y registra la ayuda (T-020)."""
    session = _get_class(db, study, class_id)
    try:
        return service.open_lesson(db, study, session, exercise_id)
    except service.ClassStateError as exc:
        raise _conflict(exc)


@router.post("/{class_id}/exercises/{exercise_id}/appeal")
def appeal_exercise(class_id: int, exercise_id: int, study: CurrentStudy, db: DbSession) -> dict:
    session = _get_class(db, study, class_id)
    try:
        attempt = service.appeal(db, study, session, exercise_id)
    except service.ClassStateError as exc:
        raise _conflict(exc)
    accepted = bool((attempt.evaluation_result or {}).get("appeal", {}).get("accepted"))
    notice = (
        "Revisión aceptada: tu respuesta se consideró válida."
        if accepted
        else "La revisión mantuvo la corrección original."
    )
    return _detail(db, session, notice)
