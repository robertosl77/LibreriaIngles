"""Catálogo único de capacidades del motor de campañas (T-065).

Backend, constructor manual y asistente IA consumen esta misma definición para evitar que
condiciones/triggers/acciones se dupliquen en varios lugares.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.campaigns.models import CampaignNotification, CampaignTrigger


class CampaignCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class RuleCapability:
    key: str
    label: str
    value_type: str
    operators: tuple[str, ...]
    description: str
    options: tuple[tuple[str, str], ...] = ()
    available: bool = True
    requires_window: bool = False
    window_min_days: int = 1
    window_max_days: int = 3650

    def payload(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "valueType": self.value_type,
            "operators": list(self.operators),
            "description": self.description,
            "options": [{"value": value, "label": label} for value, label in self.options],
            "available": self.available,
            "requiresWindow": self.requires_window,
            "windowMinDays": self.window_min_days if self.requires_window else None,
            "windowMaxDays": self.window_max_days if self.requires_window else None,
        }


RULE_CAPABILITIES: tuple[RuleCapability, ...] = (
    RuleCapability(
        "ACCOUNT_TYPE",
        "Tipo de cuenta",
        "enum",
        ("EQ",),
        "Tipo de cuenta del destinatario.",
        (("PERSONAL", "Personal"), ("CORPORATE", "Corporativa")),
    ),
    RuleCapability(
        "HAS_GRANTED_SERVICE",
        "Tiene servicio vigente",
        "boolean",
        ("EQ",),
        "Indica si la cuenta tiene actualmente un servicio otorgado vigente.",
        (("true", "Sí"), ("false", "No")),
    ),
    RuleCapability(
        "SERVICE_SOURCE",
        "Fuente de IA actual",
        "enum",
        ("EQ",),
        "Fuente de IA del servicio que rige actualmente.",
        (("BYOK", "Propias keys"), ("PLATFORM", "Plataforma"), ("HYBRID", "Híbrido")),
    ),
    RuleCapability(
        "EMAIL_DOMAIN",
        "Dominio de email",
        "string",
        ("EQ",),
        "Dominio del correo de la cuenta, sin @.",
    ),
    RuleCapability(
        "DAYS_SINCE_CREATED",
        "Días desde registro",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días transcurridos desde la creación de la cuenta.",
    ),
    RuleCapability(
        "CREATED_AT",
        "Fecha de registro",
        "datetime",
        ("EQ", "GTE", "LTE"),
        "Fecha de creación de la cuenta.",
    ),
    RuleCapability(
        "DAYS_SINCE_LAST_ACTIVITY",
        "Días desde última actividad",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días desde la última clase de práctica completada por esa cuenta.",
    ),
    RuleCapability(
        "NEVER_STUDIED",
        "Nunca realizó una clase",
        "boolean",
        ("EQ",),
        "Indica que no existe ninguna clase de práctica completada por esa cuenta.",
        (("true", "Sí"), ("false", "No")),
    ),
    RuleCapability(
        "DAYS_SINCE_SERVICE_EXPIRED",
        "Días desde vencimiento de servicio",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días desde el último servicio vencido. No equivale a antigüedad de pago.",
    ),
    RuleCapability(
        "CURRENT_LEVEL",
        "Nivel actual",
        "enum",
        ("EQ",),
        "Nivel operativo/seleccionado del perfil de estudio vinculado a la cuenta.",
        tuple((level, level) for level in ("A1", "A2", "B1", "B2", "C1", "C2")),
    ),
    RuleCapability(
        "CLASSES_COMPLETED",
        "Clases completadas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de clases de práctica completadas dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "ACTIVE_STUDY_DAYS",
        "Días con actividad",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de días distintos con al menos una clase completada dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "MIN_CLASSES_PER_ACTIVE_DAY",
        "Mínimo de clases por día activo",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Mínimo de clases completadas en cada día en el que hubo actividad dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "AVERAGE_CLASSES_PER_ACTIVE_DAY",
        "Promedio de clases por día activo",
        "number",
        ("EQ", "GTE", "LTE"),
        "Promedio de clases completadas por cada día con actividad dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "STUDY_STREAK_DAYS",
        "Racha de estudio",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de días consecutivos con clases completadas, terminando hoy o ayer.",
    ),
)

RULES_BY_KEY = {item.key: item for item in RULE_CAPABILITIES}

TRIGGER_CAPABILITIES = (
    {
        "key": CampaignTrigger.FIRST_LOGIN.value,
        "label": "Primer login",
        "available": True,
        "description": "Se evalúa al primer ingreso de una cuenta ocurrido mientras la campaña está activa.",
    },
    {
        "key": CampaignTrigger.LOGIN.value,
        "label": "Cada login",
        "available": True,
        "description": "Se evalúa cada vez que la cuenta inicia sesión.",
    },
    {
        "key": CampaignTrigger.SCHEDULED.value,
        "label": "Programada / batch",
        "available": False,
        "description": "Reservado para el scheduler de T-059.",
    },
)

ACTION_CAPABILITIES = (
    {
        "key": "GRANT_BENEFIT",
        "label": "Otorgar beneficio",
        "available": True,
        "requiresBenefit": True,
        "description": "Otorga un Benefit existente reutilizando el motor actual.",
    },
    {
        "key": "SEND_NOTIFICATION",
        "label": "Enviar notificación",
        "available": False,
        "requiresBenefit": False,
        "description": "Reservado para la evolución coordinada con T-051.",
    },
    {
        "key": "GENERATE_REPORT",
        "label": "Generar reporte",
        "available": False,
        "requiresBenefit": False,
        "description": "Reservado para T-059 y campañas corporativas.",
    },
    {
        "key": "CREATE_INVITATION",
        "label": "Crear invitación",
        "available": False,
        "requiresBenefit": False,
        "description": "Reservado para una integración futura con el motor de invitaciones.",
    },
    {
        "key": "APPLY_DISCOUNT",
        "label": "Aplicar descuento",
        "available": False,
        "requiresBenefit": False,
        "description": "No disponible hasta que exista un dominio real de pagos/promociones.",
    },
)

DELIVERY_CAPABILITIES = tuple(
    {
        "key": item.value,
        "label": {
            CampaignNotification.NONE: "Sin notificación",
            CampaignNotification.IN_APP: "En pantalla",
            CampaignNotification.EMAIL: "Email",
            CampaignNotification.IN_APP_EMAIL: "Pantalla + email",
        }[item],
        "available": True,
        "description": (
            "La campaña puede encolarlo como PENDING; el envío real depende de T-051."
            if item in {CampaignNotification.EMAIL, CampaignNotification.IN_APP_EMAIL}
            else ""
        ),
    }
    for item in CampaignNotification
)


def available_trigger_values() -> set[str]:
    return {item["key"] for item in TRIGGER_CAPABILITIES if item["available"]}


def available_action_values() -> set[str]:
    return {item["key"] for item in ACTION_CAPABILITIES if item["available"]}


def capabilities_payload() -> dict:
    return {
        "rules": [item.payload() for item in RULE_CAPABILITIES],
        "triggers": list(TRIGGER_CAPABILITIES),
        "actions": list(ACTION_CAPABILITIES),
        "deliveries": list(DELIVERY_CAPABILITIES),
    }


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def validate_rule(field: str, operator: str, value: Any, window_days: Any = None) -> dict:
    field = field.strip().upper()
    operator = operator.strip().upper()
    capability = RULES_BY_KEY.get(field)
    if capability is None or not capability.available or operator not in capability.operators:
        raise CampaignCapabilityError(f"Condición no soportada: {field} {operator}.")

    normalized_window: int | None = None
    if capability.requires_window:
        try:
            normalized_window = int(window_days)
        except (TypeError, ValueError):
            raise CampaignCapabilityError(f"{field} requiere una ventana en días.")
        if not capability.window_min_days <= normalized_window <= capability.window_max_days:
            raise CampaignCapabilityError(
                f"{field} requiere una ventana entre {capability.window_min_days} y "
                f"{capability.window_max_days} días."
            )

    if capability.value_type == "boolean":
        if not isinstance(value, bool):
            raise CampaignCapabilityError(f"{field} requiere true/false.")
    elif capability.value_type == "integer":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise CampaignCapabilityError(f"{field} requiere un entero.")
        if value < 0:
            raise CampaignCapabilityError(f"{field} no puede ser negativo.")
    elif capability.value_type == "number":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise CampaignCapabilityError(f"{field} requiere un número.")
        if value < 0:
            raise CampaignCapabilityError(f"{field} no puede ser negativo.")
    elif capability.value_type == "datetime":
        try:
            value = _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00"))).isoformat()
        except (TypeError, ValueError):
            raise CampaignCapabilityError(f"{field} requiere una fecha válida.")
    elif capability.value_type == "enum":
        value = str(value).upper()
        allowed = {option for option, _ in capability.options}
        if value not in allowed:
            raise CampaignCapabilityError(f"Valor inválido para {field}.")
    elif capability.value_type == "string":
        value = str(value).strip()
        if field == "EMAIL_DOMAIN":
            value = value.lower().lstrip("@")
            if not value or "." not in value:
                raise CampaignCapabilityError("Dominio de email inválido.")
        elif not value:
            raise CampaignCapabilityError(f"{field} no puede quedar vacío.")

    result = {"field": field, "operator": operator, "value": value}
    if normalized_window is not None:
        result["windowDays"] = normalized_window
    return result


def ai_capabilities_text() -> str:
    lines = ["Capacidades reales disponibles:"]
    for rule in RULE_CAPABILITIES:
        ops = "/".join(rule.operators)
        options = ""
        if rule.options:
            options = " valores=" + ",".join(value for value, _ in rule.options)
        window = "; requiere windowDays" if rule.requires_window else ""
        lines.append(
            f"- {rule.key}: {ops}; tipo={rule.value_type}{options}{window}. {rule.description}"
        )
    lines.append(
        "- Triggers disponibles ahora: "
        + ", ".join(item["key"] for item in TRIGGER_CAPABILITIES if item["available"])
        + ". SCHEDULED queda reservado para T-059."
    )
    lines.append("- Acción disponible ahora: GRANT_BENEFIT. No inventes otras acciones.")
    lines.append(
        "- Delivery: NONE/IN_APP están operativos; EMAIL/IN_APP_EMAIL pueden quedar en cola, "
        "pero el envío real depende de T-051."
    )
    return "\n".join(lines)
