"""Portal del PLATFORM_OWNER: constructor y control de campañas (T-004, etapa 2)."""

from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.ai.service import NoAIAvailable, run_platform_json_task
from app.ai.usage import AIUsageContext
from app.benefits.models import Benefit
from app.benefits.service import benefit_duration
from app.campaigns.capabilities import (
    CampaignCapabilityError,
    ai_capabilities_text,
    available_action_values,
    available_trigger_values,
    capabilities_payload,
    validate_rule,
)
from app.campaigns.models import (
    Campaign,
    CampaignAction,
    CampaignGrant,
    CampaignNotification,
    CampaignStatus,
    CampaignTrigger,
)
from app.campaigns.service import preview_audience
from app.core.deps import DbSession
from app.platform.api import PlatformOwner
from app.subscriptions.models import Plan, ServiceLinkType

router = APIRouter(prefix="/platform/campaigns", tags=["platform"])

class CampaignRuleIn(BaseModel):
    field: str = Field(min_length=2, max_length=60)
    subject: str | None = Field(default=None, max_length=200)
    filters: dict[str, str] = Field(default_factory=dict)
    operator: str = Field(default="EQ", min_length=2, max_length=12)
    value: Any
    windowDays: int | None = Field(default=None, ge=1, le=3650)


class CampaignAssistIn(BaseModel):
    description: str = Field(min_length=8, max_length=2000)


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    benefitId: int
    action: CampaignAction = CampaignAction.GRANT_BENEFIT
    actionConfig: dict[str, Any] | None = None
    trigger: CampaignTrigger = CampaignTrigger.FIRST_LOGIN
    rules: list[CampaignRuleIn] = Field(default_factory=list, max_length=20)
    priority: int = Field(default=100, ge=1, le=10000)
    stackable: bool = False
    maxRecipients: int | None = Field(default=None, ge=1, le=10_000_000)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    notification: CampaignNotification = CampaignNotification.IN_APP
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_window(self):
        if self.startsAt and self.endsAt and self.endsAt <= self.startsAt:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio.")
        if self.action.value not in available_action_values():
            raise ValueError("La acción elegida todavía no está disponible.")
        return self


