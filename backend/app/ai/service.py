"""Router de IA: selección de conexión, failover, backoff y health checks.

Reglas (documento funcional §24–§29):
- Las conexiones se prueban por prioridad (menor número = primero).
- Mientras una conexión funciona se sigue usando.
- Si falla, se marca su estado, se le aplica backoff y se pasa a la siguiente,
  sin avisar con modales: el resultado indica si hubo cambio de proveedor.
- Si ninguna responde, se lanza NoAIAvailable y el trabajo queda persistido
  (la clase queda pendiente y se reintenta más tarde).
"""

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import (
    AIConnection,
    AIConnectionOwnerType,
    AIConnectionStatus,
    AIUsageEvent,
    utcnow,
)
from app.ai.providers import ProviderError, build_provider
from app.core.security import decrypt_secret

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


def candidate_connections(
    db: Session, account: Account, *, include_backoff: bool = False
) -> list[AIConnection]:
    """Conexiones de la cuenta (BYOK) y, después, las de la plataforma."""
    rows = db.scalars(
        select(AIConnection).where(
            AIConnection.active.is_(True),
            or_(
                (AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT)
                & (AIConnection.owner_id == account.id),
                AIConnection.owner_type == AIConnectionOwnerType.PLATFORM,
            ),
        )
    ).all()
    rows = sorted(
        rows,
        key=lambda c: (c.owner_type != AIConnectionOwnerType.ACCOUNT, c.priority, c.id),
    )
    if include_backoff:
        return list(rows)
    return [c for c in rows if c.is_usable]


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
            errors.append(f"{connection.name}: {reason}")
            continue
        try:
            data = provider_for(connection).complete_json(system, user, task)
        except ProviderError as exc:
            _mark_failure(connection, exc)
            record_usage(db, connection, account=account, operation=operation, error=exc)
            failed.append(connection.name)
            errors.append(f"{connection.name}: {exc.message}")
            db.commit()
            continue
        _mark_success(connection)
        record_usage(db, connection, account=account, operation=operation)
        db.commit()
        return AIResult(data=data, connection=connection, failed_connections=failed)
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
