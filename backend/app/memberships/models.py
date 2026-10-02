from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MembershipRole(str, Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"


class MembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "organization_id",
            name="uq_membership_account_org",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        SqlEnum(MembershipRole, native_enum=False),
        default=MembershipRole.STUDENT,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SqlEnum(MembershipStatus, native_enum=False),
        default=MembershipStatus.ACTIVE,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


# Compatibilidad temporal: el modelo Invitation vivía originalmente en este módulo.
from app.invitations.models import (  # noqa: E402,F401
    Invitation,
    InvitationRecipientMode,
    InvitationStatus,
)
