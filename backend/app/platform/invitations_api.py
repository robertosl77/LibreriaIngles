"""PLATFORM_OWNER: gestión de pre-invitaciones e invitaciones por link."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select

from app.benefits.models import Benefit
from app.benefits.service import benefit_duration
from app.core.deps import DbSession
from app.invitations.models import (
    Invitation,
    InvitationRecipientMode,
    InvitationStatus,
)
from app.invitations.service import (
    invitation_token,
    new_token,
    redemption_count,
    refresh_status,
    set_token,
)
from app.platform.api import PlatformOwner
from app.subscriptions.models import Plan, ServiceLinkType

router = APIRouter(prefix="/platform/invitations", tags=["platform"])


class InvitationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    benefitId: int
    recipientMode: InvitationRecipientMode = InvitationRecipientMode.NAMED
    email: EmailStr | None = None
    firstName: str | None = Field(default=None, max_length=100)
    lastName: str | None = Field(default=None, max_length=100)
    maxRedemptions: int = Field(default=1, ge=1, le=1_000_000)
    expiresAt: datetime | None = None

    @model_validator(mode="after")
    def validate_recipient(self):
        if self.recipientMode == InvitationRecipientMode.NAMED and self.email is None:
            raise ValueError("La invitación nominada requiere email.")
        return self


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _benefit(db: DbSession, benefit_id: int) -> tuple[Benefit, Plan]:
    benefit = db.get(Benefit, benefit_id)
    if (
        benefit is None
        or benefit.organization_id is not None
        or not benefit.active
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente o inactivo.")
    plan = db.get(Plan, benefit.plan_id)
    if plan is None or not plan.active or plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "La invitación del OWNER solo puede otorgar beneficios personales activos.")
    return benefit, plan


def _invitation(db: DbSession, invitation_id: int) -> Invitation:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitación inexistente.")
    return invitation


def _out(db: DbSession, invitation: Invitation) -> dict:
    refresh_status(db, invitation)
    benefit = db.get(Benefit, invitation.benefit_id) if invitation.benefit_id else None
    plan = db.get(Plan, benefit.plan_id) if benefit else None
    used = redemption_count(db, invitation.id)
    return {
        "id": invitation.id,
        "name": invitation.name,
        "benefitId": invitation.benefit_id,
        "benefitName": benefit.name if benefit else "Beneficio no disponible",
        "serviceName": plan.name if plan else "Servicio no disponible",
        "durationDays": benefit_duration(benefit, plan) if benefit and plan else None,
        "recipientMode": invitation.recipient_mode.value,
        "email": invitation.email,
        "firstName": invitation.first_name,
        "lastName": invitation.last_name,
        "status": invitation.status.value,
        "maxRedemptions": invitation.max_redemptions,
        "redemptions": used,
        "remaining": max(0, invitation.max_redemptions - used),
        "expiresAt": invitation.expires_at,
        "emailStatus": invitation.email_status,
        # Solo se expone al OWNER autenticado; en DB el secreto está cifrado y además se guarda hash.
        "token": invitation_token(invitation),
        "createdAt": invitation.created_at,
    }


@router.get("")
def list_invitations(_: PlatformOwner, db: DbSession) -> list[dict]:
    invitations = db.scalars(
        select(Invitation)
        .where(Invitation.organization_id.is_(None))
        .order_by(Invitation.created_at.desc(), Invitation.id.desc())
    ).all()
    rows = [_out(db, invitation) for invitation in invitations]
    db.commit()
    return rows


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invitation(payload: InvitationIn, owner: PlatformOwner, db: DbSession) -> dict:
    _benefit(db, payload.benefitId)
    expires = _as_utc(payload.expiresAt)
    if expires is not None and expires <= datetime.now(timezone.utc):
        raise HTTPException(422, "La fecha de vencimiento debe ser futura.")

    named = payload.recipientMode == InvitationRecipientMode.NAMED
    invitation = Invitation(
        organization_id=None,
        created_by_account_id=owner.id,
        benefit_id=payload.benefitId,
        name=payload.name.strip(),
        recipient_mode=payload.recipientMode,
        email=str(payload.email).lower() if named and payload.email else None,
        first_name=(payload.firstName or "").strip() or None if named else None,
        last_name=(payload.lastName or "").strip() or None if named else None,
        token_hash="",
        status=InvitationStatus.ACTIVE,
        max_redemptions=1 if named else payload.maxRedemptions,
        expires_at=expires,
        email_status="PENDING" if named else None,
    )
    token = new_token()
    set_token(invitation, token)
    db.add(invitation)
    db.commit()
    return _out(db, invitation)


@router.post("/{invitation_id}/regenerate-token")
def regenerate_token(
    invitation_id: int,
    _: PlatformOwner,
    db: DbSession,
) -> dict:
    invitation = _invitation(db, invitation_id)
    refresh_status(db, invitation)
    if invitation.status != InvitationStatus.ACTIVE:
        raise HTTPException(409, "Solo se puede regenerar el link de una invitación activa.")
    set_token(invitation, new_token())
    if invitation.recipient_mode == InvitationRecipientMode.NAMED:
        invitation.email_status = "PENDING"
    db.commit()
    return _out(db, invitation)


@router.post("/{invitation_id}/cancel")
def cancel_invitation(
    invitation_id: int,
    _: PlatformOwner,
    db: DbSession,
) -> dict:
    invitation = _invitation(db, invitation_id)
    refresh_status(db, invitation)
    if invitation.status == InvitationStatus.CANCELLED:
        return _out(db, invitation)
    if invitation.status in {InvitationStatus.EXPIRED, InvitationStatus.EXHAUSTED}:
        raise HTTPException(409, "La invitación ya no está activa.")
    invitation.status = InvitationStatus.CANCELLED
    invitation.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return _out(db, invitation)
