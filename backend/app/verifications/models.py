from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationPurpose(str, Enum):
    ORGANIZATION_ONBOARDING_EMAIL = "ORGANIZATION_ONBOARDING_EMAIL"


class VerificationChallenge(Base):
    __tablename__ = "verification_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    purpose: Mapped[VerificationPurpose] = mapped_column(String(80), index=True)
    context_type: Mapped[str] = mapped_column(String(80), index=True)
    context_id: Mapped[str] = mapped_column(String(120), index=True)
    destination: Mapped[str] = mapped_column(String(320), index=True)
    code_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
