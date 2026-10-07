from datetime import timedelta
import hashlib
import hmac
import secrets
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.organizations.models import utcnow
from app.verifications.models import VerificationChallenge, VerificationPurpose


class ChallengeError(Exception):
    pass


class ChallengeCooldown(ChallengeError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(f"Esperá {self.retry_after_seconds} segundos antes de reenviar.")


class ChallengeRateLimited(ChallengeError):
    pass


class ChallengeInvalid(ChallengeError):
    pass


class ChallengeExpired(ChallengeError):
    pass


class ChallengeExhausted(ChallengeError):
    pass


def _hmac_digest(*parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def continuation_token_digest(raw_token: str) -> str:
    return _hmac_digest("organization-onboarding-continuation", raw_token)


def new_continuation_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, continuation_token_digest(raw)


def verification_code_digest(
    challenge_public_id: str,
    destination: str,
    code: str,
) -> str:
    return _hmac_digest(
        "verification-code",
        challenge_public_id,
        destination.lower(),
        code,
    )


def _normalized_dt(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=utcnow().tzinfo)
    return value


def _active_for_context(db, purpose: VerificationPurpose, context_type: str, context_id: str):
    return db.scalars(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.purpose == purpose.value,
            VerificationChallenge.context_type == context_type,
            VerificationChallenge.context_id == context_id,
            VerificationChallenge.consumed_at.is_(None),
            VerificationChallenge.invalidated_at.is_(None),
        )
        .order_by(VerificationChallenge.created_at.desc())
    ).all()


def invalidate_active_challenges(
    db,
    *,
    purpose: VerificationPurpose,
    context_type: str,
    context_id: str,
) -> int:
    rows = _active_for_context(db, purpose, context_type, context_id)
    now = utcnow()
    for row in rows:
        row.invalidated_at = now
    return len(rows)


def create_challenge(
    db,
    *,
    purpose: VerificationPurpose,
    context_type: str,
    context_id: str,
    destination: str,
) -> tuple[VerificationChallenge, str]:
    now = utcnow()
    existing = _active_for_context(db, purpose, context_type, context_id)
    if existing:
        last = existing[0]
        sent_at = _normalized_dt(last.sent_at)
        if sent_at is not None:
            retry_at = sent_at + timedelta(seconds=settings.verification_resend_cooldown_seconds)
            if now < retry_at:
                raise ChallengeCooldown(int((retry_at - now).total_seconds()) + 1)

    window_start = now - timedelta(hours=1)
    recent = db.scalars(
        select(VerificationChallenge).where(
            VerificationChallenge.purpose == purpose.value,
            VerificationChallenge.context_type == context_type,
            VerificationChallenge.context_id == context_id,
            VerificationChallenge.created_at >= window_start,
        )
    ).all()
    if len(recent) >= settings.verification_max_sends_per_hour:
        raise ChallengeRateLimited(
            "Se alcanzó el límite temporal de envíos. Intentá nuevamente más tarde."
        )

    invalidate_active_challenges(
        db,
        purpose=purpose,
        context_type=context_type,
        context_id=context_id,
    )

    public_id = str(uuid4())
    code = f"{secrets.randbelow(1_000_000):06d}"
    destination = destination.strip().lower()
    row = VerificationChallenge(
        public_id=public_id,
        purpose=purpose.value,
        context_type=context_type,
        context_id=context_id,
        destination=destination,
        code_digest=verification_code_digest(public_id, destination, code),
        expires_at=now + timedelta(minutes=settings.verification_code_ttl_minutes),
        attempt_count=0,
        max_attempts=settings.verification_max_attempts,
        sent_at=now,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row, code


def latest_active_challenge(
    db,
    *,
    purpose: VerificationPurpose,
    context_type: str,
    context_id: str,
) -> VerificationChallenge | None:
    rows = _active_for_context(db, purpose, context_type, context_id)
    return rows[0] if rows else None


def verify_latest_challenge(
    db,
    *,
    purpose: VerificationPurpose,
    context_type: str,
    context_id: str,
    destination: str,
    code: str,
) -> VerificationChallenge:
    row = latest_active_challenge(
        db,
        purpose=purpose,
        context_type=context_type,
        context_id=context_id,
    )
    if row is None or row.destination != destination.strip().lower():
        raise ChallengeInvalid("No hay un código vigente para verificar.")

    now = utcnow()
    expires_at = _normalized_dt(row.expires_at)
    if expires_at is None or now >= expires_at:
        row.invalidated_at = now
        raise ChallengeExpired("El código venció. Solicitá uno nuevo.")

    if row.attempt_count >= row.max_attempts:
        row.invalidated_at = now
        raise ChallengeExhausted(
            "Este código ya no puede utilizarse. Solicitá uno nuevo."
        )

    expected = verification_code_digest(row.public_id, row.destination, code)
    if row.code_digest is None or not hmac.compare_digest(row.code_digest, expected):
        row.attempt_count += 1
        if row.attempt_count >= row.max_attempts:
            row.invalidated_at = now
            raise ChallengeExhausted(
                "Este código ya no puede utilizarse. Solicitá uno nuevo."
            )
        raise ChallengeInvalid("El código no es válido.")

    row.consumed_at = now
    row.code_digest = None
    return row
