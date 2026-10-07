"""T-168 · Eficiencia de IA en clases (razonamiento, JSON compacto, catálogo, esquema, lote, reglas)."""

import json

import pytest

from app.ai import providers
from app.ai.providers import gemini_generation_config, reasoning_budget
from app.classes.prompts import evaluation_user_prompt, generation_user_prompt
from app.core.config import settings


@pytest.fixture
def efficiency_on(monkeypatch):
    monkeypatch.setattr(settings, "ai_reasoning_control", True)
    monkeypatch.setattr(settings, "ai_reasoning_budget_open", 512)
    monkeypatch.setattr(settings, "ai_response_schema", True)


# ---------------------------------------------------------------- T-169 razonamiento


def test_reasoning_budget_by_task(efficiency_on):
    assert reasoning_budget({"kind": "generate_class"}) == 0
    assert reasoning_budget({"kind": "transcribe_audio"}) == 0
    assert reasoning_budget({"kind": "evaluate_answer", "exercise": {"type": "fill_blank"}}) == 0
    assert reasoning_budget({"kind": "evaluate_answer", "exercise": {"type": "rewrite"}}) == 0
    assert reasoning_budget({"kind": "evaluate_answer", "exercise": {"type": "short_writing"}}) == 512
    assert reasoning_budget({"kind": "evaluate_answer", "exercise": {"type": "conversation"}}) == 512
    assert reasoning_budget({"kind": "evaluate_batch", "items": [{"type": "rewrite"}]}) == 0
    assert (
        reasoning_budget({"kind": "evaluate_batch", "items": [{"type": "rewrite"}, {"type": "conversation"}]})
        == 512
    )
    assert reasoning_budget({"kind": "campaign_assist"}) is None


def test_reasoning_control_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "ai_reasoning_control", False)
    assert reasoning_budget({"kind": "generate_class"}) is None
    config = gemini_generation_config("gemini-2.5-flash", {"kind": "generate_class"}, {})
    assert "thinkingConfig" not in config


def test_thinking_config_only_for_gemini_25_flash(efficiency_on):
    task = {"kind": "evaluate_answer", "exercise": {"type": "fill_blank"}}
    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "Gemini-2.5-Flash-preview"):
        assert gemini_generation_config(model, task, {})["thinkingConfig"] == {"thinkingBudget": 0}
    for model in ("gemini-2.5-pro", "gemini-3.5-flash-lite", None):
        assert "thinkingConfig" not in gemini_generation_config(model, task, {})


def test_gemini_ignores_thought_parts(monkeypatch, efficiency_on):
    sent = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "candidates": [{"content": {"parts": [
                    {"text": "thinking...", "thought": True},
                    {"text": '{"ok": true}'},
                ]}}]
            }

    def fake_request(method, url, **kwargs):
        sent.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(providers.httpx, "request", fake_request)
    provider = providers.GeminiProvider("key", "gemini-2.5-flash")
    assert provider.complete_json("sys", "user", {"kind": "generate_class"}) == {"ok": True}
    assert sent["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert sent["generationConfig"]["responseMimeType"] == "application/json"


# ---------------------------------------------------------------- T-174 JSON compacto


def test_prompts_use_compact_json():
    gen = generation_user_prompt("A1", [{"skillKey": "a1.x", "objectives": ["a", "b"]}])
    ev = evaluation_user_prompt({"level": "A1", "studentAnswer": "I am"})
    for text in (gen, ev):
        body = text.split("\n", 1)[1]
        assert "\n" not in body and ": " not in body
        json.loads(body)


# ---------------------------------------------------------------- T-170 catálogo compacto


def test_evaluation_system_carries_level_catalog():
    from app.classes.prompts import EVALUATION_SYSTEM, evaluation_system, skill_catalog

    catalog = skill_catalog("A1")
    assert "grammar.to_be.negative: To be · Negativo" in catalog
    assert "objectives" not in catalog and "a1." not in catalog
    assert not any(line.startswith(("listening.", "reading.", "conversation.")) for line in catalog.splitlines())
    system = evaluation_system("A1")
    assert system.startswith(EVALUATION_SYSTEM) and catalog in system
    assert evaluation_system("A1") is system  # mismo texto en cada llamada (prefijo cacheable)
    assert evaluation_system("Z9") == EVALUATION_SYSTEM


class _Mode:
    def __init__(self, value):
        self.value = value


class _Exercise:
    level = "A1"
    skill_key = "a1.conversation.social_basics.greetings"
    response_mode = _Mode("WRITE")


def test_secondary_areas_and_short_keys():
    from app.classes import evaluation

    ex = _Exercise()
    assert evaluation._secondary_areas(ex) == ["grammar", "vocabulary", "writing"]
    ex.response_mode = _Mode("SPEAK")
    assert evaluation._secondary_areas(ex) == ["grammar", "vocabulary"]
    ex.response_mode = _Mode("SELECT")
    assert evaluation._secondary_areas(ex) == []

    ex.response_mode = _Mode("WRITE")
    data = {"secondarySkillResults": [
        {"skillKey": "grammar.to_be.affirmative", "status": "correct", "score": 95},
        {"skillKey": "a1.vocabulary.daily_life.family", "status": "partially_correct", "score": 60},
        {"skillKey": "listening.everyday_audio.instructions", "status": "correct"},  # área no permitida
        {"skillKey": "conversation.social_basics.greetings", "status": "correct"},  # la principal
    ]}
    keys = [r["skillKey"] for r in evaluation._sanitize_secondary(ex, data)]
    assert keys == ["a1.grammar.to_be.affirmative", "a1.vocabulary.daily_life.family"]


# ---------------------------------------------------------------- T-173 esquema


def test_response_schema_only_when_enabled(monkeypatch, efficiency_on):
    from app.classes.prompts import EVALUATION_SCHEMA

    task = {"kind": "evaluate_answer", "exercise": {"type": "rewrite"}, "schema": EVALUATION_SCHEMA}
    config = gemini_generation_config("gemini-2.5-flash", task, {"responseMimeType": "application/json"})
    assert config["responseSchema"] is EVALUATION_SCHEMA
    # Transcripción en texto plano: nunca lleva esquema.
    assert "responseSchema" not in gemini_generation_config("gemini-2.5-flash", task, {"temperature": 0})
    monkeypatch.setattr(settings, "ai_response_schema", False)
    assert "responseSchema" not in gemini_generation_config(
        "gemini-2.5-flash", task, {"responseMimeType": "application/json"}
    )


def test_schemas_use_gemini_types_only():
    from app.classes.prompts import EVALUATION_BATCH_SCHEMA, GENERATION_SCHEMA

    allowed = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}

    def walk(node):
        assert node["type"] in allowed
        for child in (node.get("properties") or {}).values():
            walk(child)
        if "items" in node:
            walk(node["items"])
        for key in node.get("required") or []:
            assert key in node["properties"]

    for schema in (GENERATION_SCHEMA, EVALUATION_BATCH_SCHEMA):
        walk(schema)