CAMPAIGN_ASSIST_SYSTEM = """Sos un asistente que transforma una intención comercial en un borrador
de campaña para Librería Inglés. No inventes capacidades que el motor no tenga.

Devolvé SOLO JSON con esta forma:
{
  "draft": {
    "name": "nombre claro",
    "benefitId": 123 o null,
    "action": "acción disponible",
    "actionConfig": {},
    "trigger": "trigger disponible",
    "rules": [{"field":"...", "subject": null o "...", "filters": {}, "operator":"...", "value":..., "windowDays": null o número}],
    "priority": 100,
    "stackable": false,
    "maxRecipients": null,
    "startsAt": null o ISO-8601,
    "endsAt": null o ISO-8601,
    "notification": "NONE" | "IN_APP" | "EMAIL" | "IN_APP_EMAIL",
    "message": null o texto
  },
  "requirements": [
    {
      "text": "requisito material expresado por el usuario",
      "kind": "RULE" | "TRIGGER" | "ACTION" | "DELIVERY" | "BENEFIT" | "LIMIT" | "DATE",
      "status": "REPRESENTED" | "UNSUPPORTED",
      "capability": "clave exacta del catálogo o null"
    }
  ],
  "warnings": ["advertencia informativa que no cambia la intención"],
  "summary": "resumen breve de lo interpretado"
}

requirements es obligatorio y debe enumerar TODOS los requisitos materiales de la intención:
audiencia/condiciones, trigger, acción, delivery, beneficio, límites y fechas que el usuario haya
pedido explícitamente. Un pedido genérico de "dar un beneficio" se representa con ACTION=GRANT_BENEFIT;
usá kind=BENEFIT solo cuando el usuario exija un beneficio concreto que deba quedar identificado.
Si un requisito no puede expresarse exactamente con el catálogo actual,
marcalo UNSUPPORTED y no lo sustituyas por otra capacidad parecida. Un requisito REPRESENTED debe
apuntar mediante capability a la capacidad exacta que realmente aparece en draft. No ocultes una
limitación solo para producir un borrador válido.

El motor actual ejecuta GRANT_BENEFIT sobre un beneficio existente. No inventes descuentos,
precios, pagos, renovaciones ni otras acciones todavía no disponibles. Si una intención requiere
una capacidad inexistente, explicalo en warnings y no la reemplaces por otra condición parecida.

Las capacidades que exponen subjectOptions requieren un subject exacto del catálogo.
Por ejemplo, ABILITY_STATUS con subject=WRITING y value=NEEDS_REVIEW representa Writing en estado de repaso.
No inventes subjects ni uses el nombre visible cuando el catálogo provee una clave.

Las capacidades que exponen filters aceptan únicamente esos filtros y sus valores permitidos.
AI_FAILURES_COUNT puede combinar ownerType, errorCode y operation en la MISMA regla para que el conteo
corresponda exactamente al mismo conjunto de eventos. Para “cuota o credencial” usá
errorCode=CREDENTIAL_OR_QUOTA. No reemplaces un filtro combinado por varias métricas independientes.

PRIORIDAD y CONVIVENCIA:
- priority solo ordena campañas que resultan elegibles en la misma evaluación; un número menor se intenta primero.
- stackable=false es el valor conservador por defecto.
- stackable=true significa únicamente que la campaña puede convivir con otra campaña elegible en ESA MISMA evaluación.
- stackable NO significa ignorar campañas recibidas anteriormente, frequency caps ni supresiones históricas.
- Si el usuario pide excluir por campañas/beneficios recibidos previamente y el catálogo no ofrece esa condición,
  declaralo UNSUPPORTED. Nunca lo sustituyas por stackable=false ni por priority.

Para métricas de estudio usá las capacidades del catálogo:
- CLASSES_COMPLETED cuenta clases completadas dentro de windowDays.
- ACTIVE_STUDY_DAYS cuenta días distintos con actividad dentro de windowDays.
- MIN_CLASSES_PER_ACTIVE_DAY mide el mínimo de clases de cada día en que hubo actividad.
- AVERAGE_CLASSES_PER_ACTIVE_DAY mide el promedio solo entre los días donde hubo actividad.
- AVERAGE_CLASSES_PER_DAY mide el promedio real de toda la ventana: los días sin estudiar cuentan como cero.
- STUDY_STREAK_DAYS mide la racha consecutiva actual y no usa windowDays.
Si el usuario pide "promedio de N clases por día/diarias", usá AVERAGE_CLASSES_PER_DAY >= N.
Si pide "N clases todos los días durante K días", combiná MIN_CLASSES_PER_ACTIVE_DAY >= N con
ACTIVE_STUDY_DAYS >= K, ambas con windowDays=K. No confundas "promedio diario" con "mínimo todos
los días": son criterios distintos. Si pide una frecuencia/promedio y no informa período, usá
windowDays=30 y agregá una advertencia clara para que revise esa ventana.

Elegí benefitId únicamente entre los beneficios provistos y solo si la intención lo deja claro;
si no, devolvé null. El resultado es siempre un BORRADOR: nunca actives ni guardes una campaña."""



def _append_blocking_issue(blocking_issues: list[str], message: str) -> None:
    message = message.strip()[:400]
    if message and message not in blocking_issues and len(blocking_issues) < 12:
        blocking_issues.append(message)


def _assist_datetime(
    value,
    warnings: list[str],
    blocking_issues: list[str],
    label: str,
) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        warnings.append(f"La IA propuso una {label} inválida; se dejó vacía.")
        _append_blocking_issue(
            blocking_issues,
            f"La {label} pedida no pudo representarse con una fecha válida.",
        )
        return None
    return _as_utc(parsed).isoformat()


