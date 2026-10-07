"""T-191 · Límites de los proveedores de IA: aprenderlos solos y no chocar contra ellos.

Dos capas:

  CAPA PROVEEDOR (cruda, configurable en BD: `ai_provider_limit_mappings.rules`)
    Dónde informa cada compañía sus límites: headers de cada respuesta, cuerpo del error,
    código que distingue "se renueva" de "se agotó el saldo". Sin `if proveedor` en el código.

  CAPA NORMALIZADA (única, la que usa la app: `LimitInfo` / tabla `ai_quota_limits`)
    kind:      RENEWABLE (ventana que se renueva sola) | EXHAUSTED (saldo/tope: vuelve con intervención)
    dimension: REQUESTS | TOKENS | INPUT_TOKENS | OUTPUT_TOKENS
    window:    MINUTE | DAY | MONTH
    limit · remaining · reset_at · source (HEADER | ERROR | ESTIMATED) · tier

Con los límites aprendidos y el consumo ya registrado (`ai_usage_events`) se decide, ANTES de
llamar, si la llamada entra en el cupo (`check`) y cómo armar el trabajo (`can_run`, `batch_size`).

Rutas de las reglas: dot-path sobre JSON; `[]` recorre listas (ej. `error.details[].violations[]`).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import (
    AIConnection,
    AIProviderLimitMapping,
    AIQuotaLimit,
    AIUsageEvent,
    as_utc,
    utcnow,
)
from app.core.config import settings

RENEWABLE = "RENEWABLE"
EXHAUSTED = "EXHAUSTED"
WINDOW_SECONDS = {"MINUTE": 60, "DAY": 86_400}
HEALTH_CHECK = "health_check"

# ---------------------------------------------------------------- capa proveedor (reglas por defecto)
# Se siembran en BD con la migración 0029; si falta la fila, se usan estas.

_OPENAI_STYLE_HEADERS = [
    {"dimension": "REQUESTS", "window": "MINUTE", "limit": "x-ratelimit-limit-requests",
     "remaining": "x-ratelimit-remaining-requests", "reset": "x-ratelimit-reset-requests"},
    {"dimension": "TOKENS", "window": "MINUTE", "limit": "x-ratelimit-limit-tokens",
     "remaining": "x-ratelimit-remaining-tokens", "reset": "x-ratelimit-reset-tokens"},
]
_GEMINI_ERROR_RULES = {
    "violations": {
        "items": "error.details[].violations[]",
        "id": "quotaId",
        "value": "quotaValue",
        "model": "quotaDimensions.model",
    },
    "retryDelay": "error.details[].retryDelay",
    # El orden importa: "InputTokens" antes que "Tokens".
    "keywords": {
        "window": [["PerMinute", "MINUTE"], ["PerDay", "DAY"]],
        "dimension": [["InputTokens", "INPUT_TOKENS"], ["OutputTokens", "OUTPUT_TOKENS"],
                      ["Tokens", "TOKENS"], ["Requests", "REQUESTS"]],
        "tier": [["FreeTier", "free"]],
    },
}

DEFAULT_LIMIT_MAPPINGS: dict[str, dict] = {
    "GEMINI": {
        **_GEMINI_ERROR_RULES,
        "headers": [],
        "retryAfterHeader": "retry-after",
        "dayResetTimezone": "America/Los_Angeles",
        "classify": [
            {"contains": ["prepayment", "credits are depleted", "billing account", "billing details are"],
             "kind": EXHAUSTED},
        ],
        "renewableStatuses": [429],
    },
    "OPENAI": {
        "headers": _OPENAI_STYLE_HEADERS,
        "retryAfterHeader": "retry-after",
        "classify": [{"contains": ["insufficient_quota"], "kind": EXHAUSTED}],
        "renewableStatuses": [429],
    },
    "ANTHROPIC": {
        "headers": [
            {"dimension": "REQUESTS", "window": "MINUTE", "limit": "anthropic-ratelimit-requests-limit",
             "remaining": "anthropic-ratelimit-requests-remaining", "reset": "anthropic-ratelimit-requests-reset"},
            {"dimension": "TOKENS", "window": "MINUTE", "limit": "anthropic-ratelimit-tokens-limit",
             "remaining": "anthropic-ratelimit-tokens-remaining", "reset": "anthropic-ratelimit-tokens-reset"},
            {"dimension": "INPUT_TOKENS", "window": "MINUTE", "limit": "anthropic-ratelimit-input-tokens-limit",
             "remaining": "anthropic-ratelimit-input-tokens-remaining", "reset": "anthropic-ratelimit-input-tokens-reset"},
            {"dimension": "OUTPUT_TOKENS", "window": "MINUTE", "limit": "anthropic-ratelimit-output-tokens-limit",
             "remaining": "anthropic-ratelimit-output-tokens-remaining", "reset": "anthropic-ratelimit-output-tokens-reset"},
        ],
        "retryAfterHeader": "retry-after",
        "classify": [
            {"contains": ["enforced_spend_limit_reached", "credit balance", "specified api usage limits"],
             "kind": EXHAUSTED},
        ],
        "renewableStatuses": [429],
    },
    # El simulado entiende ambos estilos (errores tipo Gemini y headers tipo OpenAI) para los tests.
    "MOCK": {
        **_GEMINI_ERROR_RULES,
        "headers": _OPENAI_STYLE_HEADERS,
        "retryAfterHeader": "retry-after",
        "dayResetTimezone": "America/Los_Angeles",
        "classify": [{"contains": ["insufficient_quota", "credits are depleted"], "kind": EXHAUSTED}],
        "renewableStatuses": [429],
    },
}


def provider_rules(db: Session, provider: str) -> dict:
    row = db.get(AIProviderLimitMapping, (provider or "").upper())
    if row is not None:
        return row.rules if row.active else {}
    return DEFAULT_LIMIT_MAPPINGS.get((provider or "").upper(), {})


# ---------------------------------------------------------------- capa normalizada


@dataclass
class LimitInfo:
    kind: str
    dimension: str
    window: str
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None
    source: str = "ERROR"
    tier: str | None = None
    model: str | None = None


@dataclass
class ProviderSignal:
    """Lo que dijo el proveedor en una respuesta o un error, ya normalizado."""

    kind: str | None = None  # RENEWABLE | EXHAUSTED | None (no es un error de límite)
    limits: list[LimitInfo] = field(default_factory=list)
    retry_at: datetime | None = None


def _values_at(payload, path: str | None) -> list:
    if not path:
        return []
    nodes = [payload]
    for part in path.split("."):
        many = part.endswith("[]")
        key = part[:-2] if many else part
        nxt = []
        for node in nodes:
            value = node.get(key) if isinstance(node, dict) else None
            if value is None:
                continue
            if many:
                nxt.extend(value if isinstance(value, list) else [])
            else:
                nxt.append(value)
        nodes = nxt
    return nodes


def _int(value) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def parse_reset(value, now: datetime) -> datetime | None:
    """'1s', '6m0s', '20ms', '52.3s' (duración), '30' (segundos) o RFC 3339 (momento)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return now + timedelta(seconds=float(text))
    parts = _DURATION.findall(text)
    if parts and "".join(n + u for n, u in parts) == text:
        units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
        return now + timedelta(seconds=sum(float(n) * units[u] for n, u in parts))
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return as_utc(moment)


