"""Catálogo único de capacidades del motor de campañas (T-065).

Backend, constructor manual y asistente IA consumen esta misma definición para evitar que
condiciones/triggers/acciones se dupliquen en varios lugares.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.campaigns.models import CampaignNotification, CampaignTrigger
from app.curriculum.service import available_levels, get_level


class CampaignCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class RuleFilterCapability:
    key: str
    label: str
    value_type: str
    options: tuple[tuple[str, str], ...] = ()
    required: bool = False

    def payload(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "valueType": self.value_type,
            "options": [{"value": value, "label": label} for value, label in self.options],
            "required": self.required,
        }


@dataclass(frozen=True)
class RuleCapability:
    key: str
    label: str
    value_type: str
    operators: tuple[str, ...]
    description: str
    options: tuple[tuple[str, str], ...] = ()
    subject_label: str | None = None
    subject_options: tuple[tuple[str, str], ...] = ()
    filters: tuple[RuleFilterCapability, ...] = ()
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
            "subjectLabel": self.subject_label,
            "subjectOptions": [
                {"value": value, "label": label} for value, label in self.subject_options
            ],
            "filters": [item.payload() for item in self.filters],
            "available": self.available,
            "requiresWindow": self.requires_window,
            "windowMinDays": self.window_min_days if self.requires_window else None,
            "windowMaxDays": self.window_max_days if self.requires_window else None,
        }


ABILITY_OPTIONS = (
    ("GRAMMAR", "Grammar"),
    ("VOCABULARY", "Vocabulary"),
    ("LISTENING", "Listening"),
    ("SPEAKING", "Speaking"),
    ("PRONUNCIATION", "Pronunciation"),
    ("READING", "Reading"),
    ("WRITING", "Writing"),
)

PROGRESS_STATUS_OPTIONS = (
    ("NOT_STARTED", "Sin empezar"),
    ("LEARNING", "Aprendiendo"),
    ("MASTERED", "Dominada"),
    ("NEEDS_REVIEW", "Necesita repaso"),
)

PROGRESS_TREND_OPTIONS = (
    ("UP", "Mejorando"),
    ("STABLE", "Estable"),
    ("DOWN", "Bajando"),
)

AI_OWNER_FILTER_OPTIONS = (
    ("ACCOUNT", "Propias keys (cuenta)"),
    ("PLATFORM", "IA de plataforma"),
    ("ORGANIZATION", "IA de organización"),
)

AI_ERROR_FILTER_OPTIONS = (
    ("CREDENTIAL_OR_QUOTA", "Credencial inválida o cuota excedida"),
    ("INVALID_CREDENTIALS", "Credenciales inválidas"),
    ("QUOTA_EXCEEDED", "Cuota excedida"),
    ("RATE_LIMITED", "Rate limit"),
    ("PROVIDER_DOWN", "Proveedor caído"),
    ("NETWORK_ERROR", "Error de red"),
    ("UNKNOWN_ERROR", "Error desconocido"),
)

AI_FAILURE_FILTERS = (
    RuleFilterCapability(
        "ownerType",
        "Origen de IA",
        "enum",
        AI_OWNER_FILTER_OPTIONS,
    ),
    RuleFilterCapability(
        "errorCode",
        "Código de error",
        "enum",
        AI_ERROR_FILTER_OPTIONS,
    ),
    RuleFilterCapability(
        "operation",
        "Operación",
        "string",
    ),
)


def _skill_options() -> tuple[tuple[str, str], ...]:
    found: dict[str, str] = {}
    for level in available_levels():
        curriculum = get_level(level)
        if curriculum is None:
            continue
        for skill in curriculum.skills:
            found.setdefault(
                skill.key,
                f"{level} · {skill.area_name} · {skill.topic_name} · {skill.name}",
            )
    return tuple(sorted(found.items(), key=lambda item: item[1]))


SKILL_OPTIONS = _skill_options()


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
        "ACCOUNT_EMAIL",
        "Email exacto",
        "string",
        ("EQ",),
        "Cuenta concreta identificada por su email. Útil para compensaciones o gestiones manuales.",
    ),
    RuleCapability(
        "EMAIL_DOMAIN",
        "Dominio de email",
        "string",
        ("EQ",),
        "Dominio del correo de la cuenta, sin @.",
    ),
    RuleCapability(
        "DOCUMENT_COUNTRY",
        "País documental",
        "string",
        ("EQ",),
        "Código ISO de 2 letras del país del documento declarado en la cuenta. No representa residencia ni ubicación actual.",
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
        "DAYS_UNTIL_SERVICE_EXPIRES",
        "Días hasta vencimiento de servicio",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días restantes hasta el vencimiento del servicio otorgado vigente. Requiere un vencimiento real.",
    ),
    RuleCapability(
        "SUBSCRIPTION_ORIGIN",
        "Origen de la suscripción vigente",
        "enum",
        ("EQ",),
        "Origen real del servicio otorgado que rige actualmente.",
        (
            ("MANUAL", "Manual"),
            ("CAMPAIGN", "Campaña"),
            ("INVITATION", "Invitación"),
            ("PAYMENT", "Pago"),
        ),
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
        "SKILL_STATUS",
        "Estado de skill",
        "enum",
        ("EQ",),
        "Estado ya calculado por el dominio de progreso para una skill concreta.",
        PROGRESS_STATUS_OPTIONS,
        subject_label="Skill",
        subject_options=SKILL_OPTIONS,
    ),
    RuleCapability(
        "SKILL_SCORE",
        "Puntaje de skill",
        "number",
        ("EQ", "GTE", "LTE"),
        "Puntaje ya calculado por el dominio de progreso para una skill concreta.",
        subject_label="Skill",
        subject_options=SKILL_OPTIONS,
    ),
    RuleCapability(
        "SKILL_TREND",
        "Tendencia de skill",
        "enum",
        ("EQ",),
        "Tendencia ya calculada por el dominio de progreso para una skill concreta.",
        PROGRESS_TREND_OPTIONS,
        subject_label="Skill",
        subject_options=SKILL_OPTIONS,
    ),
    RuleCapability(
        "ABILITY_STATUS",
        "Estado de habilidad",
        "enum",
        ("EQ",),
        "Estado del progreso agregado de una habilidad del idioma.",
        PROGRESS_STATUS_OPTIONS,
        subject_label="Habilidad",
        subject_options=ABILITY_OPTIONS,
    ),
    RuleCapability(
        "ABILITY_SCORE",
        "Puntaje de habilidad",
        "number",
        ("EQ", "GTE", "LTE"),
        "Puntaje agregado de una habilidad del idioma calculado por el dominio de progreso.",
        subject_label="Habilidad",
        subject_options=ABILITY_OPTIONS,
    ),
    RuleCapability(
        "ABILITY_TREND",
        "Tendencia de habilidad",
        "enum",
        ("EQ",),
        "Tendencia agregada de una habilidad del idioma calculada por el dominio de progreso.",
        PROGRESS_TREND_OPTIONS,
        subject_label="Habilidad",
        subject_options=ABILITY_OPTIONS,
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
        "CLASSES_GENERATED",
        "Clases generadas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de clases de práctica generadas correctamente dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "CLASSES_STARTED",
        "Clases iniciadas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de clases de práctica en las que hubo interacción real del alumno dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "CLASSES_GENERATION_FAILED",
        "Clases con generación fallida",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de clases de práctica cuya generación falló dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "CLASSES_NOT_COMPLETED",
        "Clases generadas no completadas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de clases generadas dentro de una ventana de N días que actualmente no están completadas.",
        requires_window=True,
    ),
    RuleCapability(
        "EXAMS_COMPLETED",
        "Exámenes completados",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de exámenes de nivel completados dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "EXAMS_PASSED",
        "Exámenes aprobados",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de exámenes de nivel aprobados dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "EXAMS_FAILED",
        "Exámenes desaprobados",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de exámenes de nivel desaprobados dentro de una ventana de N días.",
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
        "AVERAGE_CLASSES_PER_DAY",
        "Promedio de clases por día",
        "number",
        ("EQ", "GTE", "LTE"),
        "Promedio diario real dentro de una ventana de N días; los días sin clases cuentan como cero.",
        requires_window=True,
    ),
    RuleCapability(
        "STUDY_STREAK_DAYS",
        "Racha de estudio",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de días consecutivos con clases completadas, terminando hoy o ayer.",
    ),
    RuleCapability(
        "LAST_ENDED_STREAK_DAYS",
        "Última racha terminada",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de días consecutivos de la racha más reciente que ya fue interrumpida.",
    ),
    RuleCapability(
        "DAYS_SINCE_STREAK_BROKEN",
        "Días desde que se cortó la última racha",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días completos desde el primer día sin actividad que interrumpió la última racha terminada.",
    ),
    RuleCapability(
        "APPEALS_COUNT",
        "Apelaciones realizadas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad real de correcciones apeladas dentro de una ventana de N días.",
        requires_window=True,
    ),
    RuleCapability(
        "SPEAKING_RESPONSES",
        "Respuestas habladas",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad histórica de respuestas efectivamente enviadas en modalidad SPEAK.",
    ),
    RuleCapability(
        "LISTENING_RESPONSES",
        "Respuestas a ejercicios escuchados",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad histórica de respuestas enviadas a ejercicios presentados en modalidad LISTEN.",
    ),
    RuleCapability(
        "AI_FAILURES_COUNT",
        "Fallos de IA",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Cantidad de llamadas de IA fallidas dentro de una ventana, con filtros opcionales por origen, código y operación.",
        filters=AI_FAILURE_FILTERS,
        requires_window=True,
    ),
    RuleCapability(
        "DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS",
        "Días con BYOK configurado sin uso exitoso",
        "integer",
        ("EQ", "GTE", "LTE"),
        "Días desde la primera conexión propia activa cuando ninguna conexión propia activa logró todavía un uso real exitoso. Los health checks no cuentan como activación.",
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


def validate_rule(
    field: str,
    operator: str,
    value: Any,
    window_days: Any = None,
    subject: Any = None,
    filters: Any = None,
) -> dict:
    field = field.strip().upper()
    operator = operator.strip().upper()
    capability = RULES_BY_KEY.get(field)
    if capability is None or not capability.available or operator not in capability.operators:
        raise CampaignCapabilityError(f"Condición no soportada: {field} {operator}.")

    normalized_subject: str | None = None
    if capability.subject_options:
        raw_subject = str(subject or "").strip()
        allowed_subjects = {option.lower(): option for option, _ in capability.subject_options}
        normalized_subject = allowed_subjects.get(raw_subject.lower())
        if normalized_subject is None:
            raise CampaignCapabilityError(f"{field} requiere seleccionar {capability.subject_label or 'un sujeto'} válido.")

    raw_filters = filters if isinstance(filters, dict) else {}
    filter_capabilities = {item.key: item for item in capability.filters}
    unknown_filters = set(raw_filters) - set(filter_capabilities)
    if unknown_filters:
        raise CampaignCapabilityError(
            f"Filtro no soportado para {field}: {sorted(unknown_filters)[0]}."
        )
    normalized_filters: dict[str, str] = {}
    for filter_key, filter_capability in filter_capabilities.items():
        raw_filter = raw_filters.get(filter_key)
        if raw_filter in (None, ""):
            if filter_capability.required:
                raise CampaignCapabilityError(
                    f"{field} requiere el filtro {filter_capability.label}."
                )
            continue
        filter_value = str(raw_filter).strip()
        if filter_capability.value_type == "enum":
            filter_value = filter_value.upper()
            allowed_values = {option for option, _ in filter_capability.options}
            if filter_value not in allowed_values:
                raise CampaignCapabilityError(
                    f"Valor inválido para el filtro {filter_capability.label}."
                )
        elif filter_capability.value_type == "string":
            if not filter_value:
                raise CampaignCapabilityError(
                    f"El filtro {filter_capability.label} no puede quedar vacío."
                )
            if filter_key == "operation":
                filter_value = filter_value.lower()
        normalized_filters[filter_key] = filter_value

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
        elif field == "ACCOUNT_EMAIL":
            value = value.lower()
            if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
                raise CampaignCapabilityError("Email inválido.")
        elif field == "DOCUMENT_COUNTRY":
            value = value.upper()
            if len(value) != 2 or not value.isalpha():
                raise CampaignCapabilityError("País documental inválido: usá un código ISO de 2 letras.")
        elif not value:
            raise CampaignCapabilityError(f"{field} no puede quedar vacío.")

    result = {"field": field, "operator": operator, "value": value}
    if normalized_subject is not None:
        result["subject"] = normalized_subject
    if normalized_filters:
        result["filters"] = normalized_filters
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
        subject = (
            f"; requiere subject ({rule.subject_label})"
            if rule.subject_options
            else ""
        )
        filters = ""
        if rule.filters:
            filter_parts = []
            for item in rule.filters:
                if item.options:
                    filter_parts.append(
                        f"{item.key}=" + "/".join(value for value, _ in item.options)
                    )
                else:
                    filter_parts.append(f"{item.key}=texto")
            filters = "; filtros opcionales: " + ", ".join(filter_parts)
        lines.append(
            f"- {rule.key}: {ops}; tipo={rule.value_type}{options}{subject}{filters}{window}. {rule.description}"
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
