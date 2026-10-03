"""Portal del PLATFORM_OWNER: constructor y control de campañas (T-004, etapa 2)."""

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.ai.service import NoAIAvailable, run_platform_json_task
from app.benefits.models import Benefit
from app.benefits.service import benefit_duration, seed_benefits
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


class CampaignAssistIn(BaseModel):
    description: str = Field(min_length=8, max_length=2000)


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    benefitId: int
    trigger: CampaignTrigger = CampaignTrigger.FIRST_LOGIN
    rules: list[CampaignRuleIn] = Field(default_factory=list, max_length=20)
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


CAMPAIGN_ASSIST_SYSTEM = """Sos un asistente que transforma una intención comercial en un borrador
de campaña para Librería Inglés. No inventes capacidades que el motor no tenga.

Devolvé SOLO JSON con esta forma:
{
  "draft": {
    "name": "nombre claro",
    "benefitId": 123 o null,
    "trigger": "FIRST_LOGIN" o "LOGIN",
    "rules": [{"field":"...", "operator":"...", "value":...}],
    "priority": 100,
    "stackable": false,
    "maxRecipients": null,
    "startsAt": null o ISO-8601,
    "endsAt": null o ISO-8601,
    "notification": "NONE" | "IN_APP" | "EMAIL" | "IN_APP_EMAIL",
    "message": null o texto
  },
  "warnings": ["limitación o dato que debe revisar el usuario"],
  "summary": "resumen breve de lo interpretado"
}

Reglas soportadas:
- ACCOUNT_TYPE: EQ PERSONAL o CORPORATE
- HAS_GRANTED_SERVICE: EQ true/false
- SERVICE_SOURCE: EQ BYOK/PLATFORM/HYBRID
- EMAIL_DOMAIN: EQ dominio
- DAYS_SINCE_CREATED: EQ/GTE/LTE número
- CREATED_AT: EQ/GTE/LTE fecha ISO

El motor actual SOLO otorga un beneficio existente. No administra precios, porcentajes de
descuento, pagos ni renovaciones. Si el pedido requiere algo no soportado, avisalo en warnings
y no inventes campos. SCHEDULED todavía no está disponible: usá FIRST_LOGIN o LOGIN.
Elegí benefitId únicamente entre los beneficios provistos y solo si la intención lo deja claro;
si no, devolvé null para que el usuario lo seleccione. El resultado es siempre un BORRADOR:
nunca actives ni guardes una campaña."""


