from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudyProfileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class AccountStudyProfileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class StudyProfileLinkMethod(str, Enum):
    INITIAL = "INITIAL"
    EMAIL_CODE = "EMAIL_CODE"


class LinkVerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class StudyProfile(Base):
    __tablename__ = "study_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StudyProfileStatus] = mapped_column(
        SqlEnum(StudyProfileStatus, native_enum=False),
        default=StudyProfileStatus.ACTIVE,
    )
    # Niveles CEFR (A1..C2). Ver documento funcional §6.
    selected_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    estimated_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    operational_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AccountStudyProfile(Base):
    __tablename__ = "account_study_profiles"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), primary_key=True
    )
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id"), primary_key=True
    )
    status: Mapped[AccountStudyProfileStatus] = mapped_column(
        SqlEnum(AccountStudyProfileStatus, native_enum=False),
        default=AccountStudyProfileStatus.ACTIVE,
    )
    link_method: Mapped[StudyProfileLinkMethod] = mapped_column(
        SqlEnum(StudyProfileLinkMethod, native_enum=False),
        default=StudyProfileLinkMethod.INITIAL,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AccountLinkVerification(Base):
    __tablename__ = "account_link_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id")
    )
    email: Mapped[str] = mapped_column(String(320))
    code_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[LinkVerificationStatus] = mapped_column(
        SqlEnum(LinkVerificationStatus, native_enum=False),
        default=LinkVerificationStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
