"""Administración PLATFORM_OWNER de políticas globales de Campaigns.

T-141: un único Campaign Policy Engine. SUPPRESSION es la primera familia
habilitada; EXCLUSION queda reservada hasta cerrar su semántica.
"""

from datetime import datetime, timezone
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.accounts.models import Account
from app.ai.service import NoAIAvailable, run_platform_json_task
from app.ai.usage import AIUsageContext
from app.campaigns.models import (
    Campaign,
    CampaignPolicy,
    CampaignPolicyBlock,
    CampaignPolicyEffect,
    CampaignPolicyKind,
)
from app.campaigns.policy_capabilities import (
    CampaignPolicyCapabilityError,
    available_policy_kind_values,
    policy_capabilities_payload,
    validate_policy_rule,
)
from app.core.deps import DbSession
from app.platform.api import PlatformOwner

router = APIRouter(prefix="/platform/campaigns/policies", tags=["platform", "campaigns"])


class CampaignPolicyRuleIn(BaseModel):
    field: str = Field(min_length=2, max_length=80)
    operator: str = Field(default="GTE", min_length=2, max_length=12)
    value: int = Field(ge=0, le=10_000_000)
    windowDays: int = Field(ge=1, le=3650)


class CampaignPolicyAssistIn(BaseModel):
    description: str = Field(min_length=8, max_length=2000)


CAMPAIGN_POLICY_ASSIST_SYSTEM = """Sos un asistente de configuración de políticas globales de Campaigns.
Tu trabajo es transformar la intención del Administrador de Plataforma en un borrador REVISABLE.
Nunca persistas ni habilites nada. No inventes capacidades, campañas, categorías ni estados.

Actualmente solo existe el tipo SUPPRESSION y el efecto técnico es BLOCK.
EXCLUSION sigue en análisis: si la intención depende de una exclusión, marcala UNSUPPORTED.
Solo podés usar las condiciones y operadores presentes en el catálogo recibido.
Si algo no puede representarse exactamente, declaralo UNSUPPORTED; no lo aproximes.

Devolvé SOLO JSON:
{
  "draft": {
    "name": "nombre claro",
    "description": "explicación breve o null",
    "kind": "SUPPRESSION",
    "enabled": true,
    "appliesTo": {
      "mode": "ALL" | "CAMPAIGNS",
      "campaignIds": [IDs válidos del catálogo]
    },
    "rules": [
      {
        "field": "capacidad exacta",
        "operator": "operador exacto",
        "value": número,
        "windowDays": número
      }
    ]
  },
  "requirements": [
    {
      "text": "requisito material pedido",
      "kind": "TYPE" | "SCOPE" | "RULE",
      "status": "REPRESENTED" | "UNSUPPORTED",
      "capability": "clave exacta o null",
      "reason": "motivo o null"
    }
  ],
  "warnings": ["advertencias informativas"],
  "summary": "resumen breve"
}

requirements debe enumerar todos los requisitos materiales de la intención. Si un requisito no
puede expresarse con el catálogo actual, debe quedar UNSUPPORTED. Una respuesta con requisitos
UNSUPPORTED no será ejecutable aunque tenga un draft parcial.
"""


class CampaignPolicyAppliesToIn(BaseModel):
    mode: str = Field(default="ALL", min_length=2, max_length=24)
    campaignIds: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_mode(self):
        self.mode = self.mode.upper()
        if self.mode not in {"ALL", "CAMPAIGNS"}:
            raise ValueError("El alcance debe ser ALL o CAMPAIGNS.")
        if self.mode == "CAMPAIGNS" and not self.campaignIds:
            raise ValueError("Elegí al menos una campaña para este alcance.")
        if self.mode == "ALL":
            self.campaignIds = []
        return self


class CampaignPolicyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    kind: CampaignPolicyKind = CampaignPolicyKind.SUPPRESSION
    enabled: bool = True
    appliesTo: CampaignPolicyAppliesToIn = Field(default_factory=CampaignPolicyAppliesToIn)
    rules: list[CampaignPolicyRuleIn] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind.value not in available_policy_kind_values():
            raise ValueError(
                "Ese tipo de política todavía no está habilitado. Exclusión sigue en análisis."
            )
        return self


