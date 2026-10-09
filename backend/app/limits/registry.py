"""T-220 (N-01) · Catálogo único de límites.

Regla: un límite se declara UNA vez acá (clave, unidad, default) y se resuelve siempre igual:

    plan del servicio vigente  →  valor de plataforma  →  default declarado
    (Plan.limits[key])            (platform_limits)       (LimitDefinition.default)

`None` en cualquier nivel = "sin tope" solo si es el valor que gana. Un plan sin la clave hereda.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LimitDefinition:
    key: str
    label: str
    unit: str
    description: str
    default: int | None = None


_LIMITS: dict[str, LimitDefinition] = {}


def define_limit(definition: LimitDefinition) -> LimitDefinition:
    existing = _LIMITS.get(definition.key)
    if existing is not None and existing != definition:
        raise RuntimeError(f"El límite {definition.key} ya está declarado con otros datos.")
    _LIMITS[definition.key] = definition
    return definition


def limit_definitions() -> list[LimitDefinition]:
    from app.limits import catalog  # noqa: F401  (composición: módulos que declaran límites)

    return sorted(_LIMITS.values(), key=lambda item: item.key)


def get_definition(key: str) -> LimitDefinition:
    for definition in limit_definitions():
        if definition.key == key:
            return definition
    raise KeyError(f"Límite no declarado: {key}")
