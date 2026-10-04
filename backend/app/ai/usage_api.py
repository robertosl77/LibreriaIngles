"""API única de Consumo para persona, organización y PLATFORM_OWNER (T-049/T-053)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import case, func, select

from app.accounts.models import Account, PlatformRole
from app.ai.models import AIConnectionOwnerType, AIUsageEvent
from app.ai.service import HEALTH_CHECK, PLATFORM_LABEL
from app.classes import service as class_service
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
                number = class_service.exercise_display_number(db, exercise)
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
    query = select(Attempt).where(Attempt.exercise_id == exercise_id)
    if event.account_id is not None:
        query = query.where(Attempt.account_id == event.account_id)
    return db.scalar(query.order_by(Attempt.attempt_number.desc(), Attempt.id.desc()))


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
            "number": class_service.exercise_display_number(db, exercise),
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
        },
    }


def _class_preview(db, event: AIUsageEvent, session: ClassSession) -> dict:
    items = []
    for exercise in class_service.exercises_of(db, session):
        attempt = _attempt_for_event(db, event, exercise.id)
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise.id))
        result = attempt.evaluation_result or {} if attempt else {}
        items.append(
            {
                "id": exercise.id,
                "number": class_service.exercise_display_number(db, exercise),
                "type": exercise.exercise_type,
                "area": exercise.area,
                "instruction": exercise.instruction,
                "question": exercise.prompt,
                "passage": (exercise.content or {}).get("passage"),
                "conversation": (exercise.content or {}).get("conversation"),
                "answer": attempt.raw_answer if attempt else (draft.answer_text if draft else None),
                "score": attempt.score if attempt else None,
                "feedback": result.get("feedback") if result else None,
            }
        )
    return {
        "kind": "CLASS",
        "class": {
            "id": session.id,
            "kind": session.kind.value,
            "label": f"{'Examen' if session.kind == SessionKind.EXAM else 'Clase'} #{session.id}",
            "title": session.title,
            "targetLevel": session.target_level,
            "status": session.status.value,
            "score": session.score,
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


@router.get("/{event_id}/reference")
def usage_reference(event_id: int, account: CurrentAccount, db: DbSession) -> dict:
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
            "outputTokens": int(sums[1] or 0),
            "totalTokens": int(sums[2] or 0),
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
