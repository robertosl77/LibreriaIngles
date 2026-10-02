"""Portal del PLATFORM_OWNER: constructor y control de campañas (T-004, etapa 2)."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.campaigns.models import (
    Campaign,
    CampaignGrant,
    CampaignNotification,
    CampaignStatus,
    CampaignTrigger,
)
from app.campaigns.service import seed_campaigns
from app.core.deps import DbSession
from app.platform.api import PlatformOwner
from app.subscriptions.models import AISource, Plan, ServiceLinkType

router = APIRouter(prefix="/platform/campaigns", tags=["platform"])

SUPPORTED_RULES: dict[str, set[str]] = {
    "ACCOUNT_TYPE": {"EQ"},
    "HAS_GRANTED_SERVICE": {"EQ"},
    "SERVICE_SOURCE": {"EQ"},
    "EMAIL_DOMAIN": {"EQ"},
    "DAYS_SINCE_CREATED": {"EQ", "GTE", "LTE"},
    "CREATED_AT": {"EQ", "GTE", "LTE"},
}


class CampaignRuleIn(BaseModel):
    field: str = Field(min_length=2, max_length=60)
    operator: str = Field(default="EQ", min_length=2, max_length=12)
    value: Any


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    serviceId: int
    trigger: CampaignTrigger = CampaignTrigger.FIRST_LOGIN
    rules: list[CampaignRuleIn] = Field(default_factory=list, max_length=20)
    grantDays: int | None = Field(default=None, ge=1, le=3650)
    priority: int = Field(default=100, ge=1, le=10000)
    stackable: bool = False
    maxRecipients: int | None = Field(default=None, ge=1, le=10_000_000)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    notification: CampaignNotification = CampaignNotification.IN_APP
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_window(self):
        if self.startsAt and self.endsAt and self.endsAt <= self.startsAt:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio.")
        return self


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _validate_rule(rule: CampaignRuleIn) -> dict:
    field = rule.field.strip().upper()
    operator = rule.operator.strip().upper()
    if field not in SUPPORTED_RULES or operator not in SUPPORTED_RULES[field]:
        raise HTTPException(422, f"Condición no soportada: {field} {operator}.")
    value = rule.value
    if field == "ACCOUNT_TYPE":
        value = str(value).upper()
        if value not in {"PERSONAL", "CORPORATE"}:
            raise HTTPException(422, "Tipo de cuenta inválido.")
    elif field == "HAS_GRANTED_SERVICE":
        if not isinstance(value, bool):
            raise HTTPException(422, "HAS_GRANTED_SERVICE requiere true/false.")
    elif field == "SERVICE_SOURCE":
        value = str(value).upper()
        if value not in {source.value for source in AISource}:
            raise HTTPException(422, "Fuente de IA inválida.")
    elif field == "EMAIL_DOMAIN":
        value = str(value).strip().lower().lstrip("@")
        if not value or "." not in value:
            raise HTTPException(422, "Dominio de email inválido.")
    elif field == "DAYS_SINCE_CREATED":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise HTTPException(422, "Días desde registro debe ser un entero.")
        if value < 0:
            raise HTTPException(422, "Días desde registro no puede ser negativo.")
    elif field == "CREATED_AT":
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "Fecha de registro inválida.")
        value = _as_utc(parsed).isoformat()
    return {"field": field, "operator": operator, "value": value}


def _plan(db: DbSession, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Servicio inexistente.")
    if plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "Las campañas corporativas llegan con la etapa de empresas.")
    return plan


def _apply(campaign: Campaign, payload: CampaignIn, db: DbSession) -> None:
    _plan(db, payload.serviceId)
    campaign.name = payload.name.strip()
    campaign.plan_id = payload.serviceId
    campaign.trigger = payload.trigger
    campaign.eligibility = {
        "mode": "ALL",
        "rules": [_validate_rule(rule) for rule in payload.rules],
    }
    campaign.grant_days = payload.grantDays
    campaign.priority = payload.priority
    campaign.stackable = payload.stackable
    campaign.max_recipients = payload.maxRecipients
    campaign.starts_at = _as_utc(payload.startsAt)
    campaign.ends_at = _as_utc(payload.endsAt)
    campaign.notification = payload.notification
    campaign.message = (payload.message or "").strip() or None


def _windows_overlap(a: Campaign, b: Campaign) -> bool:
    start_a, end_a = _as_utc(a.starts_at), _as_utc(a.ends_at)
    start_b, end_b = _as_utc(b.starts_at), _as_utc(b.ends_at)
    if end_a is not None and start_b is not None and end_a <= start_b:
        return False
    if end_b is not None and start_a is not None and end_b <= start_a:
        return False
    return True


def _overlap_warnings(db: DbSession, campaign: Campaign) -> list[dict]:
    scope_filter = (
        Campaign.organization_id.is_(None)
        if campaign.organization_id is None
        else Campaign.organization_id == campaign.organization_id
    )
    peers = db.scalars(
        select(Campaign).where(
            Campaign.id != campaign.id,
            scope_filter,
            Campaign.trigger == campaign.trigger,
            Campaign.status != CampaignStatus.ENDED,
        )
    ).all()
    return [
        {
            "id": peer.id,
            "name": peer.name,
            "priority": peer.priority,
            "stackable": peer.stackable,
        }
        for peer in peers
        if _windows_overlap(campaign, peer) and (not campaign.stackable or not peer.stackable)
    ]


def _out(db: DbSession, campaign: Campaign) -> dict:
    plan = db.get(Plan, campaign.plan_id)
    recipients = db.scalar(
        select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == campaign.id)
    ) or 0
    pending_email = db.scalar(
        select(func.count(CampaignGrant.id)).where(
            CampaignGrant.campaign_id == campaign.id,
            CampaignGrant.email_status == "PENDING",
        )
    ) or 0
    eligibility = campaign.eligibility or {"mode": "ALL", "rules": []}
    return {
        "id": campaign.id,
        "code": campaign.code,
        "name": campaign.name,
        "serviceId": campaign.plan_id,
        "serviceName": plan.name if plan else "Servicio eliminado",
        "status": campaign.status.value,
        "trigger": campaign.trigger.value,
        "rules": eligibility.get("rules", []),
        "grantDays": campaign.grant_days,
        "priority": campaign.priority,
        "stackable": campaign.stackable,
        "maxRecipients": campaign.max_recipients,
        "recipients": int(recipients),
        "startsAt": campaign.starts_at,
        "endsAt": campaign.ends_at,
        "notification": campaign.notification.value,
        "message": campaign.message,
        "pendingEmails": int(pending_email),
        "overlapWarnings": _overlap_warnings(db, campaign),
    }


def _campaign(db: DbSession, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.organization_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaña inexistente.")
    return campaign


@router.get("")
def list_campaigns(_: PlatformOwner, db: DbSession) -> list[dict]:
    seed_campaigns(db)
    db.commit()
    campaigns = db.scalars(
        select(Campaign)
        .where(Campaign.organization_id.is_(None))
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()
    return [_out(db, campaign) for campaign in campaigns]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignIn, owner: PlatformOwner, db: DbSession) -> dict:
    campaign = Campaign(
        code=f"CAMPAIGN_{uuid4().hex.upper()}",
        name="",
        plan_id=payload.serviceId,
        created_by_account_id=owner.id,
    )
    _apply(campaign, payload, db)
    db.add(campaign)
    db.commit()
    return _out(db, campaign)


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: int, payload: CampaignIn, _: PlatformOwner, db: DbSession
) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "Una campaña terminada no se puede editar.")
    _apply(campaign, payload, db)
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/activate")
def activate_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    plan = _plan(db, campaign.plan_id)
    if not plan.active:
        raise HTTPException(409, "El servicio de la campaña está inactivo.")
    if campaign.trigger == CampaignTrigger.SCHEDULED:
        raise HTTPException(409, "Las campañas programadas requieren el scheduler de T-059.")
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "La campaña ya terminó.")
    campaign.status = CampaignStatus.PAUSED
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/finish")
def finish_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    campaign.status = CampaignStatus.ENDED
    db.commit()
    return _out(db, campaign)
