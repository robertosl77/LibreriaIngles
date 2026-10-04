"""API única de Consumo para persona, organización y PLATFORM_OWNER (T-049/T-053)."""

from statistics import median
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import case, func, select

from app.accounts.models import Account, PlatformRole
from app.ai.models import AIConnectionOwnerType, AIUsageEvent
from app.ai.service import HEALTH_CHECK, PLATFORM_LABEL
from app.classes import service as class_service
from app.classes.reference import exercise_display_number
from app.core.deps import CurrentAccount, DbSession
from app.memberships.models import Membership, MembershipRole, MembershipStatus
from app.organizations.models import Organization
from app.learning.models import Attempt, ClassSession, DraftAnswer, Exercise, SessionKind


router = APIRouter(prefix="/ai/usage", tags=["ai-consumption"])
UsageScope = Literal["ME", "ORGANIZATION", "PLATFORM"]


def _is_owner(account: Account) -> bool:
    return account.platform_role == PlatformRole.PLATFORM_OWNER


def _organization_admin(
    db,
    account: Account,
    organization_id: int,
) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.account_id == account.id,
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.ADMIN,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )


def _available_scopes(db, account: Account) -> list[dict]:
    scopes = [{"kind": "ME", "id": None, "label": "Mi consumo"}]

    if _is_owner(account):
        scopes.append({"kind": "PLATFORM", "id": None, "label": "Plataforma · global"})

    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.account_id == account.id,
            Membership.role == MembershipRole.ADMIN,
            Membership.status == MembershipStatus.ACTIVE,
            Organization.active.is_(True),
        )
        .order_by(Organization.display_name, Organization.id)
    ).all()
    scopes.extend(
        {
            "kind": "ORGANIZATION",
            "id": organization.id,
            "label": organization.display_name,
        }
        for _, organization in rows
    )
    return scopes


