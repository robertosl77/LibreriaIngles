"""Portal del PLATFORM_OWNER: catálogo de servicios y asignación a cuentas (T-004, etapa 1).

sr.macros define servicios (vínculo × fuente de IA, duración y tope) y se los otorga a mano a
una cuenta, por N días o sin vencimiento. Campañas (etapa 2) e invitaciones (etapa 3) usarán
el mismo `grant_service`.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.accounts.models import Account, PlatformRole
from app.accounts.purge import purge_account_completely
from app.ai.models import AIConnection, AIConnectionOwnerType, utcnow
from app.ai.service import LIMIT_WINDOW, platform_requests
from app.core.config import settings
from app.core.deps import DbSession
from app.platform.api import PlatformOwner
from app.subscriptions.models import (
    AISource,
    Plan,
    ServiceLinkType,
    Subscription,
    SubscriptionStatus,
)
from app.subscriptions.service import (
    effective_service,
    grant_service,
    revoke_service,
    seed_services,
)

router = APIRouter(prefix="/platform", tags=["platform"])

ACCOUNTS_PAGE = 50


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    source: AISource
    linkType: ServiceLinkType = ServiceLinkType.PERSONAL
    durationDays: int | None = Field(default=None, ge=1, le=3650)
    dailyRequestLimit: int | None = Field(default=None, ge=1, le=100000)
    description: str | None = Field(default=None, max_length=300)
    active: bool = True


class GrantIn(BaseModel):
    serviceId: int
    days: int | None = Field(default=None, ge=1, le=3650)
    note: str | None = Field(default=None, max_length=200)


def _service_out(db, plan: Plan) -> dict:
    holders = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.plan_id == plan.id, Subscription.status == SubscriptionStatus.ACTIVE
        )
    )
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "source": plan.ai_source.value,
        "linkType": plan.link_type.value,
        "durationDays": plan.duration_days,
        "dailyRequestLimit": plan.daily_request_limit,
        "description": plan.description,
        "active": plan.active,
        "activeAccounts": int(holders or 0),
    }


def _apply(plan: Plan, payload: ServiceIn) -> None:
    if payload.linkType == ServiceLinkType.CORPORATE:
        # El vínculo corporativo llega con las empresas (T-004 etapa 5 / T-005).
        raise HTTPException(
            422, "Los servicios corporativos llegan con empresas."
        )
    plan.name = payload.name.strip()
    plan.ai_source = payload.source
    plan.link_type = payload.linkType
    plan.duration_days = payload.durationDays
    plan.daily_request_limit = payload.dailyRequestLimit
    plan.description = (payload.description or "").strip() or None
    plan.active = payload.active


@router.get("/services")
def list_services(_: PlatformOwner, db: DbSession) -> list[dict]:
    seed_services(db)
    db.commit()
    plans = db.scalars(select(Plan).order_by(Plan.id)).all()
    return [_service_out(db, plan) for plan in plans]


@router.post("/services", status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceIn, _: PlatformOwner, db: DbSession) -> dict:
    plan = Plan(code="", name="", ai_source=payload.source)
    _apply(plan, payload)
    db.add(plan)
    db.flush()
    plan.code = f"SERVICE_{plan.id}"
    db.commit()
    return _service_out(db, plan)


@router.put("/services/{service_id}")
def update_service(service_id: int, payload: ServiceIn, _: PlatformOwner, db: DbSession) -> dict:
    plan = db.get(Plan, service_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Servicio inexistente.")
    _apply(plan, payload)
    db.commit()
    return _service_out(db, plan)


def _account_out(db, account: Account) -> dict:
    service = effective_service(db, account)
    own_keys = db.scalar(
        select(func.count(AIConnection.id)).where(
            AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT,
            AIConnection.owner_id == account.id,
            AIConnection.active.is_(True),
        )
    )
    return {
        "id": account.id,
        "email": account.email,
        "displayName": account.display_name,
        "isPlatformOwner": account.platform_role == PlatformRole.PLATFORM_OWNER,
        "createdAt": account.created_at,
        "firstLoginAt": account.first_login_at,
        "devPurgeAllowed": (
            settings.dev_account_purge_allowed
            and account.platform_role != PlatformRole.PLATFORM_OWNER
        ),
        "ownConnections": int(own_keys or 0),
        "platformRequests24h": platform_requests(db, account.id, since=utcnow() - LIMIT_WINDOW),
        "service": service.payload(),
    }


@router.get("/accounts")
def list_accounts(
    _: PlatformOwner,
    db: DbSession,
    q: str | None = Query(default=None, max_length=120),
) -> list[dict]:
    query = select(Account).order_by(Account.created_at.desc(), Account.id.desc())
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(func.lower(Account.email).like(like), func.lower(Account.display_name).like(like))
        )
    accounts = db.scalars(query.limit(ACCOUNTS_PAGE)).all()
    result = [_account_out(db, account) for account in accounts]
    db.commit()  # persiste vencimientos perezosos
    return result


def _account(db, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta inexistente.")
    return account


@router.post("/accounts/{account_id}/service")
def grant(account_id: int, payload: GrantIn, owner: PlatformOwner, db: DbSession) -> dict:
    account = _account(db, account_id)
    plan = db.get(Plan, payload.serviceId)
    if plan is None or not plan.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Servicio inexistente o inactivo.")
    grant_service(
        db, account, plan, granted_by=owner, days=payload.days, note=(payload.note or None)
    )
    db.commit()
    return _account_out(db, account)


@router.delete("/accounts/{account_id}/service")
def revoke(account_id: int, _: PlatformOwner, db: DbSession) -> dict:
    account = _account(db, account_id)
    revoke_service(db, account)
    db.commit()
    return _account_out(db, account)



@router.delete("/accounts/{account_id}/dev-purge", status_code=status.HTTP_204_NO_CONTENT)
def dev_purge_account(account_id: int, _: PlatformOwner, db: DbSession) -> None:
    """Borra físicamente una cuenta de prueba. Disponible solo en local/dev/test."""
    if not settings.dev_account_purge_allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No disponible.")

    account = _account(db, account_id)
    if (
        account.platform_role == PlatformRole.PLATFORM_OWNER
        or account.email.lower() in settings.platform_owner_email_set
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La cuenta propietaria de la plataforma no se puede eliminar.",
        )

    purge_account_completely(db, account)
    db.commit()
