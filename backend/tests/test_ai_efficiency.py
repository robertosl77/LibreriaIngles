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