# ---------------------------------------------------------------- T-172 reglas primero


def _closed_exercise(exercise_type: str, accepted: list[str], prompt: str):
    from app.learning.models import EvaluationMode, Exercise, ResponseMode

    return Exercise(
        id=1,
        level="A1",
        area="grammar",
        skill_key="a1.grammar.to_be.negative",
        exercise_type=exercise_type,
        prompt=prompt,
        expected_concepts=["be_negative"],
        answer_key={"acceptedAnswers": accepted, "commonErrors": []},
        evaluation_mode=EvaluationMode.HYBRID,
        response_mode=ResponseMode.WRITE,
    )


class _NoCacheDb:
    def scalar(self, *args, **kwargs):
        return None


def test_fill_blank_mismatch_is_decided_by_rule(monkeypatch):
    from app.classes.evaluation import CLOSED_RULE_FEEDBACK, evaluate_without_ai
    from app.learning.models import EvaluationSource

    monkeypatch.setattr(settings, "ai_rule_first_closed", True)
    ex = _closed_exercise("fill_blank", ["aren't", "are not"], "My parents ___ at work today.")
    ev = evaluate_without_ai(_NoCacheDb(), ex, "is")
    assert ev.source == EvaluationSource.RULE_MATCH and ev.score == 0.0
    assert ev.result["feedback"] == CLOSED_RULE_FEEDBACK
    # Hablada: la transcripción puede tener ruido, decide la IA.
    assert evaluate_without_ai(_NoCacheDb(), ex, "is", spoken=True) is None
    # Apagado: vuelve a la IA como antes.
    monkeypatch.setattr(settings, "ai_rule_first_closed", False)
    assert evaluate_without_ai(_NoCacheDb(), ex, "is") is None


def test_rewrite_far_is_rule_near_goes_to_ai(monkeypatch):
    from app.classes.evaluation import evaluate_without_ai

    monkeypatch.setattr(settings, "ai_rule_first_closed", True)
    ex = _closed_exercise("rewrite", ["They are not at home.", "They aren't at home."], "They are at home.")
    far = evaluate_without_ai(_NoCacheDb(), ex, "I like pizza very much")
    assert far is not None and far.score == 0.0
    # Comparte la mayoría de las palabras: puede ser una variante válida → IA.
    assert evaluate_without_ai(_NoCacheDb(), ex, "They is not at home.") is None
    # Lo que ya coincide sigue siendo correcto por regla.
    assert evaluate_without_ai(_NoCacheDb(), ex, "they aren't at home").score == 100.0


# ---------------------------------------------------------------- T-171 lote


def _forced_slots():
    import random

    from app.classes.generation import pair_conversation_slots, slot_for
    from app.curriculum.service import get_level

    rng = random.Random(7)
    skills = {s.key: s for s in get_level("A1").skills}
    chosen = [
        skills["a1.grammar.to_be.negative"],
        skills["a1.writing.about_me.simple_sentences"],
        skills["a1.conversation.social_basics.greetings"],
        skills["a1.conversation.social_basics.introductions"],
    ]
    slots = [slot_for(skill, rng) for skill in chosen]
    slots[0]["allowedTypes"] = ["fill_blank"]
    slots[0]["example"] = next(e for e in chosen[0].examples if e["type"] == "fill_blank")
    slots[0]["examples"] = [slots[0]["example"]]
    for slot in slots:
        slot["presentation"], slot["response"] = "READ", "WRITE"
    pair_conversation_slots(slots)
    return slots