def _keyword(table: list, text: str) -> str | None:
    for needle, value in table or []:
        if needle.lower() in text.lower():
            return value
    return None


def _day_reset(rules: dict, now: datetime) -> datetime:
    tz = ZoneInfo(rules.get("dayResetTimezone") or "UTC")
    local = now.astimezone(tz)
    nxt = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.astimezone(now.tzinfo)


def _window_end(rules: dict, window: str, now: datetime) -> datetime:
    if window == "DAY":
        return _day_reset(rules, now)
    return now + timedelta(seconds=WINDOW_SECONDS.get(window, 60))


def limits_from_headers(rules: dict, headers: dict | None, now: datetime, model: str | None) -> list[LimitInfo]:
    lowered = {str(k).lower(): v for k, v in (headers or {}).items()}
    found = []
    for spec in rules.get("headers") or []:
        limit = _int(lowered.get(spec["limit"].lower()))
        if limit is None:
            continue
        found.append(
            LimitInfo(
                kind=RENEWABLE,
                dimension=spec["dimension"],
                window=spec["window"],
                limit=limit,
                remaining=_int(lowered.get(spec.get("remaining", "").lower())),
                reset_at=parse_reset(lowered.get(spec.get("reset", "").lower()), now),
                source="HEADER",
                model=model,
            )
        )
    return found


