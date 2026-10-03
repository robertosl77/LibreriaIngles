"""Consulta y canje de invitaciones por link."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.benefits.models import Benefit
from app.benefits.service import benefit_duration
from app.core.deps import CurrentAccount, DbSession
from app.invitations.models import Invitation
from app.invitations.service import (
    InvitationClaimError,
    mask_email,
    redeem_invitation,
    redemption_count,
    refresh_status,
    token_hash,
)
from app.subscriptions.models import Plan

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _by_token(db: DbSession, token: str) -> Invitation:
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == token_hash(token))
    )
    if invitation is None:
        raise HTTPException(404, "La invitación no existe o el link ya fue reemplazado.")
    return invitation


@router.get("/{token}")
def preview_invitation(token: str, db: DbSession) -> dict:
    invitation = _by_token(db, token)
    refresh_status(db, invitation)
    benefit = db.get(Benefit, invitation.benefit_id) if invitation.benefit_id else None
    plan = db.get(Plan, benefit.plan_id) if benefit else None
    used = redemption_count(db, invitation.id)
    body = {
        "name": invitation.name,
        "recipientMode": invitation.recipient_mode.value,
        "recipientEmailHint": mask_email(invitation.email),
        "benefitName": benefit.name if benefit else "Beneficio no disponible",
        "serviceName": plan.name if plan else "Servicio no disponible",
        "durationDays": benefit_duration(benefit, plan) if benefit and plan else None,
        "status": invitation.status.value,
        "remaining": max(0, invitation.max_redemptions - used),
        "expiresAt": invitation.expires_at,
    }
    db.commit()
    return body


@router.post("/{token}/redeem")
def redeem(token: str, account: CurrentAccount, db: DbSession) -> dict:
    try:
        result = redeem_invitation(db, token, account)
        db.commit()
    except InvitationClaimError as exc:
        db.rollback()
        raise HTTPException(409, exc.message) from exc
    return {
        "invitation": result.invitation.name,
        "benefit": result.redemption.benefit_summary,
        "alreadyRedeemed": result.already_redeemed,
        "redeemedAt": result.redemption.redeemed_at,
    }
