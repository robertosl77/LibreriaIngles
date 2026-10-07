"""T-183 · Tipos de ejercicio nuevos para A1: validación, armado y corrección por regla."""

import json
import random

import pytest

from app.classes.generation import _validate_exercise, slot_for
from app.classes.types import NEW_TYPES, evaluate_rule_type, format_answer, word_tiles
from app.curriculum.service import get_level
from app.learning.models import EvaluationMode, Exercise, ResponseMode

A1 = get_level("A1")
SKILLS = {s.key: s for s in A1.skills}


def _exercise(kind: str, key: dict, prompt: str = "q") -> Exercise:
    return Exercise(
        id=1,
        level="A1",
        exercise_type=kind,
        prompt=prompt,
        expected_concepts=["c"],
        answer_key=key,
        evaluation_mode=EvaluationMode.DETERMINISTIC,
        response_mode=ResponseMode.WRITE,
    )


def _score(kind, key, answer, **kw):
    result = evaluate_rule_type(_exercise(kind, key, kw.pop("prompt", "q")), answer, **kw)
    return result["_score"], result


# ---------------------------------------------------------------- catálogo y currícula


def test_every_new_type_has_seed_examples_in_a1():
    used = {t for s in A1.skills for t in s.exercise_types}
    assert NEW_TYPES <= used, NEW_TYPES - used


def test_sound_skills_exist_with_lessons():
    from app.curriculum.lessons import get_lesson

    for key in ("a1.listening.sounds.minimal_pairs", "a1.listening.sounds.word_stress"):
        assert key in SKILLS and SKILLS[key].presentations == ("LISTEN",)
        assert get_lesson(key) is not None


# ---------------------------------------------------------------- corrección por regla


def test_dictation_scores_word_by_word():
    key = {"acceptedAnswers": ["Open your book and read page ten.", "Open your book and read page 10."]}
    assert _score("dictation", key, "open your book and read page 10")[0] == 100
    score, result = _score("dictation", key, "Open your bok and read page ten.")
    assert 85 <= score < 100 and result["errors"][0]["type"] == "SPELLING_ERROR"
    score, result = _score("dictation", key, "Open the book and read")
    assert 35 <= score < 85 and result["result"] == "partially_correct"
    assert _score("dictation", key, "I like pizza")[0] < 35


def test_read_aloud_tolerates_sounds_alike():
    key = {"acceptedAnswers": ["I think it is very good."]}
    assert _score("read_aloud", key, "i think it is very good", spoken=True)[0] == 100
    score, result = _score("read_aloud", key, "I sink it is very good", spoken=True)
    assert 85 <= score < 100 and result["errors"][0]["type"] == "PRONUNCIATION_ERROR"


def test_word_order_exact_or_partial():
    key = {"acceptedAnswers": ["I drink coffee every day.", "Every day I drink coffee."]}
    assert _score("word_order", key, "every day I drink coffee")[0] == 100
    near, _ = _score("word_order", key, "I drink every coffee day")
    assert 0 < near < 85
    assert _score("word_order", key, "day coffee every drink I")[0] == 0


def test_word_stress_is_case_sensitive():
    key = {"acceptedAnswers": ["ba-NA-na"]}
    assert _score("word_stress", key, "ba-NA-na")[0] == 100
    assert _score("word_stress", key, "BA-na-na")[0] == 0


def test_match_pairs_counts_pairs():
    key = {"pairs": {"kitchen": "cocina", "bedroom": "dormitorio", "bathroom": "baño", "garden": "jardín"}}
    full = json.dumps(key["pairs"])
    assert _score("match_pairs", key, full)[0] == 100
    half = json.dumps({"kitchen": "cocina", "bedroom": "dormitorio", "bathroom": "jardín", "garden": "baño"})
    score, result = _score("match_pairs", key, half)
    assert score == 50 and len(result["errors"]) == 2
    assert _score("match_pairs", key, "not json")[0] == 0


def test_listen_form_accepts_variants_and_typos():
    key = {"fields": {"Name": ["Tom Green", "Tom"], "Age": ["32", "thirty-two"], "City": ["Madrid"]}}
    assert _score("listen_form", key, json.dumps({"Name": "tom", "Age": "thirty-two", "City": "Madrid"}))[0] == 100
    score, _ = _score("listen_form", key, json.dumps({"Name": "Tom Green", "Age": "32", "City": "Madird"}))
    assert 85 <= score < 100
    assert _score("listen_form", key, json.dumps({"Name": "Ana", "Age": "", "City": "Rome"}))[0] == 0