def classify_error(
    rules: dict, status: int, body: dict | None, text: str, headers: dict | None, now: datetime, model: str | None
) -> ProviderSignal:
    """Normaliza un error del proveedor: ¿es un límite? ¿se renueva o se agotó? ¿cuál y cuánto?"""
    lowered_text = (text or "").lower()
    kind = None
    for rule in rules.get("classify") or []:
        statuses = rule.get("status")
        if statuses and status not in statuses:
            continue
        if any(needle.lower() in lowered_text for needle in rule.get("contains") or []):
            kind = rule["kind"]
            break
    if kind is None and status in (rules.get("renewableStatuses") or []):
        kind = RENEWABLE
    if kind is None:
        return ProviderSignal()

    signal = ProviderSignal(kind=kind)
    header_map = {str(k).lower(): v for k, v in (headers or {}).items()}
    retry = parse_reset(header_map.get((rules.get("retryAfterHeader") or "").lower()), now)
    for value in _values_at(body, rules.get("retryDelay")):
        retry = retry or parse_reset(value, now)
    signal.retry_at = retry

    spec = rules.get("violations") or {}
    keywords = rules.get("keywords") or {}
    for item in _values_at(body, spec.get("items")):
        quota_id = str((_values_at(item, spec.get("id")) or [""])[0])
        dimension = _keyword(keywords.get("dimension"), quota_id)
        window = _keyword(keywords.get("window"), quota_id)
        if not dimension or not window:
            continue
        reset_at = _window_end(rules, window, now) if window == "DAY" else (retry or _window_end(rules, window, now))
        signal.limits.append(
            LimitInfo(
                kind=kind,
                dimension=dimension,
                window=window,
                limit=_int((_values_at(item, spec.get("value")) or [None])[0]),
                remaining=0,
                reset_at=reset_at,
                source="ERROR",
                tier=_keyword(keywords.get("tier"), quota_id),
                model=(_values_at(item, spec.get("model")) or [model])[0],
            )
        )
    # Si el error nombra los límites violados, vuelve cuando se renueva el ÚLTIMO de ellos: Gemini
    # manda retryDelay "1s" incluso con el límite diario agotado (engañoso).
    violated = [lim.reset_at for lim in signal.limits if lim.reset_at]
    if violated:
        signal.retry_at = max(violated + ([retry] if retry else []))
    # Los headers del error también informan límites (OpenAI / Anthropic).
    signal.limits.extend(limits_from_headers(rules, headers, now, model))
    if kind == RENEWABLE and signal.retry_at is None:
        ends = [lim.reset_at for lim in signal.limits if lim.reset_at and lim.reset_at > now]
        signal.retry_at = min(ends) if ends else now + timedelta(seconds=60)
    return signal


# ---------------------------------------------------------------- aprender (persistir)


def connection_model(connection: AIConnection) -> str:
    from app.ai.providers import PROVIDERS

    info = PROVIDERS.get((connection.provider or "").upper())
    return connection.model or (info.default_model if info else "")