def _assist_datetime(value, warnings: list[str], label: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        warnings.append(f"La IA propuso una {label} inválida; se dejó vacía.")
        return None
    return _as_utc(parsed).isoformat()


def _normalize_assist(data: dict, benefit_ids: set[int]) -> dict:
    raw = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    warnings = [
        str(item)[:300]
        for item in (data.get("warnings") or [])
        if isinstance(item, (str, int, float))
    ][:8]

    benefit_id = raw.get("benefitId")
    try:
        benefit_id = int(benefit_id) if benefit_id is not None else None
    except (TypeError, ValueError):
        benefit_id = None
    if benefit_id is not None and benefit_id not in benefit_ids:
        warnings.append("La IA eligió un beneficio no disponible; seleccioná uno manualmente.")
        benefit_id = None

    trigger = str(raw.get("trigger") or "LOGIN").upper()
    if trigger not in {"FIRST_LOGIN", "LOGIN"}:
        warnings.append("El disparador propuesto no está disponible; se usó Cada login.")
        trigger = "LOGIN"

    rules: list[dict] = []
    for item in raw.get("rules") or []:
        if not isinstance(item, dict) or len(rules) >= 20:
            continue
        try:
            rules.append(_validate_rule(CampaignRuleIn.model_validate(item)))
        except (HTTPException, ValueError, TypeError):
            warnings.append("Se omitió una condición propuesta por IA porque no es compatible.")
    if not any(rule["field"] == "ACCOUNT_TYPE" for rule in rules):
        rules.insert(0, {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"})

    try:
        priority = max(1, min(10000, int(raw.get("priority") or 100)))
    except (TypeError, ValueError):
        priority = 100

    max_recipients = raw.get("maxRecipients")
    if max_recipients in (None, ""):
        max_recipients = None
    else:
        try:
            max_recipients = max(1, min(10_000_000, int(max_recipients)))
        except (TypeError, ValueError):
            max_recipients = None
            warnings.append("El máximo de beneficiarios propuesto no era válido; se dejó sin límite.")

    starts_at = _assist_datetime(raw.get("startsAt"), warnings, "fecha de inicio")
    ends_at = _assist_datetime(raw.get("endsAt"), warnings, "fecha de fin")
    if starts_at and ends_at and datetime.fromisoformat(ends_at) <= datetime.fromisoformat(starts_at):
        ends_at = None
        warnings.append("La fecha de fin no era posterior al inicio; se dejó vacía.")

    notification = str(raw.get("notification") or "IN_APP").upper()
    allowed_notifications = {item.value for item in CampaignNotification}
    if notification not in allowed_notifications:
        notification = "IN_APP"

    name = str(raw.get("name") or "Campaña sugerida por IA").strip()[:120]
    if len(name) < 2:
        name = "Campaña sugerida por IA"
    message = raw.get("message")
    message = str(message).strip()[:500] if message else None

    return {
        "draft": {
            "name": name,
            "benefitId": benefit_id,
            "trigger": trigger,
            "rules": rules,
            "priority": priority,
            "stackable": bool(raw.get("stackable")) if isinstance(raw.get("stackable"), bool) else False,
            "maxRecipients": max_recipients,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "notification": notification,
            "message": message,
        },
        "warnings": warnings,
        "summary": str(data.get("summary") or "Borrador generado por IA. Revisalo antes de guardar.")[:500],
    }


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


def _benefit(db: DbSession, benefit_id: int, *, require_active: bool = False) -> Benefit:
    benefit = db.get(Benefit, benefit_id)
    if benefit is None or benefit.organization_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente.")
    plan = db.get(Plan, benefit.plan_id)
    if plan is None or plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "Las campañas corporativas llegan con la etapa de empresas.")
    if require_active and (not benefit.active or not plan.active):
        raise HTTPException(409, "El beneficio o su servicio está inactivo.")
    return benefit


def _apply(campaign: Campaign, payload: CampaignIn, db: DbSession) -> None:
    _benefit(db, payload.benefitId)
    campaign.name = payload.name.strip()
    campaign.benefit_id = payload.benefitId
    campaign.trigger = payload.trigger
    campaign.eligibility = {
        "mode": "ALL",
        "rules": [_validate_rule(rule) for rule in payload.rules],
    }
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
            Campaign.deleted_at.is_(None),
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
    benefit = db.get(Benefit, campaign.benefit_id)
    plan = db.get(Plan, benefit.plan_id) if benefit else None
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
        "benefitId": campaign.benefit_id,
        "benefitName": benefit.name if benefit else "Beneficio eliminado",
        "serviceId": plan.id if plan else None,
        "serviceName": plan.name if plan else "Servicio eliminado",
        "grantDays": benefit_duration(benefit, plan) if benefit and plan else None,
        "status": campaign.status.value,
        "trigger": campaign.trigger.value,
        "rules": eligibility.get("rules", []),
        "priority": campaign.priority,
        "stackable": campaign.stackable,
        "maxRecipients": campaign.max_recipients,
        "recipients": int(recipients),
        "startsAt": campaign.starts_at,
        "endsAt": campaign.ends_at,
        "activatedAt": campaign.activated_at,
        "notification": campaign.notification.value,
        "message": campaign.message,
        "pendingEmails": int(pending_email),
        "overlapWarnings": _overlap_warnings(db, campaign),
    }


def _campaign(db: DbSession, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if (
        campaign is None
        or campaign.organization_id is not None
        or campaign.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaña inexistente.")
    return campaign


@router.get("")
def list_campaigns(_: PlatformOwner, db: DbSession) -> list[dict]:
    seed_benefits(db)
    seed_campaigns(db)
    db.commit()
    campaigns = db.scalars(
        select(Campaign)
        .where(
            Campaign.organization_id.is_(None),
            Campaign.deleted_at.is_(None),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()
    return [_out(db, campaign) for campaign in campaigns]


@router.post("/assist")
def assist_campaign(payload: CampaignAssistIn, owner: PlatformOwner, db: DbSession) -> dict:
    """Convierte lenguaje natural en un borrador; nunca persiste ni activa una campaña."""
    benefits = db.execute(
        select(Benefit, Plan)
        .join(Plan, Plan.id == Benefit.plan_id)
        .where(
            Benefit.organization_id.is_(None),
            Benefit.active.is_(True),
            Benefit.deleted_at.is_(None),
            Plan.active.is_(True),
            Plan.link_type == ServiceLinkType.PERSONAL,
        )
        .order_by(Benefit.id)
    ).all()
    benefit_options = [
        {
            "id": benefit.id,
            "name": benefit.name,
            "source": plan.ai_source.value,
            "durationDays": benefit_duration(benefit, plan),
        }
        for benefit, plan in benefits
    ]

    task = {
        "kind": "campaign_assist",
        "description": payload.description.strip(),
        "benefits": benefit_options,
    }
    user_prompt = (
        "Intención del usuario:\n"
        + payload.description.strip()
        + "\n\nBeneficios activos disponibles (solo podés usar estos IDs):\n"
        + json.dumps(benefit_options, ensure_ascii=False)
    )
    try:
        result = run_platform_json_task(
            db,
            owner,
            system=CAMPAIGN_ASSIST_SYSTEM,
            user=user_prompt,
            task=task,
        )
    except NoAIAvailable as exc:
        detail = "No hay una conexión de IA de plataforma disponible para generar el borrador."
        if exc.errors:
            detail += " " + "; ".join(exc.errors)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)

    if not isinstance(result.data, dict):
        raise HTTPException(502, "La IA devolvió un borrador inválido.")
    return _normalize_assist(result.data, {item["id"] for item in benefit_options})


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignIn, owner: PlatformOwner, db: DbSession) -> dict:
    campaign = Campaign(
        code=f"CAMPAIGN_{uuid4().hex.upper()}",
        name="",
        benefit_id=payload.benefitId,
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
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "Una campaña terminada no se puede reactivar.")
    _benefit(db, campaign.benefit_id, require_active=True)
    if campaign.trigger == CampaignTrigger.SCHEDULED:
        raise HTTPException(409, "Las campañas programadas requieren el scheduler de T-059.")
    if campaign.status != CampaignStatus.ACTIVE:
        campaign.activated_at = datetime.now(timezone.utc)
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


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> None:
    campaign = _campaign(db, campaign_id)
    if campaign.status != CampaignStatus.ENDED:
        raise HTTPException(409, "Solo se puede eliminar una campaña terminada.")

    recipients = db.scalar(
        select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == campaign.id)
    ) or 0
    if int(recipients) == 0:
        db.delete(campaign)
    else:
        campaign.deleted_at = datetime.now(timezone.utc)
    db.commit()
