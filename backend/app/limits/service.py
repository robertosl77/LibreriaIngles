"""T-220 (N-01) · Resolución de límites: plan → plataforma → default."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.limits.models import PlatformLimit
from app.limits.registry import get_definition, limit_definitions


class LimitValueError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedLimit:
    key: str
    value: int | None
    source: str  # PLAN | PLATFORM | DEFAULT


def _validate(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LimitValueError("Un límite tiene que ser un entero 1 o más (vacío = sin tope).")
    return value


def platform_value(db: Session, key: str) -> int | None:
    row = db.get(PlatformLimit, key)
    return row.value if row is not None else get_definition(key).default


def set_platform_value(db: Session, key: str, value: int | None) -> None:
    get_definition(key)
    value = _validate(value)
    row = db.get(PlatformLimit, key)
    if row is None:
        db.add(PlatformLimit(key=key, value=value))
    else:
        row.value = value
    db.flush()


def plan_overrides(plan) -> dict[str, int | None]:
    return dict(plan.limits or {})


def set_plan_overrides(plan, values: dict[str, int | None]) -> None:
    """Reemplaza los valores propios del plan. Una clave ausente = hereda de la plataforma."""
    known = {definition.key for definition in limit_definitions()}
    cleaned: dict[str, int | None] = {}
    for key, value in values.items():
        if key not in known:
            raise LimitValueError(f"Límite desconocido: {key}")
        cleaned[key] = _validate(value)
    plan.limits = cleaned or None


def resolve(db: Session, key: str, *, account: Account | None = None) -> ResolvedLimit:
    """Valor que rige para la cuenta (o el de plataforma si no hay cuenta)."""
    get_definition(key)
    if account is not None:
        from app.subscriptions.models import Plan
        from app.subscriptions.service import effective_service

        service = effective_service(db, account)
        if service.plan_id is not None:
            plan = db.get(Plan, service.plan_id)
            overrides = plan_overrides(plan) if plan is not None else {}
            if key in overrides:
                return ResolvedLimit(key, overrides[key], "PLAN")
    row = db.get(PlatformLimit, key)
    if row is not None:
        return ResolvedLimit(key, row.value, "PLATFORM")
    return ResolvedLimit(key, get_definition(key).default, "DEFAULT")