def record(db: Session, connection: AIConnection, limits: list[LimitInfo]) -> None:
    """Guarda/actualiza los límites aprendidos de la conexión (capa normalizada)."""
    now = utcnow()
    for info in limits:
        if info.limit is None:
            continue
        model = info.model or connection_model(connection)
        row = db.scalar(
            select(AIQuotaLimit).where(
                AIQuotaLimit.connection_id == connection.id,
                AIQuotaLimit.model == model,
                AIQuotaLimit.dimension == info.dimension,
                AIQuotaLimit.window == info.window,
            )
        )
        if row is None:
            row = AIQuotaLimit(
                connection_id=connection.id, model=model, dimension=info.dimension, window=info.window
            )
            db.add(row)
        row.kind = info.kind
        row.limit_value = info.limit
        row.remaining = info.remaining
        row.reset_at = info.reset_at
        row.source = info.source
        row.tier = info.tier or row.tier
        row.observed_at = now
        db.flush()  # la sesión no hace autoflush: el control previo tiene que ver lo recién aprendido


def learn_from_success(db: Session, connection: AIConnection, headers: dict | None) -> None:
    rules = provider_rules(db, connection.provider)
    if rules:
        record(db, connection, limits_from_headers(rules, headers, utcnow(), connection_model(connection)))


def learn_from_error(db: Session, connection: AIConnection, http: dict | None) -> ProviderSignal:
    if not http:
        return ProviderSignal()
    rules = provider_rules(db, connection.provider)
    if not rules:
        return ProviderSignal()
    signal = classify_error(
        rules,
        http.get("status") or 0,
        http.get("json"),
        http.get("text") or "",
        http.get("headers"),
        utcnow(),
        connection_model(connection),
    )
    record(db, connection, signal.limits)
    return signal


def learned_limits(db: Session, connection: AIConnection) -> list[AIQuotaLimit]:
    """Límites propios de la conexión; si no tiene, ESTIMADOS de otra conexión del mismo proveedor y
    modelo en plan gratuito (mismos valores por modelo). No se persisten como propios."""
    model = connection_model(connection)
    own = list(
        db.scalars(
            select(AIQuotaLimit).where(
                AIQuotaLimit.connection_id == connection.id, AIQuotaLimit.model == model
            )
        ).all()
    )
    if own:
        return own
    donors = db.scalars(
        select(AIQuotaLimit)
        .join(AIConnection, AIConnection.id == AIQuotaLimit.connection_id)
        .where(
            AIConnection.provider == connection.provider,
            AIConnection.id != connection.id,
            AIQuotaLimit.model == model,
            AIQuotaLimit.tier == "free",
            AIQuotaLimit.kind == RENEWABLE,
        )
        .order_by(AIQuotaLimit.observed_at.desc())
    ).all()
    estimated, seen = [], set()
    for row in donors:
        key = (row.dimension, row.window)
        if key in seen:
            continue
        seen.add(key)
        estimated.append(
            AIQuotaLimit(
                connection_id=connection.id, model=model, kind=row.kind, dimension=row.dimension,
                window=row.window, limit_value=row.limit_value, remaining=None, reset_at=None,
                source="ESTIMATED", tier=row.tier, observed_at=row.observed_at,
            )
        )
    return estimated


# ---------------------------------------------------------------- pesos (aprendidos del consumo de todos)

DEFAULT_OUTPUT = {"generate_class": 1200, "evaluate_answer": 600, "evaluate_batch": 1300, "transcribe_audio": 400}
DEFAULT_INPUT = {"transcribe_audio": 500}
DEFAULT_CHARS_PER_TOKEN = 3.6
HISTORY = 200


@dataclass
class Estimate:
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


def _p90(values: list[int]) -> int | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, math.ceil(0.9 * len(values)) - 1)]


