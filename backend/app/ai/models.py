from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes sin zona: se asumen UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class AIConnectionOwnerType(str, Enum):
    PLATFORM = "PLATFORM"
    ORGANIZATION = "ORGANIZATION"
    ACCOUNT = "ACCOUNT"


class AIConnectionStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    PROVIDER_DOWN = "PROVIDER_DOWN"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    DISABLED = "DISABLED"


class AIConnection(Base):
    __tablename__ = "ai_connections"
    __table_args__ = (
        CheckConstraint(
            "(owner_type = 'PLATFORM' AND owner_id IS NULL) "
            "OR (owner_type <> 'PLATFORM' AND owner_id IS NOT NULL)",
            name="ck_ai_connections_owner",
        ),
        Index("ix_ai_connections_owner", "owner_type", "owner_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[AIConnectionOwnerType] = mapped_column(
        SqlEnum(AIConnectionOwnerType, native_enum=False)
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(
        String(4000), nullable=True
    )
    credential_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[AIConnectionStatus] = mapped_column(
        SqlEnum(AIConnectionStatus, native_enum=False),
        default=AIConnectionStatus.AVAILABLE,
    )
    backoff_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    @property
    def is_usable(self) -> bool:
        if not self.active:
            return False
        if self.status in (
            AIConnectionStatus.INVALID_CREDENTIALS,
            AIConnectionStatus.DISABLED,
        ):
            return False
        backoff = as_utc(self.backoff_until)
        return backoff is None or backoff <= utcnow()
