"""API única de Consumo para persona, organización y PLATFORM_OWNER (T-049/T-053)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import case, func, select

from app.accounts.models import Account, PlatformRole
from app.ai.models import AIConnectionOwnerType, AIUsageEvent
from app.ai.service import HEALTH_CHECK, PLATFORM_LABEL
from app.core.deps import CurrentAccount, DbSession
from app.memberships.models import Membership, MembershipRole, MembershipStatus
from app.organizations.models import Organization


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
        "subject": {
            "type": event.subject_type,
            "id": event.subject_id,
            "label": event.subject_label,
            # Una ruta solo se entrega cuando el visor puede abrir razonablemente ese objeto
            # con los permisos actuales. El portal ADMIN definirá navegación corporativa en T-010.
            "route": event.subject_route if own_event or _is_owner(viewer) and event.account_id is None else None,
        }
        if event.subject_type or event.subject_label
        else None,
    }


@router.get("/scopes")
def usage_scopes(account: CurrentAccount, db: DbSession) -> list[dict]:
    """Scopes que el usuario autenticado puede consultar con el mismo motor."""
    return _available_scopes(db, account)


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
                event,
                event_account,
                account,
                scope=scope,
                execution_summary=execution_summaries.get(event.execution_id or ""),
            )
            for event, event_account in rows
        ],
    }
