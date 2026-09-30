from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.accounts.models import AuthMethod, PlatformRole
from app.ai.service import candidate_connections
from app.auth import service
from app.core.config import settings
from app.core.deps import CurrentStudy, DbSession
from app.core.security import create_access_token
from app.curriculum.service import CEFR_LEVELS, available_levels
from app.learning.models import ClassSession, ClassSessionStatus

router = APIRouter(tags=["auth"])


class AuthConfig(BaseModel):
    googleClientId: str | None
    devLoginEnabled: bool


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=10)


class DevLoginRequest(BaseModel):
    email: EmailStr
    name: str | None = None


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"


class LevelRequest(BaseModel):
    level: str


@router.get("/auth/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    return AuthConfig(
        googleClientId=settings.google_client_id or None,
        devLoginEnabled=settings.dev_login_allowed,
    )


@router.post("/auth/google", response_model=TokenResponse)
def login_google(payload: GoogleLoginRequest, db: DbSession) -> TokenResponse:
    try:
        identity = service.verify_google_credential(payload.credential)
        account = service.login_personal(
            db,
            email=identity.email,
            google_subject=identity.subject,
            display_name=identity.name,
            auth_method=AuthMethod.GOOGLE,
        )
    except service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    return TokenResponse(accessToken=create_access_token(account.id))


@router.post("/auth/dev-login", response_model=TokenResponse)
def login_dev(payload: DevLoginRequest, db: DbSession) -> TokenResponse:
    if not settings.dev_login_allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No disponible.")
    try:
        account = service.login_personal(
            db,
            email=payload.email,
            google_subject=None,
            display_name=payload.name,
            # Simula el alta personal (Google) sin pasar por Google. Solo en local.
            auth_method=AuthMethod.GOOGLE,
        )
    except service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    return TokenResponse(accessToken=create_access_token(account.id))


def _me_payload(study, db) -> dict:
    account = study.account
    profile = study.profile
    counts = dict(
        db.execute(
            select(ClassSession.status, func.count())
            .where(ClassSession.study_profile_id == profile.id)
            .group_by(ClassSession.status)
        ).all()
    )
    ai_connections = candidate_connections(db, account, include_backoff=True)
    return {
        "account": {
            "id": account.id,
            "email": account.email,
            "displayName": account.display_name,
            "isPlatformOwner": account.platform_role == PlatformRole.PLATFORM_OWNER,
        },
        "studyProfile": {
            "id": profile.id,
            "selectedLevel": profile.selected_level,
            "estimatedLevel": profile.estimated_level,
            "operationalLevel": profile.operational_level,
        },
        "levels": {"all": CEFR_LEVELS, "available": available_levels()},
        "classes": {
            "inProgress": counts.get(ClassSessionStatus.READY, 0)
            + counts.get(ClassSessionStatus.IN_PROGRESS, 0),
            "awaitingEvaluation": counts.get(ClassSessionStatus.AWAITING_EVALUATION, 0),
            "generationFailed": counts.get(ClassSessionStatus.GENERATION_FAILED, 0),
            "completed": counts.get(ClassSessionStatus.COMPLETED, 0),
        },
        "ai": {
            "connections": len(ai_connections),
            "available": sum(1 for c in ai_connections if c.is_usable),
        },
    }


@router.get("/me")
def me(study: CurrentStudy, db: DbSession) -> dict:
    return _me_payload(study, db)


@router.put("/me/level")
def set_level(payload: LevelRequest, study: CurrentStudy, db: DbSession) -> dict:
    level = payload.level.upper()
    if level not in CEFR_LEVELS:
        raise HTTPException(422, "Nivel CEFR inválido.")
    if level not in available_levels():
        raise HTTPException(
            422,
            f"La currícula de {level} todavía no está disponible.",
        )
    # Elegir nivel manualmente fija también el nivel operativo inicial.
    # Luego el motor puede ajustarlo con evidencia (documento funcional §6 y §8).
    study.profile.selected_level = level
    study.profile.operational_level = level
    db.commit()
    return _me_payload(study, db)
