from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
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


class MembershipRole(str, Enum):
    OWNER = "OWNER"
    STUDENT = "STUDENT"


class MembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"


class InvitationStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class StudyProfileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


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
    document_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_number: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(120))
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="AR")
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        Index(
            "uq_pending_invitation_org_email",
            "organization_id",
            "email",
            unique=True,
            sqlite_where=text("status = 'PENDING'"),
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[MembershipRole] = mapped_column(
        SqlEnum(MembershipRole, native_enum=False),
        default=MembershipRole.STUDENT,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        SqlEnum(InvitationStatus, native_enum=False),
        default=InvitationStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class StudyProfile(Base):
    __tablename__ = "study_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StudyProfileStatus] = mapped_column(
        SqlEnum(StudyProfileStatus, native_enum=False),
        default=StudyProfileStatus.ACTIVE,
    )
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
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    link_method: Mapped[str] = mapped_column(String(40), default="INITIAL")
