"""PLATFORM_OWNER: definiciones reutilizables de beneficios (T-004)."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.benefits.models import Benefit, utcnow
from app.benefits.service import benefit_duration
from app.campaigns.models import Campaign, CampaignStatus
from app.core.deps import DbSession
from app.invitations.models import Invitation, InvitationStatus
from app.invitations.service import refresh_status
from app.platform.api import PlatformOwner
from app.subscriptions.models import AISource, Plan, ServiceLinkType, Subscription, SubscriptionStatus

router = APIRouter(prefix="/platform/benefits", tags=["platform"])


class BenefitIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    service: ServiceLinkType | None = None
    source: AISource | None = None
    # Compatibilidad temporal con consumidores anteriores; la UI nueva no lo usa.
    serviceId: int | None = None
    durationDays: int | None = Field(default=None, ge=1, le=3650)
    active: bool = True

    @model_validator(mode="after")
    def validate_axes(self):
        has_axes = self.service is not None or self.source is not None
        if has_axes and (self.service is None or self.source is None):
            raise ValueError("Servicio y fuente deben seleccionarse juntos.")
        if not has_axes and self.serviceId is None:
            raise ValueError("Debe seleccionarse servicio y fuente.")
        return self


SERVICE_LABELS = {
    ServiceLinkType.PERSONAL: "Personal",
    ServiceLinkType.CORPORATE: "Corporativa",
}


def _plan(db: DbSession, payload: BenefitIn) -> Plan:
    if payload.service is not None and payload.source is not None:
        if payload.service != ServiceLinkType.PERSONAL:
            raise HTTPException(422, "Los beneficios corporativos llegan con la etapa de empresas.")
        plan = db.scalar(
            select(Plan).where(
                Plan.link_type == payload.service,
                Plan.ai_source == payload.source,
            )
        )
    else:
        plan = db.get(Plan, payload.serviceId) if payload.serviceId else None

    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Combinación de servicio y fuente inexistente.")
    if plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "Los beneficios corporativos llegan con la etapa de empresas.")
    if payload.active and not plan.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La combinación de servicio y fuente está deshabilitada.",
        )
    return plan


def _delete_blockers(db: DbSession, benefit: Benefit) -> dict[str, int]:
    now = utcnow()
    active_beneficiaries = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.benefit_id == benefit.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            (Subscription.expires_at.is_(None) | (Subscription.expires_at > now)),
        )
    ) or 0
    active_campaigns = db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.benefit_id == benefit.id,
            Campaign.deleted_at.is_(None),
            Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
        )
    ) or 0

    invitations = db.scalars(
        select(Invitation).where(Invitation.benefit_id == benefit.id)
    ).all()
    for invitation in invitations:
        refresh_status(db, invitation, now=now)
    active_invitations = sum(
        1 for invitation in invitations if invitation.status == InvitationStatus.ACTIVE
    )
    return {
        "activeBeneficiaries": int(active_beneficiaries),
        "activeCampaigns": int(active_campaigns),
        "activeInvitations": int(active_invitations),
    }


def _out(db: DbSession, benefit: Benefit) -> dict:
    plan = db.get(Plan, benefit.plan_id)
    campaigns = db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.benefit_id == benefit.id,
            Campaign.deleted_at.is_(None),
        )
    ) or 0
    invitations = db.scalar(
        select(func.count(Invitation.id)).where(Invitation.benefit_id == benefit.id)
    ) or 0
    blockers = _delete_blockers(db, benefit)
    return {
        "id": benefit.id,
        "code": benefit.code,
        "name": benefit.name,
        "serviceId": benefit.plan_id,
        "combinationId": benefit.plan_id,
        "service": plan.link_type.value if plan else None,
        "serviceName": SERVICE_LABELS.get(plan.link_type, plan.link_type.value) if plan else "Servicio eliminado",
        "source": plan.ai_source.value if plan else None,
        "combinationName": plan.name if plan else "Combinación eliminada",
        "combinationActive": bool(plan.active) if plan else False,
        "durationDays": benefit.duration_days,
        "conflictPolicy": benefit.conflict_policy.value,
        "active": benefit.active,
        "usedByCampaigns": int(campaigns),
        "usedByInvitations": int(invitations),
        **blockers,
        "canDelete": not any(blockers.values()),
    }


def _apply(benefit: Benefit, payload: BenefitIn, db: DbSession) -> None:
    plan = _plan(db, payload)
    benefit.name = payload.name.strip()
    benefit.plan_id = plan.id
    benefit.duration_days = payload.durationDays
    benefit.active = payload.active


@router.get("")
def list_benefits(_: PlatformOwner, db: DbSession) -> list[dict]:
    rows = db.scalars(
        select(Benefit)
        .where(Benefit.organization_id.is_(None), Benefit.deleted_at.is_(None))
        .order_by(Benefit.id.asc())
    ).all()
    return [_out(db, row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_benefit(payload: BenefitIn, owner: PlatformOwner, db: DbSession) -> dict:
    plan = _plan(db, payload)
    benefit = Benefit(
        code=f"BENEFIT_{uuid4().hex.upper()}",
        name="",
        plan_id=plan.id,
        created_by_account_id=owner.id,
    )
    _apply(benefit, payload, db)
    db.add(benefit)
    db.commit()
    return _out(db, benefit)


@router.put("/{benefit_id}")
def update_benefit(
    benefit_id: int,
    payload: BenefitIn,
    _: PlatformOwner,
    db: DbSession,
) -> dict:
    benefit = db.get(Benefit, benefit_id)
    if benefit is None or benefit.organization_id is not None or benefit.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente.")
    _apply(benefit, payload, db)
    db.commit()
    return _out(db, benefit)


@router.delete("/{benefit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benefit(
    benefit_id: int,
    _: PlatformOwner,
    db: DbSession,
) -> None:
    """Baja lógica: conserva referencias históricas pero impide nuevos otorgamientos."""
    benefit = db.get(Benefit, benefit_id)
    if benefit is None or benefit.organization_id is not None or benefit.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente.")

    blockers = _delete_blockers(db, benefit)
    if any(blockers.values()):
        parts = []
        if blockers["activeBeneficiaries"]:
            parts.append(f'{blockers["activeBeneficiaries"]} beneficiario(s) vigente(s)')
        if blockers["activeCampaigns"]:
            parts.append(f'{blockers["activeCampaigns"]} campaña(s) activa(s)/pausada(s)')
        if blockers["activeInvitations"]:
            parts.append(f'{blockers["activeInvitations"]} invitación(es) vigente(s)')
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede dar de baja mientras el beneficio tenga " + ", ".join(parts) + ".",
        )

    benefit.active = False
    benefit.deleted_at = utcnow()
    db.commit()