def test_gap_text_per_gap():
    key = {"gaps": [["get"], ["have"], ["go"]]}
    assert _score("gap_text", key, json.dumps(["get", "have", "go"]))[0] == 100
    score, result = _score("gap_text", key, json.dumps(["get", "has", "go"]))
    assert round(score) == 67 and result["errors"][0]["correction"] == "have"


def test_format_answer_is_readable():
    assert format_answer("gap_text", '["get", "have"]') == "get · have"
    assert format_answer("match_pairs", '{"red": "rojo"}') == "red = rojo"
    assert format_answer("dictation", "hello") == "hello"


# ---------------------------------------------------------------- validación de lo que genera la IA


def _slot(kind, presentation="READ", skill="a1.grammar.to_be.affirmative"):
    return {"skillKey": skill, "allowedTypes": [kind], "presentation": presentation}


def _raw(kind, **fields):
    return {"skillKey": "a1.grammar.to_be.affirmative", "type": kind, "instruction": "i", "question": "q", **fields}


def test_word_order_drops_variants_with_other_words():
    item = _validate_exercise(
        _raw("word_order", acceptedAnswers=["I drink coffee every day.", "Every day I drink coffee.", "I drink tea every day."]),
        _slot("word_order"),
    )
    assert item.acceptedAnswers == ["I drink coffee every day.", "Every day I drink coffee."]
    assert _validate_exercise(_raw("word_order", acceptedAnswers=["Hi there"]), _slot("word_order")) is None


def test_match_pairs_needs_unique_pairs():
    pairs = [["red", "rojo"], ["green", "verde"], ["blue", "azul"]]
    assert _validate_exercise(_raw("match_pairs", pairs=pairs), _slot("match_pairs")) is not None
    dup = pairs + [["red", "colorado"]]
    assert _validate_exercise(_raw("match_pairs", pairs=dup), _slot("match_pairs")) is None


def test_gap_text_blanks_must_match_gaps_and_bank():
    ok = _raw("gap_text", passage="I ___ up. I ___ tea.", gaps=[["get"], ["drink"]], options=["get", "drink", "go"])
    assert _validate_exercise(ok, _slot("gap_text")) is not None
    wrong_count = _raw("gap_text", passage="I ___ up.", gaps=[["get"], ["drink"]])
    assert _validate_exercise(wrong_count, _slot("gap_text")) is None
    not_in_bank = _raw("gap_text", passage="I ___ up. I ___ tea.", gaps=[["get"], ["drink"]], options=["get", "go"])
    assert _validate_exercise(not_in_bank, _slot("gap_text")) is None


def test_error_correction_question_must_be_wrong():
    good = _raw("error_correction", question="She go to school.", acceptedAnswers=["She goes to school."])
    assert _validate_exercise(good, _slot("error_correction")) is not None
    already_ok = _raw("error_correction", question="She goes to school.", acceptedAnswers=["She goes to school."])
    assert _validate_exercise(already_ok, _slot("error_correction")) is None


def test_listen_types_need_listen_and_may_repeat_stimulus():
    raw = _raw("minimal_pairs", stimulus="sheep", options=["ship", "sheep"], acceptedAnswers=["sheep"])
    assert _validate_exercise(raw, _slot("minimal_pairs", "LISTEN")) is not None
    form = _raw("listen_form", stimulus="I'm Tom. I'm ten.", fields=[{"label": "Name", "acceptedAnswers": ["Tom"]}, {"label": "Age", "acceptedAnswers": ["10", "ten"]}])
    assert _validate_exercise(form, _slot("listen_form", "LISTEN")) is not None
    assert _validate_exercise(form, _slot("listen_form", "READ")) is None


def test_word_stress_options_differ_only_in_case():
    raw = _raw("word_stress", stimulus="banana", options=["BA-na-na", "ba-NA-na", "ba-na-NA"], acceptedAnswers=["ba-NA-na"])
    item = _validate_exercise(raw, _slot("word_stress", "LISTEN"))
    assert item is not None and item.acceptedAnswers == ["ba-NA-na"]


# ---------------------------------------------------------------- armado de la clase


def test_word_tiles_are_shuffled_and_complete():
    tiles = word_tiles("My sister lives in a small house.")
    assert sorted(tiles) == sorted(["my", "sister", "lives", "in", "a", "small", "house"])
    assert tiles != ["my", "sister", "lives", "in", "a", "small", "house"]


