"""Router de IA: selección de conexión, failover, backoff y health checks.

Reglas (documento funcional §24–§29):
- Las conexiones se prueban por prioridad (menor número = primero).
- Mientras una conexión funciona se sigue usando.
- Si falla, se marca su estado, se le aplica backoff y se pasa a la siguiente,
  sin avisar con modales: el resultado indica si hubo cambio de proveedor.
- Si ninguna responde, se lanza NoAIAvailable y el trabajo queda persistido
  (la clase queda pendiente y se reintenta más tarde).
- Fuente de IA (T-003 + T-004): la decide el servicio vigente de la cuenta.
  BYOK → solo sus conexiones propias · PLATAFORMA → solo las de la plataforma ·
  HÍBRIDO → propias primero y, si fallan, las de la plataforma. El PLATFORM_OWNER usa ambas.
  Sin servicio otorgado, la cuenta es "Individual · propias keys" (BYOK).
"""

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, PlatformRole
from app.ai.models import (
    AIConnection,
    AIConnectionOwnerType,
    AIConnectionStatus,
    AIUsageEvent,
    utcnow,
)
from app.ai.providers import PROVIDERS, ProviderError, build_provider
from app.core.security import decrypt_secret
from app.subscriptions.models import AISource
from app.subscriptions.service import effective_service

LIMIT_WINDOW = timedelta(hours=24)
HEALTH_CHECK = "health_check"

BACKOFF = {
    AIConnectionStatus.QUOTA_EXCEEDED: timedelta(minutes=60),
    AIConnectionStatus.RATE_LIMITED: timedelta(minutes=1),
    AIConnectionStatus.PROVIDER_DOWN: timedelta(minutes=5),
    AIConnectionStatus.NETWORK_ERROR: timedelta(minutes=5),
    AIConnectionStatus.UNKNOWN_ERROR: timedelta(minutes=2),
}


