"""Medición normalizada y trazabilidad de consumo de IA (T-049).

El router de IA registra un evento por intento real contra un proveedor. La extracción
provider-specific de usage se resuelve con rutas persistidas en AIProviderUsageMapping:
el dominio de consumo nunca pregunta si el proveedor es OpenAI/Gemini/Anthropic.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.accounts.models import Account, PlatformRole
from app.ai.models import AIConnection, AIProviderUsageMapping, AIUsageEvent
from app.subscriptions.service import effective_service


@dataclass(frozen=True)
class AIUsageContext:
    """Referencia funcional al trabajo que originó la llamada.

    Los campos son genéricos a propósito: campañas, agentes o funcionalidades futuras
    pueden registrar nuevos tipos sin migrar AIUsageEvent.
    """

    organization_id: int | None = None
    membership_id: int | None = None
    subject_type: str | None = None
    subject_id: int | None = None
    subject_label: str | None = None
    subject_route: str | None = None


def _value_at_path(payload: dict | None, path: str | None):
    if not payload or not path:
        return None
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _as_non_negative_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def normalize_usage(
    db: Session,
    provider: str,
    payload: dict | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Convierte el usage externo al contrato común usando configuración de BD.

    No hay condicionales por proveedor. Si no existe mapping o el proveedor no
    informa usage, los tokens quedan en NULL en lugar de inventarse.
    """

    mapping = db.get(AIProviderUsageMapping, provider.upper())
    if mapping is None or not mapping.active:
        return None, None, None, None

    input_tokens = _as_non_negative_int(
        _value_at_path(payload, mapping.input_tokens_path)
    )
    output_tokens = _as_non_negative_int(
        _value_at_path(payload, mapping.output_tokens_path)
    )
    reasoning_tokens = _as_non_negative_int(
        _value_at_path(payload, mapping.reasoning_tokens_path)
    )
    total_tokens = _as_non_negative_int(
        _value_at_path(payload, mapping.total_tokens_path)
    )
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens + (reasoning_tokens or 0)
    return input_tokens, reasoning_tokens, output_tokens, total_tokens


def _service_source(db: Session, account: Account | None, connection: AIConnection) -> str | None:
    if account is None:
        return None
    if account.platform_role == PlatformRole.PLATFORM_OWNER:
        # El OWNER no necesita una membresía para usar ambas fuentes. Guardamos
        # qué fuente efectiva atendió para no inventar un HYBRID comercial.
        return "PLATFORM" if connection.owner_type.value == "PLATFORM" else "BYOK"
    return effective_service(db, account).source.value


def build_usage_event(
    db: Session,
    connection: AIConnection,
    *,
    account: Account | None,
    operation: str,
    success: bool,
    error_code: str | None,
    usage_payload: dict | None = None,
    context: AIUsageContext | None = None,
    model: str | None = None,
    execution_id: str | None = None,
    attempt_index: int | None = None,
) -> AIUsageEvent:
    """Construye el snapshot auditable de una llamada sin guardar prompt/respuesta."""

    input_tokens, reasoning_tokens, output_tokens, total_tokens = normalize_usage(
        db, connection.provider, usage_payload
    )
    context = context or AIUsageContext()
    return AIUsageEvent(
        connection_id=connection.id,
        connection_name=connection.name,
        owner_type=connection.owner_type,
        provider=connection.provider,
        model=model or connection.model,
        account_id=account.id if account else None,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        service_source=_service_source(db, account, connection),
        execution_id=execution_id,
        attempt_index=attempt_index,
        operation=operation,
        subject_type=context.subject_type,
        subject_id=context.subject_id,
        subject_label=context.subject_label,
        subject_route=context.subject_route,
        input_tokens=input_tokens,
        reasoning_tokens=reasoning_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        success=success,
        error_code=error_code,
    )
