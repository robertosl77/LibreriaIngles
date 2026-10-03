"""PLATFORM_OWNER: catálogo de servicios y asignación manual de beneficios (T-004).

Un Servicio define vínculo × fuente de IA y metadatos comerciales. Los límites de consumo de la
IA de plataforma pertenecen exclusivamente a cada conexión de IA. La duración vive únicamente en
Benefit. Los otorgamientos manuales, campañas e invitaciones aplican un Benefit y terminan en
`grant_service`.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.accounts.models import Account, PlatformRole
from app.accounts.purge import purge_account_completely
from app.ai.models import AIConnection, AIConnectionOwnerType, utcnow
from app.ai.service import LIMIT_WINDOW, platform_requests
from app.benefits.models import Benefit
from app.benefits.service import apply_service_benefit
from app.campaigns.models import Campaign, CampaignStatus
from app.core.config import settings
from app.core.deps import DbSession
from app.invitations.models import Invitation, InvitationStatus
from app.invitations.service import refresh_status
from app.platform.api import PlatformOwner
from app.subscriptions.models import (
    AISource,
    Plan,
    ServiceLinkType,
    Subscription,
    SubscriptionOrigin,
    SubscriptionStatus,
)
from app.subscriptions.service import effective_service, revoke_service, seed_services

router = APIRouter(prefix="/platform", tags=["platform"])

ACCOUNTS_PAGE = 50


class ServiceUpdateIn(BaseModel):
    """Estado de una combinación fija Servicio × Fuente."""

    # No aceptar intentos de cambiar servicio/fuente ni campos antiguos silenciosamente.
    model_config = ConfigDict(extra="forbid")

    active: bool


class GrantBenefitIn(BaseModel):
    benefitId: int


def _combination_blockers(db: DbSession, plan: Plan) -> dict[str, int]:
    now = utcnow()
    active_accounts = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.plan_id == plan.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            (Subscription.expires_at.is_(None) | (Subscription.expires_at > now)),
        )
    ) or 0
    active_benefits = db.scalar(
        select(func.count(Benefit.id)).where(
            Benefit.plan_id == plan.id,
            Benefit.active.is_(True),
            Benefit.deleted_at.is_(None),
        )
    ) or 0
    active_campaigns = db.scalar(
        select(func.count(Campaign.id))
        .join(Benefit, Benefit.id == Campaign.benefit_id)
        .where(
            Benefit.plan_id == plan.id,
            Campaign.deleted_at.is_(None),
            Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
        )
    ) or 0

    invitations = db.scalars(
        select(Invitation)
        .join(Benefit, Benefit.id == Invitation.benefit_id)
        .where(Benefit.plan_id == plan.id)
    ).all()
    for invitation in invitations:
        refresh_status(db, invitation, now=now)
    active_invitations = sum(
        1 for invitation in invitations if invitation.status == InvitationStatus.ACTIVE
    )

    return {
        "activeAccounts": int(active_accounts),
        "activeBenefits": int(active_benefits),
        "activeCampaigns": int(active_campaigns),
        "activeInvitations": int(active_invitations),
    }


def _service_out(db: DbSession, plan: Plan) -> dict:
    blockers = _combination_blockers(db, plan)
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "source": plan.ai_source.value,
        "linkType": plan.link_type.value,
        "description": plan.description,
        "active": plan.active,
        **blockers,
        "canDisable": not any(blockers.values()),
    }


def _apply(plan: Plan, payload: ServiceUpdateIn, db: DbSession) -> None:
    if plan.active and not payload.active:
        blockers = _combination_blockers(db, plan)
        if any(blockers.values()):
            parts = []
            if blockers["activeAccounts"]:
                parts.append(f'{blockers["activeAccounts"]} cuenta(s) vigente(s)')
            if blockers["activeBenefits"]:
                parts.append(f'{blockers["activeBenefits"]} beneficio(s) activo(s)')
            if blockers["activeCampaigns"]:
                parts.append(f'{blockers["activeCampaigns"]} campaña(s) activa(s)/pausada(s)')
            if blockers["activeInvitations"]:
                parts.append(f'{blockers["activeInvitations"]} invitación(es) vigente(s)')
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No se puede deshabilitar la combinación mientras tenga " + ", ".join(parts) + ".",
            )
    plan.active = payload.active


@router.get("/services")
def list_services(_: PlatformOwner, db: DbSession) -> list[dict]:
    seed_services(db)
    db.commit()
    plans = db.scalars(select(Plan).order_by(Plan.id)).all()
    rows = [_service_out(db, plan) for plan in plans]
    db.commit()
    return rows


@router.put("/services/{service_id}")
def update_service(service_id: int, payload: ServiceUpdateIn, _: PlatformOwner, db: DbSession) -> dict:
    plan = db.get(Plan, service_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Servicio inexistente.")
    _apply(plan, payload, db)
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


@router.post("/accounts/{account_id}/benefit")
def grant_benefit(
    account_id: int,
    payload: GrantBenefitIn,
    owner: PlatformOwner,
    db: DbSession,
) -> dict:
    """Asignación manual: el OWNER establece o reemplaza el Benefit en una sola acción."""
    account = _account(db, account_id)
    benefit = db.get(Benefit, payload.benefitId)
    if (
        benefit is None
        or benefit.organization_id is not None
        or not benefit.active
        or benefit.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente o inactivo.")

    plan = db.get(Plan, benefit.plan_id)
    if plan is None or not plan.active or plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "El servicio del beneficio no está disponible.")

    result = apply_service_benefit(
        db,
        benefit,
        account,
        granted_by=owner,
        origin=SubscriptionOrigin.MANUAL,
        note=f"Otorgamiento manual · beneficio #{benefit.id}: {benefit.name}",
        replace_existing=True,
    )
    if not result.applied:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            result.error or "El beneficio no pudo aplicarse.",
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
