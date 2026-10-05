"""Administración PLATFORM_OWNER de políticas globales de Campaigns.

T-141: un único Campaign Policy Engine. SUPPRESSION es la primera familia
habilitada; EXCLUSION queda reservada hasta cerrar su semántica.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.accounts.models import Account
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