def _filters_for_scope(
    db,
    account: Account,
    scope: UsageScope,
    organization_id: int | None,
):
    filters = [AIUsageEvent.operation != HEALTH_CHECK]

    if scope == "ME":
        filters.append(AIUsageEvent.account_id == account.id)
        return filters

    if scope == "PLATFORM":
        if not _is_owner(account):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo PLATFORM_OWNER.")
        return filters

    if organization_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Elegí una organización.",
        )
    if not _is_owner(account) and _organization_admin(db, account, organization_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No administrás esta organización.")
    filters.append(AIUsageEvent.organization_id == organization_id)
    return filters


def _actual_source(owner_type: AIConnectionOwnerType) -> str:
    if owner_type == AIConnectionOwnerType.PLATFORM:
        return "PLATFORM"
    if owner_type == AIConnectionOwnerType.ORGANIZATION:
        return "ORGANIZATION"
    return "BYOK"


def _can_view_event(db, viewer: Account, event: AIUsageEvent) -> bool:
    if _is_owner(viewer) or event.account_id == viewer.id:
        return True
    return bool(
        event.organization_id is not None
        and _organization_admin(db, viewer, event.organization_id) is not None
    )


def _human_subject(db, event: AIUsageEvent) -> dict | None:
    if not event.subject_type and not event.subject_label:
        return None

    if event.subject_type == "EXERCISE" and event.subject_id is not None:
        exercise = db.get(Exercise, event.subject_id)
        if exercise is not None:
            session = db.get(ClassSession, exercise.class_session_id)
            if session is not None:
                number = exercise_display_number(db, exercise)
                kind = "Examen" if session.kind == SessionKind.EXAM else "Clase"
                return {
                    "type": event.subject_type,
                    "id": event.subject_id,
                    "label": f"{kind} #{session.id} · Ejercicio {number}",
                    "classId": session.id,
                    "exerciseNumber": number,
                    "previewable": True,
                }

    if event.subject_type in {"CLASS", "EXAM"} and event.subject_id is not None:
        session = db.get(ClassSession, event.subject_id)
        if session is not None:
            kind = "Examen" if session.kind == SessionKind.EXAM else "Clase"
            return {
                "type": event.subject_type,
                "id": event.subject_id,
                "label": f"{kind} #{session.id}",
                "classId": session.id,
                "exerciseNumber": None,
                "previewable": True,
            }

    return {
        "type": event.subject_type,
        "id": event.subject_id,
        "label": event.subject_label,
        "classId": None,
        "exerciseNumber": None,
        "previewable": False,
    }


def _attempt_for_event(db, event: AIUsageEvent, exercise_id: int) -> Attempt | None:
    """Busca el intento asociado temporalmente al evento, no simplemente el último.

    Corrección IA ocurre después de crear Attempt. Transcripción ocurre antes de
    enviar la clase, por eso en ese caso se toma el primer intento posterior.
    """
    query = select(Attempt).where(Attempt.exercise_id == exercise_id)
    if event.account_id is not None:
        query = query.where(Attempt.account_id == event.account_id)

    if event.operation == "transcribe_audio":
        candidate = db.scalar(
            query.where(Attempt.created_at >= event.created_at).order_by(
                Attempt.created_at.asc(), Attempt.id.asc()
            )
        )
        if candidate is not None:
            return candidate

    return db.scalar(
        query.where(Attempt.created_at <= event.created_at).order_by(
            Attempt.created_at.desc(), Attempt.id.desc()
        )
    )


def _execution_context(
    event: AIUsageEvent,
    exercise: Exercise,
    attempt: Attempt | None,
    draft: DraftAnswer | None,
) -> dict:
    """Datos observables que ayudan a explicar por qué una operación consumió IA."""
    signals = dict(
        (attempt.signals if attempt else None)
        or (draft.signals if draft else None)
        or {}
    )
    pronunciation = (
        attempt.pronunciation_result
        if attempt and attempt.pronunciation_result
        else (draft.pronunciation_result if draft else None)
    )
    assistance = (
        attempt.assistance.value
        if attempt
        else (draft.assistance.value if draft else "NONE")
    )
    response_mode = (
        attempt.response_mode.value
        if attempt
        else exercise.response_mode.value
    )
    evaluation_source = (
        attempt.evaluation_source.value
        if attempt and attempt.evaluation_source
        else None
    )
    audio_duration_ms = (
        attempt.audio_duration_ms
        if attempt
        else (draft.audio_duration_ms if draft else None)
    )
    practice_scores = [
        int(score) for score in (signals.get("practiceScores") or []) if score is not None
    ]
    content = exercise.content or {}

    return {
        "operation": event.operation,
        "presentationMode": exercise.presentation_mode.value,
        "responseMode": response_mode,
        "evaluationMode": exercise.evaluation_mode.value,
        "evaluationSource": evaluation_source,
        "audioDurationMs": audio_duration_ms,
        "listenPlays": int(signals.get("listenPlays", 0) or 0),
        "listenSlowPlays": int(signals.get("listenSlowPlays", 0) or 0),
        "speakRetakes": int(signals.get("speakRetakes", 0) or 0),
        "pronunciationPracticeScores": practice_scores,
        "pronunciationEvaluated": bool(pronunciation),
        "assistance": assistance,
        "contextStats": {
            "instructionChars": len(exercise.instruction or ""),
            "questionChars": len(exercise.prompt or ""),
            "passageChars": len(str(content.get("passage") or "")),
            "answerChars": len(
                (attempt.raw_answer if attempt else (draft.answer_text if draft else "")) or ""
            ),
            "options": len(content.get("options") or []),
            "expectedConcepts": len(exercise.expected_concepts or []),
        },
    }


def _exercise_preview(db, event: AIUsageEvent, exercise: Exercise) -> dict:
    session = db.get(ClassSession, exercise.class_session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clase asociada inexistente.")

    attempt = _attempt_for_event(db, event, exercise.id)
    draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise.id))
    conversation = (exercise.content or {}).get("conversation") or None
    result = attempt.evaluation_result or {} if attempt else {}

    return {
        "kind": "EXERCISE",
        "class": {
            "id": session.id,
            "kind": session.kind.value,
            "label": f"{'Examen' if session.kind == SessionKind.EXAM else 'Clase'} #{session.id}",
            "title": session.title,
            "targetLevel": session.target_level,
        },
        "exercise": {
            "id": exercise.id,
            "number": exercise_display_number(db, exercise),
            "type": exercise.exercise_type,
            "area": exercise.area,
            "skillKey": exercise.skill_key,
            "instruction": exercise.instruction,
            "question": exercise.prompt,
            "passage": (exercise.content or {}).get("passage"),
            "options": (exercise.content or {}).get("options"),
            "conversation": conversation,
            "presentation": exercise.presentation_mode.value,
            "responseMode": exercise.response_mode.value,
            "answer": attempt.raw_answer if attempt else (draft.answer_text if draft else None),
            "score": attempt.score if attempt else None,
            "result": result.get("result") if result else None,
            "feedback": result.get("feedback") if result else None,
            "correctAnswer": result.get("correctAnswer") if result else None,
            "executionContext": _execution_context(event, exercise, attempt, draft),
        },
    }


