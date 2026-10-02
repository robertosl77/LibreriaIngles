"""Alta e ingreso de cuentas personales."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import (
    Account,
    AccountStatus,
    AccountType,
    AuthMethod,
    PlatformRole,
)
from app.core.config import settings
from app.core.deps import get_active_profile
from app.study_profiles.models import (
    AccountStudyProfile,
    StudyProfile,
    StudyProfileLinkMethod,
)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


@dataclass
class GoogleIdentity:
    subject: str
    email: str
    name: str | None


def verify_google_credential(credential: str) -> GoogleIdentity:
    """Valida el ID token de Google Identity Services contra Google."""
    if not settings.google_client_id:
        raise AuthError("GOOGLE_CLIENT_ID no está configurado en el backend.")

    try:
        response = httpx.get(
            GOOGLE_TOKENINFO_URL, params={"id_token": credential}, timeout=10
        )
    except httpx.HTTPError as exc:
        raise AuthError("No se pudo contactar a Google para validar el login.") from exc

    if response.status_code != 200:
        raise AuthError("El token de Google no es válido.")

    data = response.json()
    if data.get("aud") != settings.google_client_id:
        raise AuthError("El token de Google no corresponde a esta aplicación.")
    if data.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("Emisor del token inválido.")
    if str(data.get("email_verified")).lower() != "true":
        raise AuthError("El email de Google no está verificado.")

    return GoogleIdentity(
        subject=data["sub"], email=data["email"].lower(), name=data.get("name")
    )


def _ensure_profile(db: Session, account: Account) -> None:
    if get_active_profile(db, account) is not None:
        return
    profile = StudyProfile()
    db.add(profile)
    db.flush()
    db.add(
        AccountStudyProfile(
            account_id=account.id,
            study_profile_id=profile.id,
            link_method=StudyProfileLinkMethod.INITIAL,
        )
    )


def _apply_platform_role(account: Account) -> None:
    if account.email.lower() in settings.platform_owner_email_set:
        account.platform_role = PlatformRole.PLATFORM_OWNER


def login_personal(
    db: Session,
    *,
    email: str,
    google_subject: str | None,
    display_name: str | None,
    auth_method: AuthMethod,
) -> Account:
    """Busca o crea la cuenta personal y garantiza su perfil de estudio."""
    email = email.strip().lower()
    account = None
    if google_subject:
        account = db.scalar(
            select(Account).where(Account.google_subject == google_subject)
        )
    if account is None:
        account = db.scalar(select(Account).where(Account.email == email))

    if account is None:
        account = Account(
            email=email,
            google_subject=google_subject,
            display_name=display_name,
            account_type=AccountType.PERSONAL,
            auth_method=auth_method,
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        db.flush()
    else:
        if account.account_type != AccountType.PERSONAL:
            raise AuthError("Ese email pertenece a una cuenta corporativa.")
        if account.status == AccountStatus.DISABLED:
            raise AuthError("La cuenta está deshabilitada.")
        if google_subject and not account.google_subject:
            account.google_subject = google_subject
        if display_name and not account.display_name:
            account.display_name = display_name
        account.status = AccountStatus.ACTIVE

    first_login = account.first_login_at is None
    now = datetime.now(timezone.utc)
    if first_login:
        account.first_login_at = now
    account.last_login_at = now

    _apply_platform_role(account)
    _ensure_profile(db, account)

    # Los datos esenciales del login deben quedar fuera del savepoint de campañas.
    db.flush()

    # Una campaña es un beneficio accesorio: nunca puede impedir el ingreso.
    from app.campaigns.service import evaluate_login_campaigns

    try:
        with db.begin_nested():
            evaluate_login_campaigns(db, account, first_login=first_login)
    except Exception:
        logger.exception(
            "Falló la evaluación de campañas durante login para account_id=%s",
            account.id,
        )
    db.commit()
    return account
