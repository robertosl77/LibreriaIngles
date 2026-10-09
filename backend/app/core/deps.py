"""Dependencias comunes de FastAPI: sesión de base y usuario autenticado."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountStatus
from app.core.security import InvalidSessionToken, decode_access_token
from app.db import SessionLocal
from app.memberships.models import Membership, MembershipRole, MembershipStatus
from app.organizations.models import Organization
from app.study_profiles.models import (
    AccountStudyProfile,
    AccountStudyProfileStatus,
    StudyProfile,
    StudyProfileStatus,
)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str = "Sesión inválida o vencida.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_account(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Account:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Falta el token de sesión.")

    try:
        account_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    except InvalidSessionToken:
        raise _unauthorized()

    account = db.get(Account, account_id)
    if account is None or account.status != AccountStatus.ACTIVE:
        raise _unauthorized()
    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]


ORGANIZATION_HEADER = "X-Organization-Id"


@dataclass(frozen=True)
class TenantContext:
    """T-220 (E-01): empresa en la que actúa el request.

    Sin header = actividad personal (organization_id None). Con header, la cuenta tiene que tener
    una membresía ACTIVA en esa empresa activa; si no, 403. Ningún endpoint arma este dato a mano.
    """

    organization_id: int | None = None
    membership_id: int | None = None
    role: MembershipRole | None = None

    @property
    def is_personal(self) -> bool:
        return self.organization_id is None


PERSONAL = TenantContext()


def resolve_tenant(db: Session, account: Account, organization_id: int | None) -> TenantContext:
    if organization_id is None:
        return PERSONAL
    membership = db.scalar(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.account_id == account.id,
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
            Organization.active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenés una membresía activa en esa organización.",
        )
    return TenantContext(
        organization_id=membership.organization_id,
        membership_id=membership.id,
        role=membership.role,
    )


def get_tenant(
    db: DbSession,
    account: CurrentAccount,
    x_organization_id: Annotated[int | None, Header(alias=ORGANIZATION_HEADER)] = None,
) -> TenantContext:
    return resolve_tenant(db, account, x_organization_id)


CurrentTenant = Annotated[TenantContext, Depends(get_tenant)]


def active_memberships(db: Session, account: Account) -> list[tuple[Membership, Organization]]:
    """Empresas en las que la cuenta puede actuar (para el selector del front)."""
    return list(
        db.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.account_id == account.id,
                Membership.status == MembershipStatus.ACTIVE,
                Organization.active.is_(True),
            )
            .order_by(Organization.display_name)
        ).all()
    )


@dataclass
class StudyContext:
    """Cuenta autenticada + perfil de estudio activo.

    organization_id / membership_id quedan en None para actividad personal.
    """

    account: Account
    profile: StudyProfile
    organization_id: int | None = None
    membership_id: int | None = None


def get_active_profile(db: Session, account: Account) -> StudyProfile | None:
    return db.scalar(
        select(StudyProfile)
        .join(
            AccountStudyProfile,
            AccountStudyProfile.study_profile_id == StudyProfile.id,
        )
        .where(
            AccountStudyProfile.account_id == account.id,
            AccountStudyProfile.status == AccountStudyProfileStatus.ACTIVE,
            StudyProfile.status == StudyProfileStatus.ACTIVE,
        )
        .order_by(AccountStudyProfile.linked_at.desc())
        .limit(1)
    )


def get_study_context(
    db: DbSession, account: CurrentAccount, tenant: CurrentTenant
) -> StudyContext:
    profile = get_active_profile(db, account)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cuenta no tiene un perfil de estudio activo.",
        )
    # T-220 (E-01): la empresa sale del request validado, no queda siempre en None.
    return StudyContext(
        account=account,
        profile=profile,
        organization_id=tenant.organization_id,
        membership_id=tenant.membership_id,
    )


CurrentStudy = Annotated[StudyContext, Depends(get_study_context)]
