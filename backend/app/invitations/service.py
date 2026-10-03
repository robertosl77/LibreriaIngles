"""Motor único de invitaciones de T-004 etapa 3."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.benefits.models import Benefit
from app.benefits.service import apply_service_benefit
from app.core.security import decrypt_secret, encrypt_secret
from app.invitations.models import (
    Invitation,
    InvitationRecipientMode,
    InvitationRedemption,
    InvitationStatus,
)
from app.subscriptions.models import SubscriptionOrigin


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def set_token(invitation: Invitation, token: str) -> None:
    invitation.token_hash = token_hash(token)
    invitation.token_encrypted = encrypt_secret(token)


def invitation_token(invitation: Invitation) -> str | None:
    if not invitation.token_encrypted:
        return None
    return decrypt_secret(invitation.token_encrypted)


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    shown = local[:1] if local else ""
    return f"{shown}***@{domain}"


def redemption_count(db: Session, invitation_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(InvitationRedemption.id)).where(
                InvitationRedemption.invitation_id == invitation_id
            )
        )
        or 0
    )


def refresh_status(db: Session, invitation: Invitation, *, now: datetime | None = None) -> None:
    """Materializa vencimiento/cupo sin alterar estados cancelados."""
    if invitation.status in {InvitationStatus.CANCELLED, InvitationStatus.EXPIRED}:
        return
    now = now or utcnow()
    expires = _as_utc(invitation.expires_at)
    if expires is not None and expires <= now:
        invitation.status = InvitationStatus.EXPIRED
        db.flush()
        return
    if redemption_count(db, invitation.id) >= invitation.max_redemptions:
        invitation.status = InvitationStatus.EXHAUSTED
        db.flush()
    elif invitation.status == InvitationStatus.EXHAUSTED:
        # Útil para el purge DEV: si se elimina un canje, el cupo vuelve a estar disponible.
        invitation.status = InvitationStatus.ACTIVE
        db.flush()


class InvitationClaimError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RedemptionResult:
    invitation: Invitation
    redemption: InvitationRedemption
    already_redeemed: bool


def _status_error(invitation: Invitation) -> InvitationClaimError:
    messages = {
        InvitationStatus.CANCELLED: "La invitación fue anulada.",
        InvitationStatus.EXPIRED: "La invitación venció.",
        InvitationStatus.EXHAUSTED: "La invitación ya alcanzó su cantidad máxima de canjes.",
    }
    return InvitationClaimError(
        invitation.status.value,
        messages.get(invitation.status, "La invitación no está disponible."),
    )


def redeem_invitation(
    db: Session,
    token: str,
    account: Account,
) -> RedemptionResult:
    """Canje idempotente y con reserva de cupo.

    La fila de invitación se bloquea en motores que soportan FOR UPDATE; SQLite serializa
    escrituras. Una invitación nominada valida el email de la cuenta autenticada.
    """
    hashed = token_hash(token)
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == hashed).with_for_update()
    )
    if invitation is None:
        raise InvitationClaimError("INVALID", "La invitación no existe o el link ya fue reemplazado.")

    existing = db.scalar(
        select(InvitationRedemption).where(
            InvitationRedemption.invitation_id == invitation.id,
            InvitationRedemption.account_id == account.id,
        )
    )
    if existing is not None:
        return RedemptionResult(invitation, existing, True)

    refresh_status(db, invitation)
    if invitation.status != InvitationStatus.ACTIVE:
        raise _status_error(invitation)

    if (
        invitation.recipient_mode == InvitationRecipientMode.NAMED
        and (invitation.email or "").strip().lower() != account.email.strip().lower()
    ):
        raise InvitationClaimError(
            "WRONG_RECIPIENT",
            "La invitación fue emitida para otra cuenta. Iniciaste sesión normalmente, pero este beneficio no se aplicó.",
        )

    used = redemption_count(db, invitation.id)
    if used >= invitation.max_redemptions:
        invitation.status = InvitationStatus.EXHAUSTED
        db.flush()
        raise _status_error(invitation)

    benefit = db.get(Benefit, invitation.benefit_id) if invitation.benefit_id else None
    if benefit is None:
        raise InvitationClaimError("BENEFIT_MISSING", "La invitación no tiene un beneficio válido.")

    creator = (
        db.get(Account, invitation.created_by_account_id)
        if invitation.created_by_account_id
        else None
    )
    application = apply_service_benefit(
        db,
        benefit,
        account,
        granted_by=creator,
        origin=SubscriptionOrigin.INVITATION,
        note=f"Invitación #{invitation.id}: {invitation.name}",
    )
    if not application.applied or application.subscription is None:
        raise InvitationClaimError(
            "SERVICE_CONFLICT",
            application.error or "El beneficio no pudo aplicarse al servicio actual.",
        )

    redemption = InvitationRedemption(
        invitation_id=invitation.id,
        account_id=account.id,
        subscription_id=application.subscription.id,
        benefit_summary=application.summary,
    )
    db.add(redemption)
    db.flush()

    if used + 1 >= invitation.max_redemptions:
        invitation.status = InvitationStatus.EXHAUSTED
    db.flush()
    return RedemptionResult(invitation, redemption, False)
