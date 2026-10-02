"""PLATFORM_OWNER: definiciones reutilizables de beneficios (T-004)."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.benefits.models import Benefit
from app.benefits.service import benefit_duration, seed_benefits
from app.campaigns.models import Campaign
from app.core.deps import DbSession
from app.invitations.models import Invitation
from app.platform.api import PlatformOwner
from app.subscriptions.models import Plan, ServiceLinkType

router = APIRouter(prefix="/platform/benefits", tags=["platform"])


class BenefitIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    serviceId: int
    durationDays: int | None = Field(default=None, ge=1, le=3650)
    active: bool = True


def _plan(db: DbSession, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Servicio inexistente.")
    if plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "Los beneficios corporativos llegan con la etapa de empresas.")
    return plan


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
    return {
        "id": benefit.id,
        "code": benefit.code,
        "name": benefit.name,
        "serviceId": benefit.plan_id,
        "serviceName": plan.name if plan else "Servicio eliminado",
        "durationDays": benefit.duration_days,
        "conflictPolicy": benefit.conflict_policy.value,
        "active": benefit.active,
        "usedByCampaigns": int(campaigns),
        "usedByInvitations": int(invitations),
    }


def _apply(benefit: Benefit, payload: BenefitIn, db: DbSession) -> None:
    _plan(db, payload.serviceId)
    benefit.name = payload.name.strip()
    benefit.plan_id = payload.serviceId
    benefit.duration_days = payload.durationDays
    benefit.active = payload.active


@router.get("")
def list_benefits(_: PlatformOwner, db: DbSession) -> list[dict]:
    seed_benefits(db)
    db.commit()
    rows = db.scalars(
        select(Benefit)
        .where(Benefit.organization_id.is_(None))
        .order_by(Benefit.id.asc())
    ).all()
    return [_out(db, row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_benefit(payload: BenefitIn, owner: PlatformOwner, db: DbSession) -> dict:
    benefit = Benefit(
        code=f"BENEFIT_{uuid4().hex.upper()}",
        name="",
        plan_id=payload.serviceId,
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
    if benefit is None or benefit.organization_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente.")
    _apply(benefit, payload, db)
    db.commit()
    return _out(db, benefit)