def _normalize_assist(data: dict, benefit_ids: set[int]) -> dict:
    raw = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    warnings = [
        str(item)[:300]
        for item in (data.get("warnings") or [])
        if isinstance(item, (str, int, float))
    ][:8]
    blocking_issues: list[str] = []

    benefit_id = raw.get("benefitId")
    try:
        benefit_id = int(benefit_id) if benefit_id is not None else None
    except (TypeError, ValueError):
        benefit_id = None
        _append_blocking_issue(
            blocking_issues,
            "El beneficio propuesto por IA no pudo validarse.",
        )
    if benefit_id is not None and benefit_id not in benefit_ids:
        warnings.append("La IA eligió un beneficio no disponible; seleccioná uno manualmente.")
        _append_blocking_issue(
            blocking_issues,
            "El beneficio elegido no pertenece al catálogo activo.",
        )
        benefit_id = None

    action = str(raw.get("action") or CampaignAction.GRANT_BENEFIT.value).upper()
    if action not in available_action_values():
        warnings.append("La acción propuesta todavía no está disponible; se conservó solo la parte representable.")
        _append_blocking_issue(
            blocking_issues,
            f"La acción {action} no está disponible en el motor actual.",
        )
        action = CampaignAction.GRANT_BENEFIT.value
    trigger = str(raw.get("trigger") or "LOGIN").upper()
    if trigger not in available_trigger_values():
        warnings.append("El disparador propuesto no está disponible; se usó Cada login solo como referencia editable.")
        _append_blocking_issue(
            blocking_issues,
            f"El disparador {trigger} no está disponible en el motor actual.",
        )
        trigger = "LOGIN"

    rules: list[dict] = []
    for item in raw.get("rules") or []:
        if not isinstance(item, dict):
            _append_blocking_issue(
                blocking_issues,
                "La IA devolvió una condición con formato inválido.",
            )
            continue
        if len(rules) >= 20:
            _append_blocking_issue(
                blocking_issues,
                "La IA propuso más de 20 condiciones; algunas quedarían fuera del borrador.",
            )
            continue
        try:
            rules.append(_validate_rule(CampaignRuleIn.model_validate(item)))
        except (HTTPException, ValueError, TypeError):
            field = str(item.get("field") or "desconocida").upper()
            warnings.append("Se omitió una condición propuesta por IA porque no es compatible.")
            _append_blocking_issue(
                blocking_issues,
                f"La condición {field} propuesta por IA no puede representarse con el catálogo actual.",
            )
    if not any(rule["field"] == "ACCOUNT_TYPE" for rule in rules):
        rules.insert(0, {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"})

    try:
        priority = max(1, min(10000, int(raw.get("priority") or 100)))
    except (TypeError, ValueError):
        priority = 100

    max_recipients = raw.get("maxRecipients")
    if max_recipients in (None, ""):
        max_recipients = None
    else:
        try:
            max_recipients = max(1, min(10_000_000, int(max_recipients)))
        except (TypeError, ValueError):
            max_recipients = None
            warnings.append("El máximo de beneficiarios propuesto no era válido; se dejó sin límite.")
            _append_blocking_issue(
                blocking_issues,
                "El límite de beneficiarios pedido no pudo representarse de forma válida.",
            )

    starts_at = _assist_datetime(
        raw.get("startsAt"), warnings, blocking_issues, "fecha de inicio"
    )
    ends_at = _assist_datetime(
        raw.get("endsAt"), warnings, blocking_issues, "fecha de fin"
    )
    if starts_at and ends_at and datetime.fromisoformat(ends_at) <= datetime.fromisoformat(starts_at):
        ends_at = None
        warnings.append("La fecha de fin no era posterior al inicio; se dejó vacía.")
        _append_blocking_issue(
            blocking_issues,
            "La ventana temporal propuesta es inválida.",
        )

    notification = str(raw.get("notification") or "IN_APP").upper()
    allowed_notifications = {item.value for item in CampaignNotification}
    if notification not in allowed_notifications:
        _append_blocking_issue(
            blocking_issues,
            f"El delivery {notification} no está disponible.",
        )
        notification = "IN_APP"

    name = str(raw.get("name") or "Campaña sugerida por IA").strip()[:120]
    if len(name) < 2:
        name = "Campaña sugerida por IA"
    message = raw.get("message")
    message = str(message).strip()[:500] if message else None

    return {
        "draft": {
            "name": name,
            "benefitId": benefit_id,
            "action": action,
            "actionConfig": raw.get("actionConfig") if isinstance(raw.get("actionConfig"), dict) else {},
            "trigger": trigger,
            "rules": rules,
            "priority": priority,
            "stackable": bool(raw.get("stackable")) if isinstance(raw.get("stackable"), bool) else False,
            "maxRecipients": max_recipients,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "notification": notification,
            "message": message,
        },
        "requirements": [],
        "warnings": warnings,
        "blockingIssues": blocking_issues,
        "executable": False,
        "summary": str(data.get("summary") or "Borrador generado por IA. Revisalo antes de guardar.")[:500],
    }


def _specific_benefit_requested(description: str, benefit_names: set[str]) -> bool:
    lower = description.lower()
    if any(name.lower() in lower for name in benefit_names if name.strip()):
        return True
    if "beneficio" not in lower:
        return False
    return bool(
        re.search(
            r"(?:exactamente|exacto|espec[ií]fico|llamado|denominado)\s+(?:el\s+)?beneficio"
            r"|beneficio\s+(?:exacto|espec[ií]fico|llamado|denominado|[\"“'])",
            lower,
        )
    )


def _apply_requirement_coverage(
    data: dict,
    normalized: dict,
    *,
    description: str = "",
    benefit_names: set[str] | None = None,
) -> dict:
    """Verifica que cada requisito material declarado por IA exista realmente en el draft."""
    raw_requirements = data.get("requirements")
    blocking_issues = normalized["blockingIssues"]
    draft = normalized["draft"]
    catalog = capabilities_payload()
    available_rules = {
        item["key"] for item in catalog["rules"] if item.get("available")
    }
    available_triggers = {
        item["key"] for item in catalog["triggers"] if item.get("available")
    }
    available_actions = {
        item["key"] for item in catalog["actions"] if item.get("available")
    }
    available_deliveries = {
        item["key"] for item in catalog["deliveries"] if item.get("available")
    }
    specific_benefit_requested = _specific_benefit_requested(
        description,
        benefit_names or set(),
    )

    if not isinstance(raw_requirements, list) or not raw_requirements:
        _append_blocking_issue(
            blocking_issues,
            "La IA no declaró la cobertura de requisitos de la intención; el borrador no puede considerarse completo.",
        )
        normalized["executable"] = False
        return normalized

    requirements: list[dict] = []
    rule_fields = {rule.get("field") for rule in draft["rules"]}
    allowed_kinds = {
        "RULE",
        "TRIGGER",
        "ACTION",
        "DELIVERY",
        "BENEFIT",
        "LIMIT",
        "DATE",
    }

    for raw in raw_requirements[:30]:
        if not isinstance(raw, dict):
            _append_blocking_issue(
                blocking_issues,
                "La IA devolvió un requisito de cobertura inválido.",
            )
            continue

        text = str(raw.get("text") or "").strip()[:300]
        kind = str(raw.get("kind") or "").strip().upper()
        status_value = str(raw.get("status") or "").strip().upper()
        capability_raw = raw.get("capability")
        capability = (
            str(capability_raw).strip().upper()
            if capability_raw not in (None, "")
            else None
        )
        verified = False
        reason = ""

        if not text or kind not in allowed_kinds or status_value not in {"REPRESENTED", "UNSUPPORTED"}:
            reason = "Declaración de requisito inválida."
            _append_blocking_issue(
                blocking_issues,
                "La IA devolvió una declaración de cobertura inválida; revisá la intención.",
            )
        elif status_value == "UNSUPPORTED":
            if (
                kind == "BENEFIT"
                and not specific_benefit_requested
                and draft["action"] == CampaignAction.GRANT_BENEFIT.value
            ):
                # "Dar un beneficio" ya está representado por GRANT_BENEFIT. Que todavía
                # no se haya elegido benefitId es un dato normal del formulario, no una
                # pérdida semántica de la intención.
                status_value = "REPRESENTED"
                capability = CampaignAction.GRANT_BENEFIT.value
                verified = True
                reason = "Beneficio genérico representado por GRANT_BENEFIT; se selecciona en el formulario."
            else:
                reason = "El requisito no tiene una capacidad exacta disponible."
                _append_blocking_issue(
                    blocking_issues,
                    f"Requisito no soportado: {text}",
                )
        elif kind == "RULE":
            verified = capability in available_rules and capability in rule_fields
            reason = "" if verified else "La condición declarada no está presente en el draft."
        elif kind == "TRIGGER":
            verified = capability in available_triggers and capability == draft["trigger"]
            reason = "" if verified else "El trigger declarado no coincide con el draft."
        elif kind == "ACTION":
            verified = capability in available_actions and capability == draft["action"]
            reason = "" if verified else "La acción declarada no coincide con una acción disponible."
        elif kind == "DELIVERY":
            verified = capability in available_deliveries and capability == draft["notification"]
            reason = "" if verified else "El delivery declarado no coincide con el draft."
        elif kind == "BENEFIT":
            if specific_benefit_requested:
                verified = draft["benefitId"] is not None
                reason = "" if verified else "El requisito exige un Benefit concreto y el draft no tiene uno válido."
            else:
                verified = draft["action"] == CampaignAction.GRANT_BENEFIT.value
                reason = (
                    ""
                    if verified
                    else "El pedido genérico de beneficio no quedó representado por GRANT_BENEFIT."
                )
        elif kind == "LIMIT":
            verified = capability == "MAX_RECIPIENTS" and draft["maxRecipients"] is not None
            reason = "" if verified else "El límite declarado no está representado en el draft."
        elif kind == "DATE":
            verified = (
                capability == "STARTS_AT" and draft["startsAt"] is not None
            ) or (
                capability == "ENDS_AT" and draft["endsAt"] is not None
            )
            reason = "" if verified else "La fecha declarada no está representada en el draft."

        if status_value == "REPRESENTED" and not verified:
            _append_blocking_issue(
                blocking_issues,
                f"Requisito declarado como representado pero no verificado: {text}",
            )

        requirements.append(
            {
                "text": text or "Requisito sin descripción",
                "kind": kind or "UNKNOWN",
                "status": status_value or "INVALID",
                "capability": capability,
                "verified": verified,
                "reason": reason or None,
            }
        )

    normalized["requirements"] = requirements
    normalized["executable"] = not blocking_issues
    return normalized


def _apply_description_capability_guards(description: str, normalized: dict) -> dict:
    """Evita que una buena intención de la IA se convierta en una regla de negocio falsa."""
    lower = description.lower()
    warnings = normalized["warnings"]
    blocking_issues = normalized["blockingIssues"]
    rules = normalized["draft"]["rules"]

    mentions_discount = "%" in description or any(
        word in lower for word in ("descuento", "bonific", "rebaja", "precio")
    )
    if mentions_discount:
        # Un descuento nunca se sustituye por un Benefit. Si además se pidió un Benefit real,
        # se conserva esa parte representable, pero el draft completo queda bloqueado.
        if not any("descuento" in warning.lower() or "precio" in warning.lower() for warning in warnings):
            warnings.append(
                "El motor actual no administra descuentos, precios ni porcentajes; "
                "no se sustituyó el descuento por un beneficio de servicio."
            )
        _append_blocking_issue(
            blocking_issues,
            "La intención requiere un descuento/precio que el motor actual no puede ejecutar.",
        )

    # "Promedio de N clases diarias" debe incluir los días sin actividad en el denominador.
    # Se corrige de forma determinística para no depender de una interpretación variable del LLM.
    mentions_daily_average = (
        "promedio" in lower
        and "clase" in lower
        and any(term in lower for term in ("diaria", "diario", "por día", "por dia", "al día", "al dia"))
    )
    if mentions_daily_average:
        classes_match = re.search(r"(\d+(?:[\.,]\d+)?)\s+clases?", lower)
        if classes_match:
            expected = float(classes_match.group(1).replace(",", "."))
            expected = int(expected) if expected.is_integer() else expected
            window_days = next(
                (
                    int(rule["windowDays"])
                    for rule in rules
                    if rule.get("windowDays") is not None
                    and rule.get("field") in {
                        "MIN_CLASSES_PER_ACTIVE_DAY",
                        "AVERAGE_CLASSES_PER_ACTIVE_DAY",
                        "AVERAGE_CLASSES_PER_DAY",
                        "ACTIVE_STUDY_DAYS",
                    }
                ),
                None,
            )
            if window_days is None:
                window_match = re.search(
                    r"(?:últim(?:os|as)?|ultim(?:os|as)?|durante|por|en)\s+(?:los\s+)?(\d+)\s+d[ií]as",
                    lower,
                )
                window_days = int(window_match.group(1)) if window_match else 30
                if window_match is None and not any("30 días" in warning for warning in warnings):
                    warnings.append(
                        "No se indicó el período del promedio diario; se propusieron 30 días como ventana editable."
                    )
            metric_operator = next(
                (
                    str(rule.get("operator") or "GTE").upper()
                    for rule in rules
                    if rule.get("field")
                    in {
                        "MIN_CLASSES_PER_ACTIVE_DAY",
                        "AVERAGE_CLASSES_PER_ACTIVE_DAY",
                        "AVERAGE_CLASSES_PER_DAY",
                    }
                ),
                None,
            )
            if metric_operator not in {"GTE", "LTE", "EQ"}:
                metric_operator = (
                    "LTE"
                    if any(
                        phrase in lower
                        for phrase in (
                            "como máximo",
                            "como maximo",
                            "máximo",
                            "maximo",
                            "menos de",
                            "no más de",
                            "no mas de",
                        )
                    )
                    else "GTE"
                )
            normalized["draft"]["rules"] = [
                rule
                for rule in rules
                if rule.get("field")
                not in {
                    "MIN_CLASSES_PER_ACTIVE_DAY",
                    "AVERAGE_CLASSES_PER_ACTIVE_DAY",
                    "AVERAGE_CLASSES_PER_DAY",
                }
                and not (
                    rule.get("field") == "ACTIVE_STUDY_DAYS"
                    and rule.get("windowDays") == window_days
                    and rule.get("value") == window_days
                )
            ]
            normalized["draft"]["rules"].append(
                {
                    "field": "AVERAGE_CLASSES_PER_DAY",
                    "operator": metric_operator,
                    "value": expected,
                    "windowDays": window_days,
                }
            )
            rules = normalized["draft"]["rules"]

    unsupported_audience_terms = {
        "reclamo": "El motor todavía no tiene datos de reclamos/soporte para segmentar esta campaña.",
        "queja": "El motor todavía no tiene datos de reclamos/soporte para segmentar esta campaña.",
        "ticket de soporte": "El motor todavía no tiene datos de reclamos/soporte para segmentar esta campaña.",
        "referid": "El motor todavía no registra referidos/invitaciones exitosas como métrica de campaña.",
        "invitó a": "El motor todavía no registra referidos/invitaciones exitosas como métrica de campaña.",
        "invito a": "El motor todavía no registra referidos/invitaciones exitosas como métrica de campaña.",
        "invitaron a": "El motor todavía no registra referidos/invitaciones exitosas como métrica de campaña.",
        "invitar a": "El motor todavía no registra referidos/invitaciones exitosas como métrica de campaña.",
    }
    for term, warning in unsupported_audience_terms.items():
        if term in lower and not any(warning.lower() == item.lower() for item in warnings):
            warnings.append(warning)
            _append_blocking_issue(blocking_issues, warning)
            break

    mentions_payment_tenure = any(
        phrase in lower
        for phrase in (
            "servicio pago",
            "servicio pagado",
            "membresía paga",
            "membresia paga",
            "membresía pagada",
            "membresia pagada",
            "antigüedad de pago",
            "antiguedad de pago",
            "desde que paga",
            "desde que pagó",
            "desde que pago",
            "renovación",
            "renovacion",
            "facturación",
            "facturacion",
        )
    )
    explicitly_account_age = any(
        phrase in lower
        for phrase in ("desde el registro", "desde que se registr", "antigüedad de la cuenta", "antiguedad de la cuenta")
    )
    if mentions_payment_tenure:
        if not explicitly_account_age:
            normalized["draft"]["rules"] = [
                rule for rule in rules if rule.get("field") != "DAYS_SINCE_CREATED"
            ]
        if not any("pago" in warning.lower() or "suscripción" in warning.lower() or "suscripcion" in warning.lower() for warning in warnings):
            warnings.append(
                "Todavía no existe una condición por antigüedad de pago o suscripción; no se la reemplazó por antigüedad de la cuenta."
            )
        _append_blocking_issue(
            blocking_issues,
            "La intención requiere antigüedad de pago/suscripción, una condición todavía inexistente.",
        )

    normalized["warnings"] = warnings[:8]
    normalized["blockingIssues"] = blocking_issues[:12]
    normalized["executable"] = not normalized["blockingIssues"]
    return normalized


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _validate_rule(rule: CampaignRuleIn) -> dict:
    try:
        return validate_rule(
            rule.field,
            rule.operator,
            rule.value,
            rule.windowDays,
            rule.subject,
            rule.filters,
        )
    except CampaignCapabilityError as exc:
        raise HTTPException(422, str(exc)) from exc


def _benefit(db: DbSession, benefit_id: int, *, require_active: bool = False) -> Benefit:
    benefit = db.get(Benefit, benefit_id)
    if benefit is None or benefit.organization_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficio inexistente.")
    plan = db.get(Plan, benefit.plan_id)
    if plan is None or plan.link_type != ServiceLinkType.PERSONAL:
        raise HTTPException(422, "Las campañas corporativas llegan con la etapa de empresas.")
    if require_active and (not benefit.active or not plan.active):
        raise HTTPException(409, "El beneficio o su servicio está inactivo.")
    return benefit


def _apply(campaign: Campaign, payload: CampaignIn, db: DbSession) -> None:
    _benefit(db, payload.benefitId)
    campaign.name = payload.name.strip()
    campaign.benefit_id = payload.benefitId
    campaign.action = payload.action
    campaign.action_config = payload.actionConfig or {}
    campaign.trigger = payload.trigger
    campaign.eligibility = {
        "mode": "ALL",
        "rules": [_validate_rule(rule) for rule in payload.rules],
    }
    campaign.priority = payload.priority
    campaign.stackable = payload.stackable
    campaign.max_recipients = payload.maxRecipients
    campaign.starts_at = _as_utc(payload.startsAt)
    campaign.ends_at = _as_utc(payload.endsAt)
    campaign.notification = payload.notification
    campaign.message = (payload.message or "").strip() or None


def _windows_overlap(a: Campaign, b: Campaign) -> bool:
    start_a, end_a = _as_utc(a.starts_at), _as_utc(a.ends_at)
    start_b, end_b = _as_utc(b.starts_at), _as_utc(b.ends_at)
    if end_a is not None and start_b is not None and end_a <= start_b:
        return False
    if end_b is not None and start_a is not None and end_b <= start_a:
        return False
    return True


def _overlap_warnings(db: DbSession, campaign: Campaign) -> list[dict]:
    scope_filter = (
        Campaign.organization_id.is_(None)
        if campaign.organization_id is None
        else Campaign.organization_id == campaign.organization_id
    )
    peers = db.scalars(
        select(Campaign).where(
            Campaign.id != campaign.id,
            scope_filter,
            Campaign.trigger == campaign.trigger,
            Campaign.status != CampaignStatus.ENDED,
            Campaign.deleted_at.is_(None),
        )
    ).all()
    return [
        {
            "id": peer.id,
            "name": peer.name,
            "priority": peer.priority,
            "stackable": peer.stackable,
        }
        for peer in peers
        if _windows_overlap(campaign, peer) and (not campaign.stackable or not peer.stackable)
    ]


def _out(db: DbSession, campaign: Campaign) -> dict:
    benefit = db.get(Benefit, campaign.benefit_id)
    plan = db.get(Plan, benefit.plan_id) if benefit else None
    recipients = db.scalar(
        select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == campaign.id)
    ) or 0
    pending_email = db.scalar(
        select(func.count(CampaignGrant.id)).where(
            CampaignGrant.campaign_id == campaign.id,
            CampaignGrant.email_status == "PENDING",
        )
    ) or 0
    eligibility = campaign.eligibility or {"mode": "ALL", "rules": []}
    return {
        "id": campaign.id,
        "code": campaign.code,
        "name": campaign.name,
        "benefitId": campaign.benefit_id,
        "benefitName": benefit.name if benefit else "Beneficio eliminado",
        "action": campaign.action.value,
        "actionConfig": campaign.action_config or {},
        "serviceId": plan.id if plan else None,
        "serviceName": plan.name if plan else "Servicio eliminado",
        "grantDays": benefit_duration(benefit, plan) if benefit and plan else None,
        "status": campaign.status.value,
        "trigger": campaign.trigger.value,
        "rules": eligibility.get("rules", []),
        "priority": campaign.priority,
        "stackable": campaign.stackable,
        "maxRecipients": campaign.max_recipients,
        "recipients": int(recipients),
        "startsAt": campaign.starts_at,
        "endsAt": campaign.ends_at,
        "activatedAt": campaign.activated_at,
        "notification": campaign.notification.value,
        "message": campaign.message,
        "pendingEmails": int(pending_email),
        "overlapWarnings": _overlap_warnings(db, campaign),
    }


def _campaign(db: DbSession, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if (
        campaign is None
        or campaign.organization_id is not None
        or campaign.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaña inexistente.")
    return campaign


@router.get("")
def list_campaigns(_: PlatformOwner, db: DbSession) -> list[dict]:
    campaigns = db.scalars(
        select(Campaign)
        .where(
            Campaign.organization_id.is_(None),
            Campaign.deleted_at.is_(None),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()
    return [_out(db, campaign) for campaign in campaigns]


@router.get("/capabilities")
def campaign_capabilities(_: PlatformOwner) -> dict:
    """Fuente única para constructor, plantillas y asistencia IA."""
    return capabilities_payload()


@router.post("/preview")
def preview_campaign_audience(payload: CampaignIn, _: PlatformOwner, db: DbSession) -> dict:
    """Simula la audiencia del borrador sin guardar ni ejecutar acciones."""
    _benefit(db, payload.benefitId)
    rules = [_validate_rule(rule) for rule in payload.rules]
    result = preview_audience(db, rules=rules, trigger=payload.trigger)
    result["action"] = payload.action.value
    return result


@router.post("/assist")
def assist_campaign(payload: CampaignAssistIn, owner: PlatformOwner, db: DbSession) -> dict:
    """Convierte lenguaje natural en un borrador; nunca persiste ni activa una campaña."""
    benefits = db.execute(
        select(Benefit, Plan)
        .join(Plan, Plan.id == Benefit.plan_id)
        .where(
            Benefit.organization_id.is_(None),
            Benefit.active.is_(True),
            Benefit.deleted_at.is_(None),
            Plan.active.is_(True),
            Plan.link_type == ServiceLinkType.PERSONAL,
        )
        .order_by(Benefit.id)
    ).all()
    benefit_options = [
        {
            "id": benefit.id,
            "name": benefit.name,
            "source": plan.ai_source.value,
            "durationDays": benefit_duration(benefit, plan),
        }
        for benefit, plan in benefits
    ]

    task = {
        "kind": "campaign_assist",
        "description": payload.description.strip(),
        "benefits": benefit_options,
        "capabilities": capabilities_payload(),
    }
    user_prompt = (
        "Intención del usuario:\n"
        + payload.description.strip()
        + "\n\nBeneficios activos disponibles (solo podés usar estos IDs):\n"
        + json.dumps(benefit_options, ensure_ascii=False)
    )
    try:
        result = run_platform_json_task(
            db,
            owner,
            system=CAMPAIGN_ASSIST_SYSTEM + "\n\n" + ai_capabilities_text(),
            user=user_prompt,
            task=task,
            usage_context=AIUsageContext(
                subject_type="CAMPAIGN_ASSIST",
                subject_label="Asistente de campañas",
                subject_route="/app/plataforma/campanas",
                diagnostic={
                    "descriptionChars": len(payload.description.strip()),
                    "benefitCount": len(benefit_options),
                    "capabilityCount": len(capabilities_payload()),
                },
            ),
        )
    except NoAIAvailable as exc:
        detail = "No hay una conexión de IA de plataforma disponible para generar el borrador."
        if exc.errors:
            detail += " " + "; ".join(exc.errors)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)

    if not isinstance(result.data, dict):
        raise HTTPException(502, "La IA devolvió un borrador inválido.")
    normalized = _normalize_assist(result.data, {item["id"] for item in benefit_options})
    normalized = _apply_description_capability_guards(payload.description.strip(), normalized)
    return _apply_requirement_coverage(
        result.data,
        normalized,
        description=payload.description.strip(),
        benefit_names={item["name"] for item in benefit_options},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignIn, owner: PlatformOwner, db: DbSession) -> dict:
    campaign = Campaign(
        code=f"CAMPAIGN_{uuid4().hex.upper()}",
        name="",
        benefit_id=payload.benefitId,
        action=payload.action,
        action_config=payload.actionConfig or {},
        created_by_account_id=owner.id,
    )
    _apply(campaign, payload, db)
    db.add(campaign)
    db.commit()
    return _out(db, campaign)


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: int, payload: CampaignIn, _: PlatformOwner, db: DbSession
) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "Una campaña terminada no se puede editar.")
    _apply(campaign, payload, db)
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/activate")
def activate_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "Una campaña terminada no se puede reactivar.")
    _benefit(db, campaign.benefit_id, require_active=True)
    if campaign.trigger == CampaignTrigger.SCHEDULED:
        raise HTTPException(409, "Las campañas programadas requieren el scheduler de T-059.")
    if campaign.status != CampaignStatus.ACTIVE:
        campaign.activated_at = datetime.now(timezone.utc)
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status == CampaignStatus.ENDED:
        raise HTTPException(409, "La campaña ya terminó.")
    campaign.status = CampaignStatus.PAUSED
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/finish")
def finish_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> dict:
    campaign = _campaign(db, campaign_id)
    campaign.status = CampaignStatus.ENDED
    db.commit()
    return _out(db, campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: int, _: PlatformOwner, db: DbSession) -> None:
    campaign = _campaign(db, campaign_id)
    if campaign.status != CampaignStatus.ENDED:
        raise HTTPException(409, "Solo se puede eliminar una campaña terminada.")

    recipients = db.scalar(
        select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == campaign.id)
    ) or 0
    if int(recipients) == 0:
        db.delete(campaign)
    else:
        campaign.deleted_at = datetime.now(timezone.utc)
    db.commit()
