"""T-191 · Límites de los proveedores: capa proveedor → capa normalizada, aprendizaje y control previo."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.ai import limits as quota
from app.ai.limits import DEFAULT_LIMIT_MAPPINGS, EXHAUSTED, RENEWABLE, classify_error, limits_from_headers, parse_reset
from app.core.config import settings

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # 08:00 en Los Ángeles (PDT)

GEMINI_RPD_429 = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaDimensions": {"model": "gemini-2.5-flash", "location": "global"},
                        "quotaValue": "250",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1s"},
        ],
    }
}
GEMINI_RPM_429 = {
    "error": {
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": "You exceeded your current quota.",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{
                "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                "quotaDimensions": {"model": "gemini-2.5-flash"}, "quotaValue": "10"}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "52.3s"},
        ],
    }
}


def _classify(provider, status, body, text=None, headers=None):
    import json

    return classify_error(
        DEFAULT_LIMIT_MAPPINGS[provider], status, body, text or json.dumps(body or {}), headers, NOW, "gemini-2.5-flash"
    )


# ---------------------------------------------------------------- capa proveedor → normalizada


def test_gemini_daily_limit_is_renewable_until_pacific_midnight():
    signal = _classify("GEMINI", 429, GEMINI_RPD_429)
    assert signal.kind == RENEWABLE  # dice "quota" pero se renueva sola
    [limit] = signal.limits
    assert (limit.dimension, limit.window, limit.limit, limit.tier) == ("REQUESTS", "DAY", 250, "free")
    # Medianoche de Los Ángeles = 07:00 UTC del día siguiente (PDT).
    assert limit.reset_at == datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


def test_gemini_minute_limit_uses_retry_delay():
    signal = _classify("GEMINI", 429, GEMINI_RPM_429)
    [limit] = signal.limits
    assert (limit.dimension, limit.window, limit.limit) == ("REQUESTS", "MINUTE", 10)
    assert signal.retry_at == NOW + timedelta(seconds=52.3)


def test_exhausted_balance_is_distinguished_for_every_provider():
    openai = _classify("OPENAI", 429, {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}})
    anthropic = _classify(
        "ANTHROPIC", 429,
        {"type": "error", "error": {"type": "rate_limit_error", "details": {"error_code": "enforced_spend_limit_reached"}}},
    )
    credit = _classify("ANTHROPIC", 400, None, text="Your credit balance is too low to access the Anthropic API.")
    rate = _classify("OPENAI", 429, {"error": {"code": "rate_limit_exceeded"}}, headers={"retry-after": "2"})
    assert openai.kind == anthropic.kind == credit.kind == EXHAUSTED
    assert rate.kind == RENEWABLE and rate.retry_at == NOW + timedelta(seconds=2)
    assert _classify("OPENAI", 500, None, text="boom").kind is None  # no es un límite


def test_headers_on_success_teach_the_limit_before_hitting_it():
    openai = limits_from_headers(DEFAULT_LIMIT_MAPPINGS["OPENAI"], {
        "x-ratelimit-limit-requests": "500", "x-ratelimit-remaining-requests": "499",
        "x-ratelimit-reset-requests": "120ms", "x-ratelimit-limit-tokens": "200000",
        "x-ratelimit-remaining-tokens": "197000", "x-ratelimit-reset-tokens": "6m0s",
    }, NOW, "gpt-4o-mini")
    by_dim = {l.dimension: l for l in openai}
    assert by_dim["REQUESTS"].limit == 500 and by_dim["TOKENS"].remaining == 197000
    assert by_dim["TOKENS"].reset_at == NOW + timedelta(minutes=6)
    anthropic = limits_from_headers(DEFAULT_LIMIT_MAPPINGS["ANTHROPIC"], {
        "Anthropic-Ratelimit-Input-Tokens-Limit": "50000",
        "anthropic-ratelimit-input-tokens-remaining": "48000",
        "anthropic-ratelimit-input-tokens-reset": "2026-10-07T15:01:00Z",
    }, NOW, "claude-haiku-4-5")
    assert anthropic[0].dimension == "INPUT_TOKENS" and anthropic[0].reset_at == NOW + timedelta(minutes=1)
    assert all(l.source == "HEADER" for l in openai + anthropic)


@pytest.mark.parametrize("value,seconds", [("1s", 1), ("6m0s", 360), ("20ms", 0.02), ("52.3s", 52.3), ("30", 30), ("1h2m3s", 3723)])
def test_parse_reset(value, seconds):
    assert parse_reset(value, NOW) == NOW + timedelta(seconds=seconds)


# ---------------------------------------------------------------- persistencia y control previo


def _connection(db, provider="MOCK", model="mock", name="Simulado", owner_id=None):
    from app.ai.models import AIConnection, AIConnectionOwnerType

    connection = AIConnection(
        provider=provider, name=name, model=model, priority=1, active=True,
        owner_type=AIConnectionOwnerType.PLATFORM if owner_id is None else AIConnectionOwnerType.ACCOUNT,
        owner_id=owner_id,
    )
    db.add(connection)
    db.flush()
    return connection


def _usage(db, connection, count, *, tokens=100, when=None):
    from app.ai.models import AIUsageEvent

    for _ in range(count):
        db.add(AIUsageEvent(
            connection_id=connection.id, connection_name=connection.name, owner_type=connection.owner_type,
            provider=connection.provider, model=connection.model, operation="generate_class",
            input_tokens=tokens, output_tokens=0, total_tokens=tokens, success=True,
            created_at=when or quota.utcnow(),
        ))
    db.flush()


@pytest.fixture
def db(client):
    from app.db import SessionLocal

    with SessionLocal() as session:
        yield session


def test_db_mapping_overrides_defaults(db):
    """La capa proveedor es configurable en BD: agregar o cambiar una IA = cargar reglas."""
    from app.ai.models import AIProviderLimitMapping

    db.add(AIProviderLimitMapping(provider="NUEVA", rules={
        "headers": [{"dimension": "REQUESTS", "window": "MINUTE", "limit": "x-cupo", "remaining": "x-queda", "reset": "x-vuelve"}],
        "renewableStatuses": [429],
    }, active=True))
    db.flush()
    rules = quota.provider_rules(db, "nueva")
    [limit] = limits_from_headers(rules, {"X-Cupo": "7", "x-queda": "3", "x-vuelve": "10s"}, NOW, "m")
    assert (limit.limit, limit.remaining) == (7, 3)


def test_learned_limit_blocks_before_calling(db):
    connection = _connection(db)
    quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="MINUTE", limit=5)])
    _usage(db, connection, 5)
    decision = quota.check(db, connection, quota.Estimate(100, 50))
    assert not decision.ok and decision.blocked_by == "REQUESTS/MINUTE"
    assert decision.retry_at is not None


def test_tokens_per_minute_and_margin(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_quota_margin", 0.9)
    connection = _connection(db)
    quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="INPUT_TOKENS", window="MINUTE", limit=10_000)])
    _usage(db, connection, 1, tokens=8_000)
    assert quota.check(db, connection, quota.Estimate(900, 0)).ok  # 8.000 + 900 ≤ 9.000
    assert not quota.check(db, connection, quota.Estimate(1_500, 0)).ok
    old = quota.utcnow() - timedelta(minutes=2)
    connection2 = _connection(db, name="Otra")
    quota.record(db, connection2, [quota.LimitInfo(kind=RENEWABLE, dimension="INPUT_TOKENS", window="MINUTE", limit=10_000)])
    _usage(db, connection2, 1, tokens=9_500, when=old)  # fuera de la ventana
    assert quota.check(db, connection2, quota.Estimate(1_500, 0)).ok


def test_new_connection_inherits_free_tier_limit_as_estimate(db):
    donor = _connection(db, provider="GEMINI", model="gemini-2.5-flash", name="Gemini #1")
    quota.record(db, donor, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="DAY", limit=250, tier="free")])
    jacinto = _connection(db, provider="GEMINI", model="gemini-2.5-flash", name="Gemini Jacinto")
    [estimated] = quota.learned_limits(db, jacinto)
    assert estimated.source == "ESTIMATED" and estimated.limit_value == 250
    # Su primer dato real reemplaza el estimado.
    quota.record(db, jacinto, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="DAY", limit=1000)])
    [own] = quota.learned_limits(db, jacinto)
    assert own.source == "ERROR" and own.limit_value == 1000


def test_quota_control_can_be_turned_off(db, monkeypatch):
    connection = _connection(db)
    quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="MINUTE", limit=1)])
    _usage(db, connection, 3)
    monkeypatch.setattr(settings, "ai_quota_control", False)
    assert quota.check(db, connection, quota.Estimate(1, 1)).ok


def test_estimate_learns_chars_per_token_and_output_from_history(db):
    from app.ai.models import AIUsageEvent

    connection = _connection(db)
    for _ in range(5):
        db.add(AIUsageEvent(
            connection_id=connection.id, connection_name="x", owner_type=connection.owner_type, provider="MOCK",
            model="mock", operation="evaluate_answer", input_tokens=1000, output_tokens=300, reasoning_tokens=100,
            total_tokens=1400, success=True, diagnostic_snapshot={"systemChars": 3000, "userChars": 1000},
        ))
    db.flush()
    est = quota.estimate(db, "MOCK", "mock", "evaluate_answer", chars=8000)
    assert est.input_tokens == 2000  # 4 caracteres por token aprendidos
    assert est.output_tokens == 400  # salida + razonamiento


# ---------------------------------------------------------------- router y plan B


def _student(client):
    from conftest import login

    headers = login(client)
    assert client.put("/api/v1/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    created = client.post(
        "/api/v1/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    return headers, created.json()["id"]


def test_renewable_429_backs_off_until_reset_not_paused(client, monkeypatch):
    """El límite diario gratuito de Gemini no deja la conexión en 'cuota agotada'."""
    import json

    from app.ai.mock import MockProvider
    from app.ai.models import AIConnection, AIConnectionStatus, AIQuotaLimit
    from app.ai.providers import ProviderError
    from app.db import SessionLocal

    def rate_limited(self, system, user, task):
        error = ProviderError(AIConnectionStatus.QUOTA_EXCEEDED, "Cuota agotada.")
        error.http = {"status": 429, "headers": {}, "json": GEMINI_RPD_429, "text": json.dumps(GEMINI_RPD_429)}
        raise error

    monkeypatch.setattr(MockProvider, "complete_json", rate_limited)
    headers, connection_id = _student(client)
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "GENERATION_FAILED"
    with SessionLocal() as db:
        connection = db.get(AIConnection, connection_id)
        assert connection.status == AIConnectionStatus.RATE_LIMITED
        backoff = quota.as_utc(connection.backoff_until)
        assert backoff - quota.utcnow() > timedelta(hours=1)  # hasta la medianoche del Pacífico
        [limit] = db.scalars(select(AIQuotaLimit)).all()
        assert (limit.dimension, limit.window, limit.limit_value, limit.tier) == ("REQUESTS", "DAY", 250, "free")


def test_no_quota_skips_the_call_and_says_until_when(client, monkeypatch):
    from app.ai.mock import MockProvider
    from app.ai.models import AIConnection
    from app.db import SessionLocal

    headers, connection_id = _student(client)
    with SessionLocal() as db:
        connection = db.get(AIConnection, connection_id)
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="DAY", limit=2)])
        _usage(db, connection, 2)
        db.commit()
    called = []
    monkeypatch.setattr(MockProvider, "complete_json", lambda *a, **k: called.append(1))
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert called == []  # no se llamó: no se pagó ni se gastó un pedido
    assert klass["status"] == "GENERATION_FAILED"
    assert "sin cupo de pedidos del día hasta las" in klass["generationError"]
    assert "REQUESTS/DAY" not in klass["generationError"]  # el alumno no ve el código


def test_short_wait_is_waited_instead_of_failing(client, monkeypatch):
    from app.ai import service as ai_service
    from app.ai.models import AIConnection
    from app.db import SessionLocal

    headers, connection_id = _student(client)
    with SessionLocal() as db:
        connection = db.get(AIConnection, connection_id)
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="MINUTE", limit=1)])
        _usage(db, connection, 1)
        db.commit()
    slept = []
    monkeypatch.setattr(settings, "ai_quota_max_wait_seconds", 120)
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "READY" and slept and slept[0] <= 60


def test_class_is_reduced_to_fit_tokens_keeping_conversation_pairs(client, monkeypatch):
    from app.ai.models import AIConnection
    from app.classes import generation
    from app.db import SessionLocal

    headers, connection_id = _student(client)
    real_select = generation.select_slots
    monkeypatch.setattr(generation, "select_slots", lambda *a, **k: real_select(*a, **{**k, "rng": __import__("random").Random(5)}))
    with SessionLocal() as db:
        connection = db.get(AIConnection, connection_id)
        # Entra un pedido chico pero no uno de 6 ejercicios.
        full = generation.generation_chars("A1", real_select(list(__import__("app.curriculum.service", fromlist=["get_level"]).get_level("A1").skills), {}, rng=__import__("random").Random(5)))
        cap = int(full / quota.DEFAULT_CHARS_PER_TOKEN * 0.75 / settings.ai_quota_margin)
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="INPUT_TOKENS", window="MINUTE", limit=cap)])
        db.commit()
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "READY"
    count = len(klass["exercises"])
    assert settings.ai_class_min_exercises <= count < 6
    turns = [e["conversation"]["turn"] for e in klass["exercises"] if e.get("conversation")]
    assert len(turns) % 2 == 0  # una conversación nunca queda con un turno suelto
    with SessionLocal() as db:
        from app.learning.models import ClassSession

        assert db.get(ClassSession, klass["id"]).generation_request["reducedFrom"] == 6


def test_drop_one_keeps_focus_and_pairs():
    slots = [
        {"skillKey": "a1.grammar.to_be.affirmative", "response": "WRITE"},
        {"skillKey": "a1.vocabulary.home.rooms_furniture", "response": "WRITE"},
        {"skillKey": "a1.conversation.social_basics.greetings", "response": "WRITE", "conversationGroup": "c1"},
        {"skillKey": "a1.conversation.social_basics.introductions", "response": "WRITE", "conversationGroup": "c1"},
        {"skillKey": "a1.writing.about_me.simple_sentences", "response": "WRITE"},
    ]
    from app.classes.generation import _drop_one

    focus = [{"key": "WRITING", "kind": "ability"}]
    smaller = _drop_one(slots, focus, 3)
    # Writing es foco: sale primero la conversación entera (dos turnos), no la escritura.
    assert [s["skillKey"].split(".")[1] for s in smaller] == ["grammar", "vocabulary", "writing"]
    assert _drop_one(smaller, focus, 3) is None  # no baja del mínimo


def test_exam_is_not_created_without_quota(client):
    from app.ai.models import AIConnection
    from app.db import SessionLocal
    from app.learning.models import ClassSession
    from test_exams import _make_eligible

    headers, connection_id = _student(client)
    _make_eligible(client, headers)
    with SessionLocal() as db:
        connection = db.get(AIConnection, connection_id)
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="DAY", limit=1)])
        _usage(db, connection, 1)
        db.commit()
    response = client.post("/api/v1/exams", headers=headers)
    assert response.status_code >= 400
    assert "No hay tokens disponibles para generar el examen" in response.text
    assert "Probá de nuevo después de las" in response.text
    with SessionLocal() as db:
        assert db.scalar(select(ClassSession).where(ClassSession.kind == "EXAM")) is None


def test_batch_size_follows_the_tight_limit(client):
    from app.accounts.models import Account
    from app.ai.models import AIConnection
    from app.db import SessionLocal

    headers, connection_id = _student(client)
    with SessionLocal() as db:
        account = db.scalar(select(Account))
        connection = db.get(AIConnection, connection_id)
        # Sin límites: el tope configurado.
        assert quota.batch_size(db, account, items=9, chars_per_item=1000) == 6
        # Aprietan los PEDIDOS: queda 1 → todo en una sola llamada.
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="MINUTE", limit=3)])
        _usage(db, connection, 1)  # 3 × 0,9 = 2 → queda 1
        assert quota.batch_size(db, account, items=9, chars_per_item=1000) == 9
        # Aprietan los TOKENS: tandas más chicas.
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="REQUESTS", window="MINUTE", limit=1000)])
        quota.record(db, connection, [quota.LimitInfo(kind=RENEWABLE, dimension="TOKENS", window="MINUTE", limit=5000)])
        size = quota.batch_size(db, account, items=9, chars_per_item=1000)
        assert 1 <= size < 6


def test_simulation_script_reduces_class_blocks_exam_and_cleans(client, monkeypatch):
    """scripts/simular_cupo.py: herramienta de prueba manual de T-191 (solo local/dev)."""
    import importlib.util
    import sys
    from pathlib import Path

    from app.ai.models import AIQuotaLimit
    from app.db import SessionLocal
    from test_exams import _make_eligible

    path = Path(__file__).resolve().parent.parent / "scripts" / "simular_cupo.py"
    spec = importlib.util.spec_from_file_location("simular_cupo", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    def run(mode):
        monkeypatch.setattr(sys, "argv", ["simular_cupo.py", mode, "--email", "roberto@example.com"])
        assert script.main() == 0

    headers, _ = _student(client)
    run("clase")
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "READY" and klass["reducedFrom"] > len(klass["exercises"])

    _make_eligible(client, headers)
    run("examen")
    response = client.post("/api/v1/exams", headers=headers)
    assert "No hay tokens disponibles para generar el examen" in response.text

    run("limpiar")
    with SessionLocal() as db:
        assert db.scalar(select(AIQuotaLimit).where(AIQuotaLimit.source == "SIMULATED")) is None


def test_blocked_text_is_simple_and_technical_only_for_owner():
    assert quota.blocked_text("OUTPUT_TOKENS/DAY") == "sin cupo de tokens del día"
    assert quota.blocked_text("REQUESTS/MINUTE", technical=True) == "sin cupo de pedidos del minuto (REQUESTS/MINUTE)"