def _class_preview(db, event: AIUsageEvent, session: ClassSession) -> dict:
    items = []
    type_counts: dict[str, int] = {}
    presentation_counts: dict[str, int] = {}
    response_counts: dict[str, int] = {}
    logical_numbers: set[int] = set()

    for exercise in class_service.exercises_of(db, session):
        attempt = _attempt_for_event(db, event, exercise.id)
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise.id))
        result = attempt.evaluation_result or {} if attempt else {}
        number = exercise_display_number(db, exercise)
        logical_numbers.add(number)
        type_counts[exercise.exercise_type] = type_counts.get(exercise.exercise_type, 0) + 1
        presentation = exercise.presentation_mode.value
        response_mode = exercise.response_mode.value
        presentation_counts[presentation] = presentation_counts.get(presentation, 0) + 1
        response_counts[response_mode] = response_counts.get(response_mode, 0) + 1
        items.append(
            {
                "id": exercise.id,
                "number": number,
                "type": exercise.exercise_type,
                "area": exercise.area,
                "instruction": exercise.instruction,
                "question": exercise.prompt,
                "passage": (exercise.content or {}).get("passage"),
                "conversation": (exercise.content or {}).get("conversation"),
                "presentation": presentation,
                "responseMode": response_mode,
                "answer": attempt.raw_answer if attempt else (draft.answer_text if draft else None),
                "score": attempt.score if attempt else None,
                "feedback": result.get("feedback") if result else None,
            }
        )
    return {
        "kind": "CLASS",
        "operation": event.operation,
        "class": {
            "id": session.id,
            "kind": session.kind.value,
            "label": f"{'Examen' if session.kind == SessionKind.EXAM else 'Clase'} #{session.id}",
            "title": session.title,
            "targetLevel": session.target_level,
            "status": session.status.value,
            "score": session.score,
        },
        "generationSummary": {
            "logicalExercises": len(logical_numbers),
            "storedExerciseRows": len(items),
            "types": type_counts,
            "presentationModes": presentation_counts,
            "responseModes": response_counts,
        },
        "exercises": items,
    }


def _execution_summaries(db, execution_ids: set[str]) -> dict[str, dict]:
    """Resumen de una ejecución lógica, incluyendo todos sus intentos de failover."""
    if not execution_ids:
        return {}

    events = db.scalars(
        select(AIUsageEvent)
        .where(AIUsageEvent.execution_id.in_(execution_ids))
        .order_by(AIUsageEvent.execution_id, AIUsageEvent.attempt_index, AIUsageEvent.id)
    ).all()
    grouped: dict[str, list[AIUsageEvent]] = {}
    for event in events:
        if event.execution_id:
            grouped.setdefault(event.execution_id, []).append(event)

    summaries: dict[str, dict] = {}
    for execution_id, attempts in grouped.items():
        success = any(item.success for item in attempts)
        had_failure = any(not item.success for item in attempts)
        if success and had_failure:
            state = "RECOVERED_BY_FAILOVER"
        elif success:
            state = "OK"
        else:
            state = "INTERRUPTED"
        summaries[execution_id] = {
            "attempts": len(attempts),
            "status": state,
        }
    return summaries


_DIAGNOSTIC_LABELS = {
    "systemChars": "Prompt base / instrucciones del sistema",
    "userChars": "Contexto dinámico enviado",
    "audioBytes": "Tamaño del audio",
    "responseJsonChars": "Tamaño estructural de la respuesta",
    "instructionChars": "Consigna",
    "questionChars": "Pregunta",
    "passageChars": "Texto / pasaje",
    "stimulusChars": "Estímulo de escucha",
    "answerChars": "Respuesta del alumno",
    "optionsChars": "Opciones",
    "referenceAnswersChars": "Respuestas de referencia",
    "objectivesChars": "Objetivos curriculares",
    "conversationChars": "Historial conversacional",
    "conversationTurns": "Turnos de conversación",
    "slotCount": "Slots solicitados",
    "conversationSlots": "Slots conversacionales",
    "descriptionChars": "Descripción del asistente",
    "benefitCount": "Beneficios disponibles",
    "capabilityCount": "Capacidades disponibles",
}


