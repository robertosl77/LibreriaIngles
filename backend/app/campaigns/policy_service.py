"""Motor genérico de políticas previas a la resolución de conflictos de Campaigns.

No decide prioridad ni convivencia. Recibe una campaña candidata y una cuenta y
responde si la candidatura puede continuar. SUPPRESSION es la primera familia
habilitada; EXCLUSION reutilizará el mismo contrato cuando su semántica quede definida.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.campaigns.models import (
    Campaign,
    CampaignGrant,
    CampaignPolicy,
    CampaignPolicyBlock,
    CampaignPolicyEffect,
)
from app.campaigns.policy_capabilities import validate_policy_rule


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CampaignPolicyMatch:
    policy_id: int
    policy_name: str
    policy_kind: str
    reason: str
    rule_results: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class CampaignPolicyDecision:
    allowed: bool
    matches: list[CampaignPolicyMatch] = field(default_factory=list)


def _compare_number(actual: int, operator: str, expected: int) -> bool:
    if operator == "EQ":
        return actual == expected
    if operator == "GTE":
        return actual >= expected
    if operator == "LTE":
        return actual <= expected
    return False


def _policy_scope_matches(policy: CampaignPolicy, campaign: Campaign) -> bool:
    return policy.organization_id == campaign.organization_id


def _policy_applies_to_campaign(policy: CampaignPolicy, campaign: Campaign) -> bool:
    if not _policy_scope_matches(policy, campaign):
        return False
    applies_to = policy.applies_to or {"mode": "ALL", "campaignIds": []}
    mode = str(applies_to.get("mode") or "ALL").upper()
    if mode == "ALL":
        return True
    if mode == "CAMPAIGNS":
        ids: set[int] = set()
        for raw in applies_to.get("campaignIds") or []:
            try:
                ids.add(int(raw))
            except (TypeError, ValueError):
                continue
        return campaign.id in ids
    return False


def _grant_count(
    db: Session,
    *,
    account_id: int,
    campaign: Campaign,
    since: datetime,
    same_benefit: bool,
) -> int:
    statement = (
        select(func.count(CampaignGrant.id))
        .join(Campaign, Campaign.id == CampaignGrant.campaign_id)
        .where(
            CampaignGrant.account_id == account_id,
            CampaignGrant.applied_at >= since,
        )
    )
    if campaign.organization_id is None:
        statement = statement.where(Campaign.organization_id.is_(None))
    else:
        statement = statement.where(Campaign.organization_id == campaign.organization_id)
    if same_benefit:
        statement = statement.where(Campaign.benefit_id == campaign.benefit_id)
    return int(db.scalar(statement) or 0)


def policy_rule_evaluation(
    db: Session,
    account: Account,
    campaign: Campaign,
    raw_rule: dict,
    *,
    now: datetime,
) -> dict:
    rule = validate_policy_rule(raw_rule)
    window_days = int(rule["windowDays"] or 0)
    since = now - timedelta(days=window_days)
    field = rule["field"]

    if field == "CAMPAIGN_GRANTS_COUNT":
        actual = _grant_count(
            db,
            account_id=account.id,
            campaign=campaign,
            since=since,
            same_benefit=False,
        )
        description = f"Recibió {actual} campaña(s) en los últimos {window_days} días."
    elif field == "SAME_BENEFIT_GRANTS_COUNT":
        actual = _grant_count(
            db,
            account_id=account.id,
            campaign=campaign,
            since=since,
            same_benefit=True,
        )
        description = (
            f"Recibió el mismo beneficio {actual} vez/veces en los últimos {window_days} días."
        )
    else:
        return {
            "field": field,
            "operator": rule["operator"],
            "expected": rule["value"],
            "actual": None,
            "windowDays": window_days,
            "matched": False,
            "description": "Condición no evaluable.",
        }

    return {
        "field": field,
        "operator": rule["operator"],
        "expected": rule["value"],
        "actual": actual,
        "windowDays": window_days,
        "matched": _compare_number(actual, rule["operator"], int(rule["value"])),
        "description": description,
    }


def _policy_match(
    db: Session,
    policy: CampaignPolicy,
    account: Account,
    campaign: Campaign,
    *,
    now: datetime,
) -> CampaignPolicyMatch | None:
    if policy.effect != CampaignPolicyEffect.BLOCK:
        return None
    if not _policy_applies_to_campaign(policy, campaign):
        return None

    conditions = policy.conditions or {"mode": "ALL", "rules": []}
    if str(conditions.get("mode") or "ALL").upper() != "ALL":
        return None
    raw_rules = conditions.get("rules") or []
    if not raw_rules:
        return None

    evaluations = [
        policy_rule_evaluation(db, account, campaign, rule, now=now) for rule in raw_rules
    ]
    if not all(item["matched"] for item in evaluations):
        return None

    reason = " ".join(item["description"] for item in evaluations)
    return CampaignPolicyMatch(
        policy_id=policy.id,
        policy_name=policy.name,
        policy_kind=policy.kind.value,
        reason=reason[:500],
        rule_results=evaluations,
    )


def evaluate_campaign_policies(
    db: Session,
    campaign: Campaign,
    account: Account,
    *,
    now: datetime | None = None,
    record_blocks: bool = True,
) -> CampaignPolicyDecision:
    """Evalúa políticas antes de prioridad/convivencia.

    OR entre políticas: una sola política BLOCK que haga match alcanza para bloquear.
    AND dentro de cada política: todas sus condiciones deben cumplirse.
    """
    now = now or utcnow()
    scope_filter = (
        CampaignPolicy.organization_id.is_(None)
        if campaign.organization_id is None
        else CampaignPolicy.organization_id == campaign.organization_id
    )
    policies = db.scalars(
        select(CampaignPolicy)
        .where(
            scope_filter,
            CampaignPolicy.enabled.is_(True),
            CampaignPolicy.deleted_at.is_(None),
        )
        .order_by(CampaignPolicy.id.asc())
    ).all()

    matches: list[CampaignPolicyMatch] = []
    for policy in policies:
        match = _policy_match(db, policy, account, campaign, now=now)
        if match is None:
            continue
        matches.append(match)
        if record_blocks:
            db.add(
                CampaignPolicyBlock(
                    policy_id=policy.id,
                    campaign_id=campaign.id,
                    account_id=account.id,
                    policy_kind=policy.kind.value,
                    policy_name=policy.name,
                    reason=match.reason,
                    rule_snapshot={"results": match.rule_results},
                )
            )

    if matches and record_blocks:
        db.flush()
    return CampaignPolicyDecision(allowed=not matches, matches=matches)
