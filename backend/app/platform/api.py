"""Portal del PLATFORM_OWNER (T-006).

Muestra consumo de IA y estado de las conexiones de plataforma.
La gestión de conexiones (alta, límites, prueba, pausa, baja) usa /ai/connections?scope=platform.

No expone datos de estudio de los usuarios: solo metadatos de consumo.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func, select

from app.accounts.models import Account, PlatformRole
from app.ai.models import AIConnection, AIConnectionOwnerType, AIUsageEvent, utcnow
from app.ai.service import HEALTH_CHECK
from app.benefits.models import Benefit
from app.campaigns.models import Campaign
from app.invitations.models import Invitation
from app.subscriptions.models import Plan, Subscription, SubscriptionStatus
from app.core.deps import CurrentAccount, DbSession
from app.learning.models import ClassSession

router = APIRouter(prefix="/platform", tags=["platform"])

USAGE_DAYS = 14


def require_platform_owner(account: CurrentAccount) -> Account:
    if account.platform_role != PlatformRole.PLATFORM_OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo PLATFORM_OWNER.")
    return account


PlatformOwner = Annotated[Account, Depends(require_platform_owner)]


def _counts(db, *filters) -> dict:
    row = db.execute(
        select(
            func.count(AIUsageEvent.id),
            func.coalesce(func.sum(case((AIUsageEvent.success.is_(True), 1), else_=0)), 0),
        ).where(AIUsageEvent.operation != HEALTH_CHECK, *filters)
    ).one()
    total, ok = int(row[0] or 0), int(row[1] or 0)
    return {"requests": total, "successful": ok, "errors": total - ok}


@router.get("/overview")
def overview(_: PlatformOwner, db: DbSession) -> dict:
    now = utcnow()
    last_24h = now - timedelta(hours=24)
    since_days = (now - timedelta(days=USAGE_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    platform_events = AIUsageEvent.owner_type == AIConnectionOwnerType.PLATFORM

    # Consumo diario (todas las conexiones), separado plataforma / usuarios.
    day = func.date(AIUsageEvent.created_at)
    daily_rows = db.execute(
        select(
            day,
            func.count(AIUsageEvent.id),
            func.sum(case((platform_events, 1), else_=0)),
            func.sum(case((AIUsageEvent.success.is_(False), 1), else_=0)),
        )
        .where(AIUsageEvent.operation != HEALTH_CHECK, AIUsageEvent.created_at >= since_days)
        .group_by(day)
    ).all()
    by_day = {str(r[0]): r for r in daily_rows}
    daily = []
    for offset in range(USAGE_DAYS):
        date = (since_days + timedelta(days=offset)).date().isoformat()
        row = by_day.get(date)
        daily.append(
            {
                "date": date,
                "requests": int(row[1]) if row else 0,
                "platform": int(row[2] or 0) if row else 0,
                "errors": int(row[3] or 0) if row else 0,
            }
        )

    # Consumo por conexión de plataforma.
    connections = db.scalars(
        select(AIConnection)
        .where(AIConnection.owner_type == AIConnectionOwnerType.PLATFORM)
        .order_by(AIConnection.priority, AIConnection.id)
    ).all()
    per_connection = []
    for connection in connections:
        of_connection = AIUsageEvent.connection_id == connection.id
        per_connection.append(
            {
                "id": connection.id,
                "name": connection.name,
                "last24h": _counts(db, of_connection, AIUsageEvent.created_at >= last_24h),
                "last30d": _counts(
                    db, of_connection, AIUsageEvent.created_at >= now - timedelta(days=30)
                ),
            }
        )

    # Cuentas que más consumen IA de plataforma (costo propio).
    top_rows = db.execute(
        select(Account.email, func.count(AIUsageEvent.id).label("requests"))
        .join(Account, Account.id == AIUsageEvent.account_id)
        .where(
            platform_events,
            AIUsageEvent.success.is_(True),
            AIUsageEvent.operation != HEALTH_CHECK,
            AIUsageEvent.created_at >= last_24h,
        )
        .group_by(Account.email)
        .order_by(func.count(AIUsageEvent.id).desc())
        .limit(10)
    ).all()

    active_accounts = db.scalar(
        select(func.count(func.distinct(AIUsageEvent.account_id))).where(
            AIUsageEvent.operation != HEALTH_CHECK,
            AIUsageEvent.created_at >= last_24h,
        )
    )

    benefit_usage = []
    benefits = db.scalars(
        select(Benefit).where(Benefit.deleted_at.is_(None)).order_by(Benefit.id)
    ).all()
    for item in benefits:
        benefit_usage.append({
            "id": item.id,
            "name": item.name,
            "campaigns": int(db.scalar(select(func.count(Campaign.id)).where(Campaign.benefit_id == item.id)) or 0),
            "invitations": int(db.scalar(select(func.count(Invitation.id)).where(Invitation.benefit_id == item.id)) or 0),
        })

    benefit_rows = db.execute(
        select(
            Account.email,
            Benefit.name,
            Plan.name,
            Subscription.origin,
            Subscription.expires_at,
        )
        .join(Subscription, Subscription.account_id == Account.id)
        .join(Benefit, Benefit.id == Subscription.benefit_id)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .order_by(Account.email)
        .limit(100)
    ).all()
    account_benefits = [
        {
            "email": row[0],
            "benefitName": row[1],
            "serviceName": row[2],
            "origin": row[3].value,
            "expiresAt": row[4],
        }
        for row in benefit_rows
    ]

    return {
        "last24h": {
            "all": _counts(db, AIUsageEvent.created_at >= last_24h),
            "platform": _counts(db, platform_events, AIUsageEvent.created_at >= last_24h),
            "activeAccounts": int(active_accounts or 0),
            "classesCreated": int(
                db.scalar(
                    select(func.count(ClassSession.id)).where(ClassSession.created_at >= last_24h)
                )
                or 0
            ),
        },
        "accounts": int(db.scalar(select(func.count(Account.id))) or 0),
        "daily": daily,
        "connections": per_connection,
        "topAccounts24h": [{"email": r[0], "requests": int(r[1])} for r in top_rows],
        "benefitUsage": benefit_usage,
        "accountBenefits": account_benefits,
    }


# ---------------------------------------------------------------- T-216: ejercicios en revisión


class BankDecision(BaseModel):
    action: str  # ACTIVATE | RETIRE | FIX
    acceptedAnswers: list[str] | None = None


@router.get("/bank/review")
def bank_review(_: PlatformOwner, db: DbSession) -> list[dict]:
    """Ejercicios del banco reportados por alumnos (no se sirven hasta decidir). Más reportados primero."""
    from app.classes import bank

    return bank.review_queue(db)


@router.post("/bank/{item_id}/decision")
def bank_decision(item_id: int, payload: BankDecision, _: PlatformOwner, db: DbSession) -> list[dict]:
    from app.classes import bank

    try:
        bank.decide(db, item_id, payload.action, payload.acceptedAnswers)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return bank.review_queue(db)
