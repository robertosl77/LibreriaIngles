import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.accounts.models import AuthMethod, PlatformRole
from app.ai.models import AIConnection, AIConnectionOwnerType
from app.ai.service import ai_sources, candidate_connections
from app.auth import service
from app.core.config import settings
from app.core.deps import CurrentStudy, DbSession, active_memberships
from app.core.security import create_access_token
from app.curriculum.service import CEFR_LEVELS, available_levels
from app.campaigns.service import reconcile_first_login_campaigns
from app.learning.models import ClassSession, ClassSessionStatus
from app.subscriptions.service import effective_service

router = APIRouter(tags=["auth"])
# T-220 (E-07): rutas de desarrollo en un router aparte; solo se montan fuera de producción.
dev_router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


def _reconcile_campaigns_safely(db: DbSession, account) -> None:
    """Las campañas nunca deben romper endpoints esenciales de sesión."""
    try:
        with db.begin_nested():
            reconcile_first_login_campaigns(db, account)
    except Exception:
        logger.exception(
            "Falló la reconciliación de campañas FIRST_LOGIN para account_id=%s",
            account.id,
        )



class AuthConfig(BaseModel):
    googleClientId: str | None
    devLoginEnabled: bool


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=10)
    invitationToken: str | None = Field(default=None, min_length=10, max_length=500)


class DevLoginRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    invitationToken: str | None = Field(default=None, min_length=10, max_length=500)


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
            invitation_token=payload.invitationToken,
        )
    except service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    return TokenResponse(accessToken=create_access_token(account.id))


@dev_router.post("/auth/dev-login", response_model=TokenResponse)
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
            invitation_token=payload.invitationToken,
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
    service = effective_service(db, account)
    uses_own, uses_platform = ai_sources(db, account)
    service_payload = service.payload()
    service_payload["usesOwnKeys"] = uses_own
    service_payload["usesPlatform"] = uses_platform
    if account.platform_role == PlatformRole.PLATFORM_OWNER:
        # El dueño no tiene servicio: configura y usa las conexiones de la plataforma (T-200).
        service_payload.update(
            name="Dueño de la plataforma", source="PLATFORM", ownKeys="unused", granted=False
        )
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
            # Propias guardadas, se usen o no según el servicio (T-055).
            "own": db.scalar(
                select(func.count(AIConnection.id)).where(
                    AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT,
                    AIConnection.owner_id == account.id,
                )
            )
            or 0,
        },
        "service": service_payload,
        # T-220 (E-01): empresas en las que puede actuar y la del request actual.
        "organizations": [
            {"id": org.id, "name": org.display_name, "role": membership.role.value}
            for membership, org in active_memberships(db, account)
        ],
        "activeOrganizationId": study.organization_id,
    }


@router.get("/me")
def me(study: CurrentStudy, db: DbSession) -> dict:
    # Si el request de autenticación no alcanzó a aplicar FIRST_LOGIN, /me lo reconcilia
    # usando first_login_at + activated_at persistidos.
    _reconcile_campaigns_safely(db, study.account)
    payload = _me_payload(study, db)
    db.commit()  # persiste campaña/vencimientos perezosos del servicio
    return payload


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
    db.flush()
    _reconcile_campaigns_safely(db, study.account)
    payload = _me_payload(study, db)
    db.commit()
    return payload