def estimate(db: Session, provider: str, model: str, operation: str, *, chars: int = 0, items: int = 1) -> Estimate:
    """Peso estimado de una llamada, con datos de cualquier persona:
    entrada = caracteres del pedido / (caracteres por token aprendidos de ese modelo);
    salida  = percentil 90 de salida + razonamiento de esa operación (por ítem en lotes)."""
    rows = db.execute(
        select(AIUsageEvent.input_tokens, AIUsageEvent.output_tokens, AIUsageEvent.reasoning_tokens,
               AIUsageEvent.diagnostic_snapshot)
        .where(
            AIUsageEvent.success.is_(True),
            AIUsageEvent.provider == provider,
            AIUsageEvent.model == model,
            AIUsageEvent.operation == operation,
        )
        .order_by(AIUsageEvent.id.desc())
        .limit(HISTORY)
    ).all()
    ratios, outputs, inputs = [], [], []
    for inp, out, reasoning, snapshot in rows:
        snap = snapshot or {}
        if inp is not None:
            inputs.append(inp)
        sent = (snap.get("systemChars") or 0) + (snap.get("userChars") or 0)
        if inp and sent:
            ratios.append(sent / inp)
        if out is not None:
            per = (out + (reasoning or 0)) / max(1, ((snap.get("details") or {}).get("itemCount") or 1))
            outputs.append(int(per))
    chars_per_token = sorted(ratios)[len(ratios) // 2] if ratios else DEFAULT_CHARS_PER_TOKEN
    per_item_out = _p90(outputs) or DEFAULT_OUTPUT.get(operation, 800)
    if chars <= 0:
        # Audio u operación sin texto medible: entrada típica del historial.
        input_tokens = _p90(inputs) or DEFAULT_INPUT.get(operation, 500)
    else:
        input_tokens = math.ceil(chars / max(0.5, chars_per_token))
    return Estimate(input_tokens=input_tokens, output_tokens=per_item_out * max(1, items))


# ---------------------------------------------------------------- control previo


@dataclass
class QuotaDecision:
    ok: bool = True
    retry_at: datetime | None = None
    blocked_by: str | None = None  # ej. "REQUESTS/DAY"
    # Lo que queda disponible por dimensión (mínimo entre ventanas), para armar tandas.
    available: dict[str, int] = field(default_factory=dict)


def _window_start(rules: dict, row: AIQuotaLimit, now: datetime) -> datetime:
    if row.window == "DAY":
        reset = as_utc(row.reset_at)
        if reset and reset > now:
            return reset - timedelta(days=1)
        return _day_reset(rules, now) - timedelta(days=1)
    return now - timedelta(seconds=WINDOW_SECONDS.get(row.window, 60))


def _used(db: Session, connection: AIConnection, model: str, dimension: str, since: datetime) -> int:
    base = [
        AIUsageEvent.connection_id == connection.id,
        AIUsageEvent.created_at >= since,
        AIUsageEvent.operation != HEALTH_CHECK,
    ]
    if model:
        base.append((AIUsageEvent.model == model) | AIUsageEvent.model.is_(None))
    if dimension == "REQUESTS":
        return db.scalar(select(func.count(AIUsageEvent.id)).where(*base)) or 0
    column = {
        "INPUT_TOKENS": AIUsageEvent.input_tokens,
        "OUTPUT_TOKENS": AIUsageEvent.output_tokens,
    }.get(dimension, AIUsageEvent.total_tokens)
    return db.scalar(select(func.coalesce(func.sum(column), 0)).where(*base)) or 0


def _need(dimension: str, est: Estimate) -> int:
    return {
        "REQUESTS": 1,
        "INPUT_TOKENS": est.input_tokens,
        "OUTPUT_TOKENS": est.output_tokens,
    }.get(dimension, est.total)


def check(db: Session, connection: AIConnection, est: Estimate, *, now: datetime | None = None) -> QuotaDecision:
    """¿Entra esta llamada en el cupo aprendido de la conexión? (margen `ai_quota_margin`)."""
    decision = QuotaDecision()
    if not settings.ai_quota_control:
        return decision
    now = now or utcnow()
    rules = provider_rules(db, connection.provider)
    model = connection_model(connection)
    for row in learned_limits(db, connection):
        if row.kind != RENEWABLE or row.limit_value is None or row.window not in WINDOW_SECONDS:
            continue
        since = _window_start(rules, row, now)
        used = _used(db, connection, model, row.dimension, since)
        cap = int(row.limit_value * settings.ai_quota_margin)
        observed = as_utc(row.observed_at)
        reset = as_utc(row.reset_at)
        # El proveedor dijo cuánto quedaba (headers): se descuenta lo usado desde entonces.
        if row.source == "HEADER" and row.remaining is not None and reset and reset > now and observed:
            margin_loss = row.limit_value - cap
            available = row.remaining - margin_loss - _used(db, connection, model, row.dimension, observed)
        else:
            available = cap - used
        key = row.dimension
        decision.available[key] = min(decision.available.get(key, available), available)
        if available < _need(row.dimension, est):
            decision.ok = False
            ends_at = reset if reset and reset > now else (
                _day_reset(rules, now) if row.window == "DAY" else now + timedelta(seconds=WINDOW_SECONDS[row.window])
            )
            if decision.retry_at is None or ends_at > decision.retry_at:
                decision.retry_at = ends_at
                decision.blocked_by = f"{row.dimension}/{row.window}"
    return decision


def wait_seconds(decision: QuotaDecision, now: datetime | None = None) -> float | None:
    if decision.ok or decision.retry_at is None:
        return None
    return max(0.0, (decision.retry_at - (now or utcnow())).total_seconds())


def can_run(db: Session, account, operation: str, *, chars: int, items: int = 1) -> QuotaDecision:
    """¿Alguna conexión habilitada para la cuenta puede hacer esta operación ahora?
    Devuelve la primera decisión OK, o la que vuelve antes si ninguna entra."""
    from app.ai.service import candidate_connections, limit_reason

    best: QuotaDecision | None = None
    for connection in candidate_connections(db, account):
        if limit_reason(db, connection, account):
            continue
        est = estimate(db, connection.provider, connection_model(connection), operation, chars=chars, items=items)
        decision = check(db, connection, est)
        if decision.ok:
            return decision
        if best is None or (decision.retry_at and best.retry_at and decision.retry_at < best.retry_at):
            best = decision
    return best or QuotaDecision()


def batch_size(db: Session, account, *, items: int, chars_per_item: int) -> int:
    """Tamaño de tanda del lote de corrección según el límite que aprieta (T-171/T-181):
    si aprietan los PEDIDOS se juntan más ítems por llamada; si aprietan los TOKENS, menos."""
    from app.ai.service import candidate_connections

    size = max(2, settings.ai_batch_max_items)
    connections = candidate_connections(db, account)
    if not settings.ai_quota_control or not connections:
        return size
    connection = connections[0]
    per_item = estimate(db, connection.provider, connection_model(connection), "evaluate_batch",
                        chars=chars_per_item, items=1)
    decision = check(db, connection, Estimate(0, 0))
    requests_left = decision.available.get("REQUESTS")
    if requests_left is not None and requests_left > 0 and math.ceil(items / size) > requests_left:
        size = math.ceil(items / requests_left)
    token_keys = [k for k in ("TOKENS", "INPUT_TOKENS") if k in decision.available]
    if token_keys:
        tokens_left = min(decision.available[k] for k in token_keys)
        per = per_item.total if "TOKENS" in token_keys else per_item.input_tokens
        if per > 0:
            size = min(size, max(1, tokens_left // per))
    return max(1, min(size, items))


def no_quota_message(decision: QuotaDecision, action: str) -> str:
    """Aviso al usuario cuando el cupo de IA no alcanza (con la hora en que vuelve, si se sabe)."""
    text = f"No hay tokens disponibles para {action}."
    if decision.retry_at:
        local = decision.retry_at.astimezone(ZoneInfo(settings.display_timezone))
        today = utcnow().astimezone(ZoneInfo(settings.display_timezone)).date()
        when = f"{local:%H:%M}" if local.date() == today else f"{local:%d/%m %H:%M}"
        text += f" Probá de nuevo después de las {when}."
    return text
