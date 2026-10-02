from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.accounts.models import Account, PlatformRole
from app.ai.models import (
    AICredentialAuditEvent,
    AIConnection,
    AIConnectionOwnerType,
    AIConnectionStatus,
    utcnow,
)
from app.ai.providers import PROVIDERS, ProviderError, build_provider
from app.ai.service import (
    LIMIT_WINDOW,
    active_connection,
    check_connection,
    connection_snapshot,
    public_trace,
    provider_for,
    successful_requests,
)
from app.core.config import settings
from app.core.deps import CurrentAccount, DbSession
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from sqlalchemy import select

router = APIRouter(prefix="/ai", tags=["ai"])

Scope = Literal["account", "platform"]


class ConnectionCreate(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    apiKey: str | None = Field(default=None, max_length=2000)
    priority: int = Field(default=100, ge=1, le=10_000)
    scope: Scope = "account"
    # Límites de 24 h: solo para conexiones de plataforma.
    dailyRequestLimit: int | None = Field(default=None, ge=1, le=1_000_000)
    perAccountDailyLimit: int | None = Field(default=None, ge=1, le=1_000_000)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    apiKey: str | None = Field(default=None, max_length=2000)
    priority: int | None = Field(default=None, ge=1, le=10_000)
    active: bool | None = None
    # Enviar null explícito borra el límite.
    dailyRequestLimit: int | None = Field(default=None, ge=1, le=1_000_000)
    perAccountDailyLimit: int | None = Field(default=None, ge=1, le=1_000_000)


class ModelsRequest(BaseModel):
    provider: str
    apiKey: str | None = Field(default=None, max_length=2000)


def _models_payload(provider) -> list[dict]:
    try:
        models = provider.list_models()
    except ProviderError as exc:
        raise HTTPException(422, f"No se pudo obtener la lista de modelos: {exc.message}")
    return [{"id": m.id, "label": m.label} for m in models]


def _is_platform_owner(account: Account) -> bool:
    return account.platform_role == PlatformRole.PLATFORM_OWNER


def _owner_filter(account: Account, scope: Scope):
    if scope == "platform":
        if not _is_platform_owner(account):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo PLATFORM_OWNER.")
        return AIConnectionOwnerType.PLATFORM, None
    return AIConnectionOwnerType.ACCOUNT, account.id


LIMIT_FIELDS = {
    "dailyRequestLimit": "daily_request_limit",
    "perAccountDailyLimit": "per_account_daily_limit",
}


def _reject_limits_outside_platform(owner_type: AIConnectionOwnerType, payload: BaseModel) -> None:
    if owner_type == AIConnectionOwnerType.PLATFORM:
        return
    if any(getattr(payload, f) is not None for f in LIMIT_FIELDS):
        raise HTTPException(422, "Los límites de consumo solo aplican a conexiones de plataforma.")


def _serialize(connection: AIConnection, db=None) -> dict:
    usage = (
        successful_requests(db, connection.id, since=utcnow() - LIMIT_WINDOW)
        if db is not None
        else None
    )
    return {
        "id": connection.id,
        "scope": "platform"
        if connection.owner_type == AIConnectionOwnerType.PLATFORM
        else "account",
        "provider": connection.provider,
        "name": connection.name,
        "model": connection.model or PROVIDERS[connection.provider].default_model,
        "credentialHint": connection.credential_hint,
        "priority": connection.priority,
        "active": connection.active,
        "status": connection.status.value,
        "usable": connection.is_usable,
        "backoffUntil": connection.backoff_until,
        "lastCheckAt": connection.last_check_at,
        "lastUsedAt": connection.last_used_at,
        "lastErrorCode": connection.last_error_code,
        "dailyRequestLimit": connection.daily_request_limit,
        "perAccountDailyLimit": connection.per_account_daily_limit,
        "usage24h": usage,
        "supportsAudioInput": PROVIDERS[connection.provider].supports_audio_input,
    }


def _get_owned(db, account: Account, connection_id: int) -> AIConnection:
    connection = db.get(AIConnection, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")
    if connection.owner_type == AIConnectionOwnerType.ACCOUNT:
        if connection.owner_id != account.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")
    elif connection.owner_type == AIConnectionOwnerType.PLATFORM:
        if not _is_platform_owner(account):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")
    return connection


def _get_owner_credential_connection(
    db, account: Account, connection_id: int
) -> AIConnection:
    """Solo el PLATFORM_OWNER puede recuperar secretos bajo su administración."""
    if not _is_platform_owner(account):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo PLATFORM_OWNER.")

    connection = db.get(AIConnection, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")

    allowed = connection.owner_type == AIConnectionOwnerType.PLATFORM or (
        connection.owner_type == AIConnectionOwnerType.ACCOUNT
        and connection.owner_id == account.id
    )
    if not allowed:
        # No confirmar la existencia de credenciales BYOK de otras cuentas.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión inexistente.")
    if not connection.credentials_encrypted:
        raise HTTPException(status.HTTP_409_CONFLICT, "La conexión no tiene una API key guardada.")
    return connection


@router.get("/providers")
def providers() -> list[dict]:
    return [
        {
            "key": info.key,
            "label": info.label,
            "defaultModel": info.default_model,
            "requiresKey": info.requires_key,
            "supportsAudioInput": info.supports_audio_input,
        }
        for info in PROVIDERS.values()
        if info.key != "MOCK" or settings.mock_ai_allowed
    ]


@router.post("/models")
def list_models_for_key(payload: ModelsRequest, account: CurrentAccount) -> list[dict]:
    """Modelos disponibles para una API key todavía no guardada (alta de conexión).

    La key se usa solo para esta consulta: no se guarda ni se registra.
    """
    provider_key = payload.provider.upper()
    info = PROVIDERS.get(provider_key)
    if info is None or (provider_key == "MOCK" and not settings.mock_ai_allowed):
        raise HTTPException(422, "Proveedor no soportado.")
    if info.requires_key and not payload.apiKey:
        raise HTTPException(422, "Ingresá la API key para consultar los modelos.")
    try:
        provider = build_provider(provider_key, (payload.apiKey or "").strip() or None, None)
    except ProviderError as exc:
        raise HTTPException(422, exc.message)
    return _models_payload(provider)


@router.post("/connections/{connection_id}/credential/copy")
def copy_connection_credential(
    connection_id: int,
    account: CurrentAccount,
    db: DbSession,
    response: Response,
) -> dict:
    """Excepción T-042: copiar una API key solo para el PLATFORM_OWNER.

    La credencial nunca se incluye en listados, logs ni auditoría. El frontend la recibe
    únicamente como respuesta a esta acción explícita para enviarla al portapapeles.
    """
    connection = _get_owner_credential_connection(db, account, connection_id)
    secret = decrypt_secret(connection.credentials_encrypted)
    db.add(
        AICredentialAuditEvent(
            connection_id=connection.id,
            account_id=account.id,
            connection_name=connection.name,
            owner_type=connection.owner_type.value,
            action="COPY",
        )
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"apiKey": secret}


@router.get("/connections/{connection_id}/models")
def list_models_for_connection(connection_id: int, account: CurrentAccount, db: DbSession) -> list[dict]:
    """Modelos disponibles para una conexión existente, con su credencial guardada."""
    connection = _get_owned(db, account, connection_id)
    try:
        provider = provider_for(connection)
    except ProviderError as exc:
        raise HTTPException(422, exc.message)
    return _models_payload(provider)


@router.get("/active")
def active_connections(account: CurrentAccount, db: DbSession) -> dict:
    """Conexiones que el router usaría ahora para texto y audio."""
    default = active_connection(db, account)
    audio = active_connection(db, account, audio=True)
    return {
        "default": public_trace(db, connection_snapshot(default), account) if default else None,
        "audio": public_trace(db, connection_snapshot(audio), account) if audio else None,
    }


@router.get("/connections")
def list_connections(
    account: CurrentAccount, db: DbSession, scope: Scope = "account"
) -> list[dict]:
    owner_type, owner_id = _owner_filter(account, scope)
    query = select(AIConnection).where(AIConnection.owner_type == owner_type)
    query = query.where(
        AIConnection.owner_id.is_(None)
        if owner_id is None
        else AIConnection.owner_id == owner_id
    )
    rows = db.scalars(query.order_by(AIConnection.priority, AIConnection.id)).all()
    return [_serialize(c, db) for c in rows]


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ConnectionCreate, account: CurrentAccount, db: DbSession
) -> dict:
    provider = payload.provider.upper()
    info = PROVIDERS.get(provider)
    if info is None or (provider == "MOCK" and not settings.mock_ai_allowed):
        raise HTTPException(422, "Proveedor no soportado.")
    if info.requires_key and not payload.apiKey:
        raise HTTPException(422, "Falta la API key.")

    owner_type, owner_id = _owner_filter(account, payload.scope)
    _reject_limits_outside_platform(owner_type, payload)
    connection = AIConnection(
        owner_type=owner_type,
        owner_id=owner_id,
        provider=provider,
        name=payload.name.strip(),
        model=(payload.model or "").strip() or info.default_model,
        priority=payload.priority,
        active=True,
        status=AIConnectionStatus.AVAILABLE,
        daily_request_limit=payload.dailyRequestLimit,
        per_account_daily_limit=payload.perAccountDailyLimit,
    )
    if payload.apiKey:
        key = payload.apiKey.strip()
        connection.credentials_encrypted = encrypt_secret(key)
        connection.credential_hint = mask_secret(key)
    db.add(connection)
    db.commit()

    # Documento funcional §26.3: al agregar una conexión, probarla de inmediato.
    ok, error = check_connection(db, connection, account)
    return {**_serialize(connection, db), "test": {"ok": ok, "error": error}}


@router.patch("/connections/{connection_id}")
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    account: CurrentAccount,
    db: DbSession,
) -> dict:
    connection = _get_owned(db, account, connection_id)
    _reject_limits_outside_platform(connection.owner_type, payload)
    for field_name, column in LIMIT_FIELDS.items():
        if field_name in payload.model_fields_set:
            setattr(connection, column, getattr(payload, field_name))
    if payload.name is not None:
        connection.name = payload.name.strip()
    if payload.model is not None:
        connection.model = payload.model.strip() or PROVIDERS[connection.provider].default_model
    if payload.priority is not None:
        connection.priority = payload.priority
    if payload.active is not None:
        connection.active = payload.active
    credentials_changed = False
    if payload.apiKey:
        key = payload.apiKey.strip()
        connection.credentials_encrypted = encrypt_secret(key)
        connection.credential_hint = mask_secret(key)
        credentials_changed = True
    db.commit()

    if credentials_changed or payload.model is not None:
        ok, error = check_connection(db, connection, account)
        return {**_serialize(connection, db), "test": {"ok": ok, "error": error}}
    return _serialize(connection, db)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: int, account: CurrentAccount, db: DbSession) -> None:
    connection = _get_owned(db, account, connection_id)
    db.delete(connection)
    db.commit()


@router.post("/connections/{connection_id}/test")
def test_connection(connection_id: int, account: CurrentAccount, db: DbSession) -> dict:
    connection = _get_owned(db, account, connection_id)
    ok, error = check_connection(db, connection, account)
    return {**_serialize(connection, db), "test": {"ok": ok, "error": error}}