class NoAIAvailable(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("No hay conexiones de IA disponibles.")
        self.errors = errors


@dataclass
class AIResult:
    data: dict
    connection: AIConnection
    failed_connections: list[str] = field(default_factory=list)

    @property
    def switched(self) -> bool:
        return bool(self.failed_connections)


@dataclass
class AudioTranscriptionResult:
    text: str
    connection: AIConnection
    failed_connections: list[str] = field(default_factory=list)
    # Estimación de pronunciación cruda del proveedor (None si no la ofrece).
    pronunciation: dict | None = None

    @property
    def switched(self) -> bool:
        return bool(self.failed_connections)


def ai_sources(db: Session, account: Account) -> tuple[bool, bool]:
    """(usa propias, usa plataforma) según el servicio vigente de la cuenta (T-004)."""
    if account.platform_role == PlatformRole.PLATFORM_OWNER:
        return True, True
    source = effective_service(db, account).source
    if source == AISource.PLATFORM:
        return False, True
    if source == AISource.HYBRID:
        return True, True
    return True, False


def platform_ai_allowed(db: Session, account: Account) -> bool:
    """¿Puede esta cuenta usar las conexiones de IA de la plataforma?"""
    return ai_sources(db, account)[1]


def candidate_connections(
    db: Session, account: Account, *, include_backoff: bool = False
) -> list[AIConnection]:
    """Conexiones que el servicio vigente habilita: propias y/o de la plataforma."""
    use_own, use_platform = ai_sources(db, account)
    own = (AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT) & (
        AIConnection.owner_id == account.id
    )
    platform = AIConnection.owner_type == AIConnectionOwnerType.PLATFORM
    if use_own and use_platform:
        source = or_(own, platform)
    elif use_platform:
        source = platform
    else:
        source = own
    rows = db.scalars(select(AIConnection).where(AIConnection.active.is_(True), source)).all()
    rows = sorted(
        rows,
        key=lambda c: (c.owner_type != AIConnectionOwnerType.ACCOUNT, c.priority, c.id),
    )
    if include_backoff:
        return list(rows)
    return [c for c in rows if c.is_usable]


PLATFORM_LABEL = "IA de Librería Inglés"


def shows_connection_details(account: Account | None, owner_type) -> bool:
    """¿Puede esta cuenta ver nombre/motor de la conexión? (T-055)

    Las conexiones de la plataforma son información interna de sr.macros: el alumno solo ve
    "IA de Librería Inglés". Sus propias conexiones y el dueño ven todo.
    """
    value = getattr(owner_type, "value", owner_type)
    if value != AIConnectionOwnerType.PLATFORM.value:
        return True
    return account is not None and account.platform_role == PlatformRole.PLATFORM_OWNER


def connection_label(connection: AIConnection, account: Account | None) -> str:
    """Nombre de la conexión para mensajes al usuario (errores, avisos)."""
    if shows_connection_details(account, connection.owner_type):
        return connection.name
    return PLATFORM_LABEL


def public_trace(db: Session, trace, account: Account | None):
    """Oculta nombre/proveedor/motor de una traza de IA de plataforma para quien no es dueño.

    Sirve para snapshots de `connection_snapshot` y para resultados de pronunciación. Las trazas
    viejas sin `ownerType` se resuelven por `connectionId` si la conexión sigue existiendo.
    """
    if not isinstance(trace, dict):
        return trace
    owner_type = trace.get("ownerType")
    if owner_type is None and trace.get("connectionId"):
        connection = db.get(AIConnection, trace["connectionId"])
        owner_type = connection.owner_type.value if connection else None
    if owner_type is None or shows_connection_details(account, owner_type):
        return trace
    masked = {**trace, "connection": PLATFORM_LABEL, "provider": "PLATFORM", "model": ""}
    masked["providerLabel"] = PLATFORM_LABEL
    if "connectionId" in masked:
        masked["connectionId"] = None
    return masked


def connection_snapshot(connection: AIConnection) -> dict:
    """Metadatos no sensibles de la conexión que produjo un resultado.

    Se persisten junto al resultado para que el histórico no dependa de que la
    conexión siga existiendo o conserve el mismo nombre/modelo.
    """
    info = PROVIDERS.get(connection.provider.upper())
    model = connection.model or (info.default_model if info else "")
    return {
        "connectionId": connection.id,
        "connection": connection.name,
        "provider": connection.provider,
        "providerLabel": info.label if info else connection.provider,
        "model": model,
        "ownerType": connection.owner_type.value,
    }


def active_connection(
    db: Session,
    account: Account,
    *,
    audio: bool = False,
) -> AIConnection | None:
    """Primera conexión que el router usaría ahora, incluyendo límites de cuota."""
    rows = audio_connections(db, account) if audio else candidate_connections(db, account)
    for connection in rows:
        if limit_reason(db, connection, account) is None:
            return connection
    return None


def connection_supports_audio(connection: AIConnection) -> bool:
    info = PROVIDERS.get(connection.provider.upper())
    return bool(info and info.supports_audio_input)


def audio_connections(
    db: Session, account: Account, *, include_backoff: bool = False
) -> list[AIConnection]:
    """Conexiones utilizables por prioridad que pueden recibir audio."""
    return [
        connection
        for connection in candidate_connections(db, account, include_backoff=include_backoff)
        if connection_supports_audio(connection)
    ]


def has_audio_connection(db: Session, account: Account) -> bool:
    return bool(audio_connections(db, account))


def provider_for(connection: AIConnection):
    api_key = (
        decrypt_secret(connection.credentials_encrypted)
        if connection.credentials_encrypted
        else None
    )
    return build_provider(connection.provider, api_key, connection.model)


def _mark_failure(connection: AIConnection, error: ProviderError) -> None:
    now = utcnow()
    connection.status = error.code
    connection.last_error_code = error.code.value
    connection.last_error_at = now
    connection.last_check_at = now
    delay = BACKOFF.get(error.code)
    connection.backoff_until = now + delay if delay else None


def _mark_success(connection: AIConnection, *, used: bool = True) -> None:
    now = utcnow()
    connection.status = AIConnectionStatus.AVAILABLE
    connection.backoff_until = None
    connection.last_check_at = now
    if used:
        connection.last_used_at = now


# ------------------------------------------------------------------ consumo


def record_usage(
    db: Session,
    connection: AIConnection,
    *,
    account: Account | None,
    operation: str,
    error: ProviderError | None = None,
) -> None:
    db.add(
        AIUsageEvent(
            connection_id=connection.id,
            owner_type=connection.owner_type,
            provider=connection.provider,
            model=connection.model,
            account_id=account.id if account else None,
            operation=operation,
            success=error is None,
            error_code=error.code.value if error else None,
        )
    )


def successful_requests(
    db: Session,
    connection_id: int,
    *,
    since,
    account_id: int | None = None,
) -> int:
    """Requests exitosos (los que consumen cuota), sin contar health checks."""
    query = select(func.count(AIUsageEvent.id)).where(
        AIUsageEvent.connection_id == connection_id,
        AIUsageEvent.success.is_(True),
        AIUsageEvent.operation != HEALTH_CHECK,
        AIUsageEvent.created_at >= since,
    )
    if account_id is not None:
        query = query.where(AIUsageEvent.account_id == account_id)
    return db.scalar(query) or 0


def platform_requests(db: Session, account_id: int, *, since) -> int:
    """Requests exitosos de la cuenta sobre CUALQUIER conexión de la plataforma."""
    return (
        db.scalar(
            select(func.count(AIUsageEvent.id)).where(
                AIUsageEvent.owner_type == AIConnectionOwnerType.PLATFORM,
                AIUsageEvent.account_id == account_id,
                AIUsageEvent.success.is_(True),
                AIUsageEvent.operation != HEALTH_CHECK,
                AIUsageEvent.created_at >= since,
            )
        )
        or 0
    )


def limit_reason(db: Session, connection: AIConnection, account: Account) -> str | None:
    """Motivo por el que la conexión no puede usarse ahora por límites, o None."""
    if connection.daily_request_limit is None and connection.per_account_daily_limit is None:
        return None
    since = utcnow() - LIMIT_WINDOW
    if connection.daily_request_limit is not None:
        used = successful_requests(db, connection.id, since=since)
        if used >= connection.daily_request_limit:
            return "alcanzó su límite total de 24 h"
    if connection.per_account_daily_limit is not None:
        used = successful_requests(db, connection.id, since=since, account_id=account.id)
        if used >= connection.per_account_daily_limit:
            return "alcanzaste tu límite de uso de 24 h"
    return None


# ------------------------------------------------------------------ router


def run_json_task(
    db: Session, account: Account, *, system: str, user: str, task: dict
) -> AIResult:
    errors: list[str] = []
    failed: list[str] = []
    operation = str(task.get("kind") or "unknown")[:40]
    for connection in candidate_connections(db, account):
        reason = limit_reason(db, connection, account)
        if reason:
            # Límite de consumo: se saltea sin marcarla como caída.
            errors.append(f"{connection_label(connection, account)}: {reason}")
            continue
        try:
            data = provider_for(connection).complete_json(system, user, task)
        except ProviderError as exc:
            _mark_failure(connection, exc)
            record_usage(db, connection, account=account, operation=operation, error=exc)
            failed.append(connection.name)
            errors.append(f"{connection_label(connection, account)}: {exc.message}")
            db.commit()
            continue
        _mark_success(connection)
        record_usage(db, connection, account=account, operation=operation)
        db.commit()
        return AIResult(data=data, connection=connection, failed_connections=failed)
    raise NoAIAvailable(errors)


def transcribe_audio(
    db: Session,
    account: Account,
    *,
    audio: bytes,
    mime_type: str,
) -> AudioTranscriptionResult:
    """Transcribe sin persistir el audio y con el mismo failover/límites del router de IA."""
    errors: list[str] = []
    failed: list[str] = []
    for connection in audio_connections(db, account):
        reason = limit_reason(db, connection, account)
        if reason:
            errors.append(f"{connection_label(connection, account)}: {reason}")
            continue
        try:
            analysis = provider_for(connection).analyze_speech(audio, mime_type)
            text = analysis.text.strip()
            if not text:
                raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "No se detectó voz.")
        except ProviderError as exc:
            _mark_failure(connection, exc)
            record_usage(
                db, connection, account=account, operation="transcribe_audio", error=exc
            )
            failed.append(connection.name)
            errors.append(f"{connection_label(connection, account)}: {exc.message}")
            db.commit()
            continue
        _mark_success(connection)
        record_usage(db, connection, account=account, operation="transcribe_audio")
        db.commit()
        return AudioTranscriptionResult(
            text=text,
            connection=connection,
            failed_connections=failed,
            pronunciation=analysis.pronunciation,
        )
    if not errors:
        errors.append("No hay conexiones activas compatibles con audio.")
    raise NoAIAvailable(errors)


def check_connection(
    db: Session, connection: AIConnection, account: Account | None = None
) -> tuple[bool, str | None]:
    """Health check liviano. Resetea el backoff si la conexión responde."""
    try:
        provider_for(connection).health_check()
    except ProviderError as exc:
        _mark_failure(connection, exc)
        record_usage(db, connection, account=account, operation=HEALTH_CHECK, error=exc)
        db.commit()
        return False, exc.message
    _mark_success(connection, used=False)
    record_usage(db, connection, account=account, operation=HEALTH_CHECK)
    db.commit()
    return True, None