def _run_class(client, monkeypatch, *, batch: bool) -> list[str]:
    from sqlalchemy import select

    from app.ai.models import AIUsageEvent
    from app.classes import generation
    from app.db import SessionLocal
    from conftest import login

    monkeypatch.setattr(settings, "ai_batch_evaluation", batch)
    monkeypatch.setattr(generation, "select_slots", lambda *a, **k: _forced_slots())
    headers = login(client)
    assert client.put("/api/v1/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    client.post(
        "/api/v1/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "READY", klass
    answers = {
        str(e["id"]): ("zzz-wrong" if e["type"] == "fill_blank" else "Hello! I am fine, thank you. I live in Buenos Aires with my family.")
        for e in klass["exercises"]
    }
    result = client.post(f"/api/v1/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers).json()
    assert result["status"] == "COMPLETED", result
    assert all(e["result"] is not None for e in result["exercises"])
    with SessionLocal() as db:
        return [
            e.operation
            for e in db.scalars(select(AIUsageEvent).where(AIUsageEvent.operation.like("evaluate%"))).all()
        ]


def test_class_with_several_open_answers_is_corrected_in_one_call(client, monkeypatch):
    operations = _run_class(client, monkeypatch, batch=True)
    # 1 short_writing + 2 turnos de conversación en una sola llamada; el fill_blank fue por regla.
    assert operations == ["evaluate_batch"]


def test_batch_can_be_turned_off(client, monkeypatch):
    operations = _run_class(client, monkeypatch, batch=False)
    assert operations == ["evaluate_answer"] * 3


def test_missing_batch_result_falls_back_to_single_call(client, monkeypatch):
    from app.ai import mock

    original = mock.MockProvider.complete_json

    def drop_one(self, system, user, task):
        data = original(self, system, user, task)
        if task.get("kind") == "evaluate_batch":
            data["results"] = data["results"][1:]
        return data

    monkeypatch.setattr(mock.MockProvider, "complete_json", drop_one)
    operations = _run_class(client, monkeypatch, batch=True)
    assert sorted(operations) == ["evaluate_answer", "evaluate_batch"]


# ---------------------------------------------------------------- segunda tanda (T-178 a T-181)


def test_prompt_example_is_compact(monkeypatch):
    from app.classes.generation import _prompt_example, _public_slot

    example = {
        "type": "fill_blank",
        "instruction": "Complete.",
        "question": "My sister ___ a nurse.",
        "passage": "long text " * 20,
        "acceptedAnswers": ["is", "'s", "is really", "is truly"],
        "commonErrors": [
            {"answer": "are", "feedback": "Con she se usa is.", "conceptResults": [{"concept": "x", "status": "incorrect"}]},
            {"answer": "am", "feedback": "No."},
        ],
        "expectedConcepts": ["be_agreement"],
    }
    monkeypatch.setattr(settings, "ai_compact_examples", True)
    compact = _prompt_example(example)
    assert "passage" not in compact
    assert compact["acceptedAnswers"] == ["is", "'s", "is really"]
    assert compact["commonErrors"] == [{"answer": "are", "feedback": "Con she se usa is."}]
    public = _public_slot({"skillKey": "k", "example": example, "examples": [example]})
    assert "examples" not in public and public["example"] == compact
    monkeypatch.setattr(settings, "ai_compact_examples", False)
    assert _prompt_example(example) is example


def test_cached_input_tokens_by_provider():
    from app.ai.providers import cached_input_tokens

    assert cached_input_tokens({"usageMetadata": {"promptTokenCount": 3000, "cachedContentTokenCount": 2048}}) == 2048
    assert cached_input_tokens({"usageMetadata": {"promptTokenCount": 3000}}) == 0
    assert cached_input_tokens({"usage": {"prompt_tokens_details": {"cached_tokens": 1024}}}) == 1024
    assert cached_input_tokens({"usage": {"cache_read_input_tokens": 512, "input_tokens": 900}}) == 512
    assert cached_input_tokens({"usage": {"input_tokens": 120}}) is None
    assert cached_input_tokens(None) is None


def test_evaluation_output_is_trimmed():
    from app.classes.prompts import EVALUATION_BATCH_SCHEMA, EVALUATION_SCHEMA, EVALUATION_SYSTEM

    assert "scoreSuggested" not in EVALUATION_SYSTEM
    assert "scoreSuggested" not in EVALUATION_SCHEMA["properties"]
    assert "scoreSuggested" not in EVALUATION_BATCH_SCHEMA["properties"]["results"]["items"]["properties"]
    assert "at most 2 suggestions" in EVALUATION_SYSTEM


def test_batch_is_split_by_max_items(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_batch_max_items", 2)
    operations = _run_class(client, monkeypatch, batch=True)
    # 3 respuestas para IA con máximo 2: un lote de 2 + la restante individual.
    assert sorted(operations) == ["evaluate_answer", "evaluate_batch"]
