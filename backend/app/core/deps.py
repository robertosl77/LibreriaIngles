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


def get_study_context(db: DbSession, account: CurrentAccount) -> StudyContext:
    profile = get_active_profile(db, account)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cuenta no tiene un perfil de estudio activo.",
        )
    return StudyContext(account=account, profile=profile)


CurrentStudy = Annotated[StudyContext, Depends(get_study_context)]
