from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountType(str, Enum):
    PERSONAL = "PERSONAL"
    CORPORATE = "CORPORATE"


class AuthMethod(str, Enum):
    GOOGLE = "GOOGLE"
    LOCAL = "LOCAL"


class AccountStatus(str, Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class PlatformRole(str, Enum):
    PLATFORM_OWNER = "PLATFORM_OWNER"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_subject: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        SqlEnum(AccountType, native_enum=False), index=True
    )
    auth_method: Mapped[AuthMethod] = mapped_column(
        SqlEnum(AuthMethod, native_enum=False)
    )
    status: Mapped[AccountStatus] = mapped_column(
        SqlEnum(AccountStatus, native_enum=False),
        default=AccountStatus.PENDING_VERIFICATION,
    )
    platform_role: Mapped[PlatformRole | None] = mapped_column(
        SqlEnum(PlatformRole, native_enum=False), nullable=True
    )
    document_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