def _policy(db: DbSession, policy_id: int) -> CampaignPolicy:
    policy = db.get(CampaignPolicy, policy_id)
    if (
        policy is None
        or policy.organization_id is not None
        or policy.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Política inexistente.")
    return policy


def _platform_campaign(db: DbSession, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if (
        campaign is None
        or campaign.organization_id is not None
        or campaign.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaña inexistente.")
    return campaign


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _normalize_policy_assist(
    raw: dict[str, Any],
    *,
    valid_campaign_ids: set[int],
) -> dict[str, Any]:
    draft_raw = raw.get("draft") if isinstance(raw.get("draft"), dict) else {}
    blocking: list[str] = []
    warnings = [
        str(item).strip()
        for item in (raw.get("warnings") or [])
        if str(item).strip()
    ]

    name = str(draft_raw.get("name") or "").strip()
    if len(name) < 2:
        blocking.append("La IA no propuso un nombre válido para la política.")
        name = "Política de supresión"

    description_raw = draft_raw.get("description")
    description = str(description_raw).strip()[:500] if description_raw else None

    kind = str(draft_raw.get("kind") or "SUPPRESSION").strip().upper()
    if kind not in available_policy_kind_values():
        blocking.append(
            f"El tipo {kind or 'vacío'} no está disponible. Hoy solo puede configurarse SUPPRESSION."
        )
        kind = "SUPPRESSION"

    enabled = bool(draft_raw.get("enabled", True))

    applies_raw = (
        draft_raw.get("appliesTo") if isinstance(draft_raw.get("appliesTo"), dict) else {}
    )
    applies_mode = str(applies_raw.get("mode") or "ALL").strip().upper()
    if applies_mode not in {"ALL", "CAMPAIGNS"}:
        blocking.append(f"Alcance no soportado: {applies_mode or 'vacío'}.")
        applies_mode = "ALL"

    campaign_ids: list[int] = []
    invalid_campaign_ids: list[str] = []
    if applies_mode == "CAMPAIGNS":
        for raw_id in applies_raw.get("campaignIds") or []:
            try:
                campaign_id = int(raw_id)
            except (TypeError, ValueError):
                invalid_campaign_ids.append(str(raw_id))
                continue
            if campaign_id not in valid_campaign_ids:
                invalid_campaign_ids.append(str(campaign_id))
                continue
            if campaign_id not in campaign_ids:
                campaign_ids.append(campaign_id)
        if invalid_campaign_ids:
            blocking.append(
                "La IA referenció campañas inexistentes o fuera del scope: "
                + ", ".join(invalid_campaign_ids)
                + "."
            )
        if not campaign_ids:
            blocking.append(
                "La política pide campañas seleccionadas pero no quedó ninguna campaña válida."
            )
    else:
        campaign_ids = []

    normalized_rules: list[dict[str, Any]] = []
    raw_rules = draft_raw.get("rules") if isinstance(draft_raw.get("rules"), list) else []
    if len(raw_rules) > 10:
        blocking.append("El borrador supera el máximo de 10 condiciones.")
    for raw_rule in raw_rules[:10]:
        if not isinstance(raw_rule, dict):
            blocking.append("La IA devolvió una condición inválida.")
            continue
        try:
            normalized_rules.append(validate_policy_rule(raw_rule))
        except CampaignPolicyCapabilityError as exc:
            blocking.append(str(exc))
    if not normalized_rules:
        blocking.append("La política necesita al menos una condición de supresión válida.")

    requirements: list[dict[str, Any]] = []
    raw_requirements = raw.get("requirements")
    if not isinstance(raw_requirements, list):
        blocking.append("La IA no devolvió la cobertura de requisitos de la intención.")
        raw_requirements = []
    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        status_value = str(item.get("status") or "UNSUPPORTED").strip().upper()
        status_value = "REPRESENTED" if status_value == "REPRESENTED" else "UNSUPPORTED"
        capability = item.get("capability")
        reason = item.get("reason")
        requirement = {
            "text": text,
            "kind": str(item.get("kind") or "RULE").strip().upper(),
            "status": status_value,
            "capability": str(capability).strip() if capability else None,
            "reason": str(reason).strip() if reason else None,
            "verified": status_value == "REPRESENTED",
        }
        requirements.append(requirement)
        if status_value != "REPRESENTED":
            blocking.append(
                requirement["reason"]
                or f"No se puede representar exactamente: {requirement['text']}."
            )

    blocking = _unique_texts(blocking)
    return {
        "draft": {
            "name": name[:120],
            "description": description,
            "kind": kind,
            "enabled": enabled,
            "appliesTo": {
                "mode": applies_mode,
                "campaignIds": sorted(campaign_ids),
            },
            "rules": normalized_rules,
        },
        "requirements": requirements,
        "warnings": _unique_texts(warnings),
        "blockingIssues": blocking,
        "executable": len(blocking) == 0,
        "summary": str(raw.get("summary") or "").strip()
        or "Borrador de política generado por IA.",
    }


def _validated_rules(payload: CampaignPolicyIn) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for rule in payload.rules:
        try:
            rules.append(validate_policy_rule(rule.model_dump()))
        except CampaignPolicyCapabilityError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return rules


def _validated_applies_to(db: DbSession, payload: CampaignPolicyIn) -> dict[str, Any]:
    mode = payload.appliesTo.mode
    if mode == "ALL":
        return {"mode": "ALL", "campaignIds": []}

    campaign_ids = sorted(set(payload.appliesTo.campaignIds))
    for campaign_id in campaign_ids:
        _platform_campaign(db, campaign_id)
    return {"mode": "CAMPAIGNS", "campaignIds": campaign_ids}


def _apply_policy(policy: CampaignPolicy, payload: CampaignPolicyIn, db: DbSession) -> None:
    policy.name = payload.name.strip()
    policy.description = payload.description.strip() if payload.description else None
    policy.kind = payload.kind
    policy.effect = CampaignPolicyEffect.BLOCK
    policy.enabled = payload.enabled
    policy.applies_to = _validated_applies_to(db, payload)
    policy.conditions = {"mode": "ALL", "rules": _validated_rules(payload)}


def _out(db: DbSession, policy: CampaignPolicy) -> dict[str, Any]:
    block_count = int(
        db.scalar(
            select(func.count(CampaignPolicyBlock.id)).where(
                CampaignPolicyBlock.policy_id == policy.id
            )
        )
        or 0
    )
    last_block = db.scalar(
        select(CampaignPolicyBlock)
        .where(CampaignPolicyBlock.policy_id == policy.id)
        .order_by(CampaignPolicyBlock.created_at.desc(), CampaignPolicyBlock.id.desc())
        .limit(1)
    )
    conditions = policy.conditions or {"mode": "ALL", "rules": []}
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "kind": policy.kind.value,
        "effect": policy.effect.value,
        "enabled": policy.enabled,
        "appliesTo": policy.applies_to or {"mode": "ALL", "campaignIds": []},
        "rules": conditions.get("rules", []),
        "blockCount": block_count,
        "lastBlockedAt": last_block.created_at if last_block else None,
        "createdAt": policy.created_at,
        "updatedAt": policy.updated_at,
    }


@router.get("")
def list_policies(_: PlatformOwner, db: DbSession) -> list[dict[str, Any]]:
    policies = db.scalars(
        select(CampaignPolicy)
        .where(
            CampaignPolicy.organization_id.is_(None),
            CampaignPolicy.deleted_at.is_(None),
        )
        .order_by(CampaignPolicy.id.asc())
    ).all()
    return [_out(db, policy) for policy in policies]


@router.get("/capabilities")
def policy_capabilities(_: PlatformOwner) -> dict[str, Any]:
    return policy_capabilities_payload()


@router.get("/blocks")
def policy_blocks(
    _: PlatformOwner,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CampaignPolicyBlock, Campaign, Account)
        .join(Campaign, Campaign.id == CampaignPolicyBlock.campaign_id)
        .join(Account, Account.id == CampaignPolicyBlock.account_id)
        .where(Campaign.organization_id.is_(None))
        .order_by(CampaignPolicyBlock.created_at.desc(), CampaignPolicyBlock.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": block.id,
            "policyId": block.policy_id,
            "policy": block.policy_name,
            "kind": block.policy_kind,
            "campaignId": campaign.id,
            "campaign": campaign.name,
            "accountId": account.id,
            "account": account.email,
            "reason": block.reason,
            "createdAt": block.created_at,
        }
        for block, campaign, account in rows
    ]


@router.post("/assist")
def assist_policy(
    payload: CampaignPolicyAssistIn,
    owner: PlatformOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Interpreta lenguaje natural y devuelve un borrador; nunca persiste la política."""
    campaigns = db.scalars(
        select(Campaign)
        .where(
            Campaign.organization_id.is_(None),
            Campaign.deleted_at.is_(None),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()
    campaign_options = [
        {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status.value,
            "priority": campaign.priority,
        }
        for campaign in campaigns
    ]
    capabilities = policy_capabilities_payload()
    description = payload.description.strip()
    task = {
        "kind": "campaign_policy_assist",
        "description": description,
        "campaigns": campaign_options,
        "capabilities": capabilities,
    }
    user_prompt = (
        "Intención del Administrador de Plataforma:\n"
        + description
        + "\n\nCatálogo de políticas disponible:\n"
        + json.dumps(capabilities, ensure_ascii=False)
        + "\n\nCampañas disponibles (solo podés usar estos IDs):\n"
        + json.dumps(campaign_options, ensure_ascii=False)
    )
    try:
        result = run_platform_json_task(
            db,
            owner,
            system=CAMPAIGN_POLICY_ASSIST_SYSTEM,
            user=user_prompt,
            task=task,
            usage_context=AIUsageContext(
                subject_type="CAMPAIGN_POLICY_ASSIST",
                subject_label="Asistente de políticas de Campaigns",
                subject_route="/app/plataforma/campanas",
                diagnostic={
                    "descriptionChars": len(description),
                    "campaignCount": len(campaign_options),
                    "policyRuleCapabilityCount": len(capabilities.get("rules") or []),
                },
            ),
        )
    except NoAIAvailable as exc:
        detail = "No hay una conexión de IA de plataforma disponible para interpretar la política."
        if exc.errors:
            detail += " " + "; ".join(exc.errors)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)

    if not isinstance(result.data, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "La IA devolvió un borrador inválido.")
    return _normalize_policy_assist(
        result.data,
        valid_campaign_ids={campaign.id for campaign in campaigns},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_policy(payload: CampaignPolicyIn, owner: PlatformOwner, db: DbSession) -> dict[str, Any]:
    policy = CampaignPolicy(
        organization_id=None,
        created_by_account_id=owner.id,
        name="",
        kind=payload.kind,
        effect=CampaignPolicyEffect.BLOCK,
    )
    _apply_policy(policy, payload, db)
    db.add(policy)
    db.commit()
    return _out(db, policy)


@router.put("/{policy_id}")
def update_policy(
    policy_id: int, payload: CampaignPolicyIn, _: PlatformOwner, db: DbSession
) -> dict[str, Any]:
    policy = _policy(db, policy_id)
    _apply_policy(policy, payload, db)
    db.commit()
    return _out(db, policy)


@router.post("/{policy_id}/enable")
def enable_policy(policy_id: int, _: PlatformOwner, db: DbSession) -> dict[str, Any]:
    policy = _policy(db, policy_id)
    policy.enabled = True
    db.commit()
    return _out(db, policy)


@router.post("/{policy_id}/disable")
def disable_policy(policy_id: int, _: PlatformOwner, db: DbSession) -> dict[str, Any]:
    policy = _policy(db, policy_id)
    policy.enabled = False
    db.commit()
    return _out(db, policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: int, _: PlatformOwner, db: DbSession) -> None:
    policy = _policy(db, policy_id)
    policy.enabled = False
    policy.deleted_at = datetime.now(timezone.utc)
    db.commit()