def test_read_aloud_only_with_audio_and_fixed_presentations():
    skill = SKILLS["a1.conversation.social_basics.greetings"]
    rng = random.Random(1)
    for _ in range(30):
        assert slot_for(skill, rng, allow_speaking=False)["allowedTypes"] != ["read_aloud"]
    slot = slot_for(skill, rng, allow_speaking=True, types={"read_aloud"})
    assert slot["presentation"] == "READ" and slot["response"] == "SPEAK"
    dictation = slot_for(SKILLS["a1.listening.everyday_audio.instructions"], rng, types={"dictation"})
    assert dictation["presentation"] == "LISTEN" and dictation["response"] == "WRITE"


NEW_TYPE_SKILLS = [
    ("a1.listening.everyday_audio.instructions", "dictation"),
    ("a1.writing.sentence_building.word_order", "word_order"),
    ("a1.conversation.social_basics.greetings", "dialogue_choice"),
    ("a1.conversation.social_basics.introductions", "read_aloud"),
    ("a1.listening.sounds.minimal_pairs", "minimal_pairs"),
    ("a1.vocabulary.home.rooms_furniture", "match_pairs"),
    ("a1.listening.everyday_audio.personal_info", "listen_form"),
    ("a1.reading.short_texts.comprehension", "gap_text"),
    ("a1.grammar.articles.a_an", "error_correction"),
    ("a1.listening.sounds.word_stress", "word_stress"),
]


@pytest.fixture
def all_types_class(client, monkeypatch):
    from app.classes import generation
    from conftest import login

    def forced(*args, **kwargs):
        rng = random.Random(3)
        return [slot_for(SKILLS[key], rng, allow_speaking=True, types={kind}) for key, kind in NEW_TYPE_SKILLS]

    monkeypatch.setattr(generation, "select_slots", forced)
    headers = login(client)
    assert client.put("/api/v1/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    client.post(
        "/api/v1/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    klass = client.post("/api/v1/classes", headers=headers).json()
    assert klass["status"] == "READY", klass
    return headers, klass


def test_class_with_all_new_types_is_corrected_without_ai(client, all_types_class):
    from sqlalchemy import select

    from app.ai.models import AIUsageEvent
    from app.db import SessionLocal
    from conftest import correct_answer

    headers, klass = all_types_class
    by_type = {e["type"]: e for e in klass["exercises"]}
    assert set(by_type) == {kind for _, kind in NEW_TYPE_SKILLS}
    # Lo que arma el backend llega al frontend; la answer key no.
    assert by_type["word_order"]["tiles"] and by_type["match_pairs"]["pairs"]["right"]
    assert by_type["listen_form"]["fields"] and by_type["listen_form"]["presentation"] == "LISTEN"
    assert by_type["read_aloud"]["response"] == "SPEAK"
    assert by_type["word_stress"]["response"] == "SELECT"
    assert "acceptedAnswers" not in json.dumps(klass) and "gaps" not in json.dumps(klass)

    with SessionLocal() as db:
        answers = {str(e["id"]): correct_answer(db.get(Exercise, e["id"])) for e in klass["exercises"]}
    result = client.post(f"/api/v1/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers).json()
    assert result["status"] == "COMPLETED"
    assert all(e["result"]["score"] == 100 for e in result["exercises"]), [
        (e["type"], e["result"]["score"]) for e in result["exercises"]
    ]
    with SessionLocal() as db:
        operations = [e.operation for e in db.scalars(select(AIUsageEvent)).all() if e.operation != "health_check"]
    assert operations == ["generate_class"]  # cero tokens al corregir


def test_new_rule_types_cannot_be_appealed(client, all_types_class):
    headers, klass = all_types_class
    answers = {str(e["id"]): ("[]" if e["type"] == "gap_text" else "zzz") for e in klass["exercises"]}
    result = client.post(f"/api/v1/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers).json()
    by_type = {e["type"]: e for e in result["exercises"]}
    assert by_type["match_pairs"]["result"]["canAppeal"] is False
    assert by_type["dictation"]["result"]["canAppeal"] is False
    assert by_type["error_correction"]["result"]["canAppeal"] is True  # usa IA al apelar
    response = client.post(
        f"/api/v1/classes/{klass['id']}/exercises/{by_type['match_pairs']['id']}/appeal", headers=headers
    )
    assert response.status_code == 409
