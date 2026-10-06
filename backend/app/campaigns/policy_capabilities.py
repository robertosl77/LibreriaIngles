"""Catálogo de capacidades del motor genérico de políticas de Campaigns.

La primera familia ejecutable es SUPPRESSION. EXCLUSION queda reservada en el
contrato para evolucionar sin crear un segundo motor.
"""

from typing import Any


class CampaignPolicyCapabilityError(ValueError):
    pass


_POLICY_KINDS = (
    {
        "key": "SUPPRESSION",
        "label": "Supresión",
        "available": True,
        "description": "Bloquea una campaña candidata por una política global reutilizable.",
    },
    {
        "key": "EXCLUSION",
        "label": "Exclusión",
        "available": False,
        "description": "Reservada para definir su semántica mediante story times antes de habilitarla.",
    },
)

_POLICY_EFFECTS = (
    {
        "key": "BLOCK",
        "label": "Bloquear",
        "available": True,
        "description": "La campaña candidata no continúa hacia prioridad/convivencia.",
    },
)

_POLICY_RULES = {
    "CAMPAIGN_GRANTS_COUNT": {
        "key": "CAMPAIGN_GRANTS_COUNT",
        "label": "Campañas recibidas",
        "valueType": "integer",
        "operators": ["EQ", "GTE", "LTE"],
        "description": "Cantidad de campañas efectivamente recibidas por la persona dentro de una ventana.",
        "requiresWindow": True,
        "windowMinDays": 1,
        "windowMaxDays": 3650,
        "available": True,
    },
    "SAME_BENEFIT_GRANTS_COUNT": {
        "key": "SAME_BENEFIT_GRANTS_COUNT",
        "label": "Veces que recibió el mismo beneficio",
        "valueType": "integer",
        "operators": ["EQ", "GTE", "LTE"],
        "description": "Cantidad de campañas previas que otorgaron el mismo Benefit que la campaña candidata dentro de una ventana.",
        "requiresWindow": True,
        "windowMinDays": 1,
        "windowMaxDays": 3650,
        "available": True,
    },
}


def available_policy_kind_values() -> set[str]:
    return {item["key"] for item in _POLICY_KINDS if item["available"]}


def policy_capabilities_payload() -> dict[str, Any]:
    return {
        "kinds": [dict(item) for item in _POLICY_KINDS],
        "effects": [dict(item) for item in _POLICY_EFFECTS],
        "rules": [dict(item) for item in _POLICY_RULES.values()],
        "conditionModes": [
            {
                "key": "ALL",
                "label": "Todas (AND)",
                "available": True,
                "description": "Todas las condiciones de la política deben cumplirse para bloquear.",
            }
        ],
        "appliesToModes": [
            {
                "key": "ALL",
                "label": "Todas las campañas",
                "available": True,
                "description": "La política se evalúa para cualquier campaña del mismo scope.",
            },
            {
                "key": "CAMPAIGNS",
                "label": "Campañas seleccionadas",
                "available": True,
                "description": "La política solo se evalúa para las campañas elegidas.",
            },
        ],
    }


def validate_policy_rule(rule: dict[str, Any]) -> dict[str, Any]:
    field = str(rule.get("field") or "").strip().upper()
    capability = _POLICY_RULES.get(field)
    if capability is None or not capability["available"]:
        raise CampaignPolicyCapabilityError(
            f"Condición de política no soportada: {field or 'vacía'}."
        )

    operator = str(rule.get("operator") or "").strip().upper()
    if operator not in capability["operators"]:
        raise CampaignPolicyCapabilityError(
            f"Operador {operator or 'vacío'} no válido para {capability['label']}."
        )

    value = rule.get("value")
    if isinstance(value, bool):
        raise CampaignPolicyCapabilityError(
            f"{capability['label']} requiere un número entero."
        )
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise CampaignPolicyCapabilityError(
            f"{capability['label']} requiere un número entero."
        ) from exc
    if value < 0 or value > 10_000_000:
        raise CampaignPolicyCapabilityError("El valor debe estar entre 0 y 10.000.000.")

    window_days = rule.get("windowDays")
    if capability["requiresWindow"]:
        try:
            window_days = int(window_days)
        except (TypeError, ValueError) as exc:
            raise CampaignPolicyCapabilityError("La ventana debe indicarse en días.") from exc
        minimum = int(capability["windowMinDays"])
        maximum = int(capability["windowMaxDays"])
        if not minimum <= window_days <= maximum:
            raise CampaignPolicyCapabilityError(
                f"La ventana debe estar entre {minimum} y {maximum} días."
            )
    else:
        window_days = None

    return {
        "field": field,
        "operator": operator,
        "value": value,
        "windowDays": window_days,
    }
