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

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import AIConnection, AIConnectionOwnerType, AIConnectionStatus, utcnow
from app.ai.providers import ProviderError, build_provider
from app.core.security import decrypt_secret

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


def run_json_task(
    db: Session, account: Account, *, system: str, user: str, task: dict
) -> AIResult:
    errors: list[str] = []
    failed: list[str] = []
    for connection in candidate_connections(db, account):
        try:
            data = provider_for(connection).complete_json(system, user, task)
        except ProviderError as exc:
            _mark_failure(connection, exc)
            failed.append(connection.name)
            errors.append(f"{connection.name}: {exc.message}")
            db.commit()
            continue
        _mark_success(connection)
        db.commit()
        return AIResult(data=data, connection=connection, failed_connections=failed)
    raise NoAIAvailable(errors)


def check_connection(db: Session, connection: AIConnection) -> tuple[bool, str | None]:
    """Health check liviano. Resetea el backoff si la conexión responde."""
    try:
        provider_for(connection).health_check()
    except ProviderError as exc:
        _mark_failure(connection, exc)
        db.commit()
        return False, exc.message
    _mark_success(connection, used=False)
    db.commit()
    return True, None