def _diagnostic_numbers(snapshot: dict | None) -> dict[str, float]:
    if not isinstance(snapshot, dict):
        return {}
    values: dict[str, float] = {}
    for key in ("systemChars", "userChars", "audioBytes", "responseJsonChars"):
        value = snapshot.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[key] = float(value)
    details = snapshot.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[key] = float(value)
    return values


def _median(values: list[int | float]) -> float | None:
    return float(median(values)) if values else None


def _ratio(value: int | float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline <= 0:
        return None
    return round(float(value) / baseline, 2)


def _diagnostic_payload(db, event: AIUsageEvent, viewer: Account) -> dict:
    """Explica el consumo con hechos observables; no inventa causalidad."""
    query = select(AIUsageEvent).where(
        AIUsageEvent.operation == event.operation,
        AIUsageEvent.provider == event.provider,
        AIUsageEvent.model == event.model,
        AIUsageEvent.success.is_(True),
        AIUsageEvent.total_tokens.is_not(None),
        AIUsageEvent.operation != HEALTH_CHECK,
    )
    if event.subject_type is not None:
        query = query.where(AIUsageEvent.subject_type == event.subject_type)

    if not _is_owner(viewer):
        if event.account_id == viewer.id:
            query = query.where(AIUsageEvent.account_id == viewer.id)
        elif event.organization_id is not None:
            query = query.where(AIUsageEvent.organization_id == event.organization_id)

    comparable = list(
        db.scalars(query.order_by(AIUsageEvent.created_at.desc()).limit(500)).all()
    )

    current_details = (
        event.diagnostic_snapshot.get("details")
        if isinstance(event.diagnostic_snapshot, dict)
        and isinstance(event.diagnostic_snapshot.get("details"), dict)
        else {}
    )
    cohort_exercise_type = None
    exercise_type = current_details.get("exerciseType")
    if exercise_type:
        same_type = [
            item
            for item in comparable
            if isinstance(item.diagnostic_snapshot, dict)
            and isinstance(item.diagnostic_snapshot.get("details"), dict)
            and item.diagnostic_snapshot["details"].get("exerciseType") == exercise_type
        ]
        if len(same_type) >= 3:
            comparable = same_type
            cohort_exercise_type = exercise_type

    prompt_fingerprint = (
        event.diagnostic_snapshot.get("systemFingerprint")
        if isinstance(event.diagnostic_snapshot, dict)
        else None
    )
    cohort_prompt_fingerprint = None
    if prompt_fingerprint:
        same_prompt = [
            item
            for item in comparable
            if isinstance(item.diagnostic_snapshot, dict)
            and item.diagnostic_snapshot.get("systemFingerprint") == prompt_fingerprint
        ]
        if len(same_prompt) >= 3:
            comparable = same_prompt
            cohort_prompt_fingerprint = prompt_fingerprint

    totals = [item.total_tokens for item in comparable if item.total_tokens is not None]
    sorted_totals = sorted(totals)
    total_median = _median(totals)
    p90 = (
        float(sorted_totals[int(round((len(sorted_totals) - 1) * 0.9))])
        if sorted_totals
        else None
    )

    metrics: list[dict] = []
    token_fields = [
        ("inputTokens", "Tokens de entrada", "input_tokens"),
        ("reasoningTokens", "Tokens de pensamiento", "reasoning_tokens"),
        ("outputTokens", "Tokens de salida", "output_tokens"),
    ]
    for key, label, attr in token_fields:
        current = getattr(event, attr)
        values = [getattr(item, attr) for item in comparable if getattr(item, attr) is not None]
        baseline = _median(values)
        if current is not None and baseline is not None:
            metrics.append(
                {
                    "key": key,
                    "label": label,
                    "value": float(current),
                    "median": baseline,
                    "ratio": _ratio(current, baseline),
                    "sampleSize": len(values),
                }
            )

    current_numbers = _diagnostic_numbers(event.diagnostic_snapshot)
    for key, current in current_numbers.items():
        values = [
            numbers[key]
            for item in comparable
            if key in (numbers := _diagnostic_numbers(item.diagnostic_snapshot))
        ]
        baseline = _median(values)
        if baseline is None:
            continue
        metrics.append(
            {
                "key": key,
                "label": _DIAGNOSTIC_LABELS.get(key, key),
                "value": current,
                "median": baseline,
                "ratio": _ratio(current, baseline),
                "sampleSize": len(values),
            }
        )

    signals = sorted(
        [
            metric
            for metric in metrics
            if metric["sampleSize"] >= 3
            and metric["ratio"] is not None
            and metric["ratio"] >= 1.5
        ],
        key=lambda metric: metric["ratio"],
        reverse=True,
    )[:8]

    hide_platform_engine = (
        event.owner_type == AIConnectionOwnerType.PLATFORM and not _is_owner(viewer)
    )
    cohort = {
        "operation": event.operation,
        "subjectType": event.subject_type,
        "provider": "PLATFORM" if hide_platform_engine else event.provider,
        "model": None if hide_platform_engine else event.model,
        "exerciseType": cohort_exercise_type,
        "promptFingerprint": cohort_prompt_fingerprint,
    }
    return {
        "tokens": {
            "input": event.input_tokens,
            "reasoning": event.reasoning_tokens,
            "output": event.output_tokens,
            "total": event.total_tokens,
        },
        "snapshot": event.diagnostic_snapshot,
        "comparison": {
            "sampleSize": len(totals),
            "enoughSample": len(totals) >= 3,
            "medianTotalTokens": total_median,
            "p90TotalTokens": p90,
            "totalVsMedian": _ratio(event.total_tokens, total_median),
            "cohort": cohort,
            "metrics": metrics,
            "signals": signals,
        },
        "note": (
            "Las diferencias son señales comparativas; no atribuyen causalidad ni tokens exactos a cada componente."
        ),
    }


def _serialize_event(
    db,
    event: AIUsageEvent,
    event_account: Account | None,
    viewer: Account,
    *,
    scope: UsageScope,
    execution_summary: dict | None = None,
) -> dict:
    hide_platform_engine = (
        event.owner_type == AIConnectionOwnerType.PLATFORM and not _is_owner(viewer)
    )
    own_event = event.account_id == viewer.id

    return {
        "id": event.id,
        "createdAt": event.created_at,
        "accountId": event.account_id,
        "accountEmail": event_account.email if event_account else None,
        "accountName": event_account.display_name if event_account else None,
        "organizationId": event.organization_id,
        "operation": event.operation,
        "provider": "PLATFORM" if hide_platform_engine else event.provider,
        "model": None if hide_platform_engine else event.model,
        "connectionName": PLATFORM_LABEL if hide_platform_engine else event.connection_name,
        "connectionOwnerType": event.owner_type.value,
        "serviceSource": event.service_source,
        "actualSource": _actual_source(event.owner_type),
        "inputTokens": event.input_tokens,
        "reasoningTokens": event.reasoning_tokens,
        "outputTokens": event.output_tokens,
        "totalTokens": event.total_tokens,
        "success": event.success,
        "errorCode": event.error_code,
        "execution": {
            "id": event.execution_id,
            "attempt": event.attempt_index,
            "attempts": execution_summary["attempts"],
            "status": execution_summary["status"],
        }
        if event.execution_id and execution_summary
        else None,
        "subject": (
            {
                **subject,
                # La clase completa sigue siendo navegable solo desde la propia cuenta.
                # ADMIN/OWNER auditan mediante el modal de solo lectura.
                "route": event.subject_route if own_event else None,
            }
            if (subject := _human_subject(db, event))
            else None
        ),
    }


@router.get("/scopes")
def usage_scopes(account: CurrentAccount, db: DbSession) -> list[dict]:
    """Scopes que el usuario autenticado puede consultar con el mismo motor."""
    return _available_scopes(db, account)


@router.get("/{event_id}/diagnostic")
def usage_diagnostic(
    event_id: int,
    account: CurrentAccount,
    db: DbSession,
) -> dict:
    """Diagnóstico auditable de cualquier llamada IA, tenga o no referencia visual."""
    event = db.get(AIUsageEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento de consumo inexistente.")
    if not _can_view_event(db, account, event):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tenés acceso a este consumo.")

    execution = None
    if event.execution_id:
        execution = _execution_summaries(db, {event.execution_id}).get(event.execution_id)

    return {
        "eventId": event.id,
        "operation": event.operation,
        "createdAt": event.created_at,
        "subject": _human_subject(db, event),
        "execution": {
            "id": event.execution_id,
            "attempt": event.attempt_index,
            "attempts": execution["attempts"],
            "status": execution["status"],
        }
        if event.execution_id and execution
        else None,
        "diagnostic": _diagnostic_payload(db, event, account),
    }


@router.get("/{event_id}/reference")
def usage_reference(
    event_id: int,
    account: CurrentAccount,
    db: DbSession,
    view: Literal["REFERENCE", "CLASS"] = "REFERENCE",
) -> dict:
    """Visor de solo lectura del trabajo asociado al evento de consumo."""
    event = db.get(AIUsageEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento de consumo inexistente.")
    if not _can_view_event(db, account, event):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tenés acceso a esta referencia.")

    if event.subject_type == "EXERCISE" and event.subject_id is not None:
        exercise = db.get(Exercise, event.subject_id)
        if exercise is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejercicio asociado inexistente.")
        if view == "CLASS":
            session = db.get(ClassSession, exercise.class_session_id)
            if session is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clase asociada inexistente.")
            preview = _class_preview(db, event, session)
            preview["sourceExerciseId"] = exercise.id
        else:
            preview = _exercise_preview(db, event, exercise)
    elif event.subject_type in {"CLASS", "EXAM"} and event.subject_id is not None:
        session = db.get(ClassSession, event.subject_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Clase asociada inexistente.")
        preview = _class_preview(db, event, session)
    else:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Este evento no tiene una referencia visualizable.",
        )

    preview["eventId"] = event.id
    preview["fullClassRoute"] = (
        f"/app/clase/{preview['class']['id']}"
        if event.account_id == account.id
        else None
    )
    return preview


@router.get("")
def usage(
    account: CurrentAccount,
    db: DbSession,
    scope: UsageScope = "ME",
    organizationId: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    filters = _filters_for_scope(db, account, scope, organizationId)

    total = db.scalar(select(func.count(AIUsageEvent.id)).where(*filters)) or 0
    correlated_executions = (
        db.scalar(
            select(func.count(func.distinct(AIUsageEvent.execution_id))).where(
                *filters,
                AIUsageEvent.execution_id.is_not(None),
            )
        )
        or 0
    )
    legacy_executions = (
        db.scalar(
            select(func.count(AIUsageEvent.id)).where(
                *filters,
                AIUsageEvent.execution_id.is_(None),
            )
        )
        or 0
    )
    executions = correlated_executions + legacy_executions
    measured = (
        db.scalar(
            select(func.count(AIUsageEvent.id)).where(
                *filters,
                AIUsageEvent.total_tokens.is_not(None),
            )
        )
        or 0
    )
    successful = (
        db.scalar(
            select(func.sum(case((AIUsageEvent.success.is_(True), 1), else_=0))).where(
                *filters
            )
        )
        or 0
    )
    sums = db.execute(
        select(
            func.coalesce(func.sum(AIUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.reasoning_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.output_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
        ).where(*filters)
    ).one()

    rows = db.execute(
        select(AIUsageEvent, Account)
        .outerjoin(Account, Account.id == AIUsageEvent.account_id)
        .where(*filters)
        .order_by(AIUsageEvent.created_at.desc(), AIUsageEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    execution_summaries = _execution_summaries(
        db,
        {event.execution_id for event, _ in rows if event.execution_id},
    )

    return {
        "scope": scope,
        "organizationId": organizationId if scope == "ORGANIZATION" else None,
        "scopes": _available_scopes(db, account),
        "summary": {
            "executions": int(executions),
            "requests": int(total),
            "successful": int(successful),
            "errors": int(total - successful),
            "measuredRequests": int(measured),
            "inputTokens": int(sums[0] or 0),
            "reasoningTokens": int(sums[1] or 0),
            "outputTokens": int(sums[2] or 0),
            "totalTokens": int(sums[3] or 0),
        },
        "offset": offset,
        "limit": limit,
        "total": int(total),
        "rows": [
            _serialize_event(
                db,
                event,
                event_account,
                account,
                scope=scope,
                execution_summary=execution_summaries.get(event.execution_id or ""),
            )
            for event, event_account in rows
        ],
    }
