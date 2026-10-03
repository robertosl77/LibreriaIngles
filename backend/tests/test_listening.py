"""T-025: Listening como MODALIDAD de presentación, no como tipo de ejercicio.

El mismo tipo (fill_blank, multiple_choice, rewrite...) puede presentarse READ o LISTEN;
la corrección es la misma.
"""

import random

from conftest import login

from app.classes.generation import EVALUATION_MODE_BY_TYPE, _validate_exercise, ensure_listening, slot_for
from app.curriculum.service import EXERCISE_TYPES, get_level
from app.db import SessionLocal
from app.learning.models import Exercise

API = "/api/v1"
SKILL = "a1.grammar.to_be.affirmative"


def _slot(exercise_type: str, presentation: str = "LISTEN", skill: str = SKILL) -> dict:
    return {"skillKey": skill, "allowedTypes": [exercise_type], "presentation": presentation}


def _setup(client) -> dict:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    return headers


def test_no_listening_exercise_types() -> None:
    assert not any(t.startswith("listening") for t in EXERCISE_TYPES)
    assert set(EVALUATION_MODE_BY_TYPE) == EXERCISE_TYPES


def test_listening_comprehension_skills_are_listen_only() -> None:
    level = get_level("A1")
    listen_only = [s for s in level.skills if s.presentations == ("LISTEN",)]
    assert len(listen_only) >= 4
    for skill in listen_only:
        assert set(skill.exercise_types) <= EXERCISE_TYPES
        assert all(e.get("stimulus") for e in skill.examples)
    # El resto de la currícula también se puede escuchar.
    others = [s for s in level.skills if s not in listen_only]
    assert others and all("LISTEN" in s.presentations and "READ" in s.presentations for s in others)


def test_same_type_validates_in_both_presentations() -> None:
    mc = {
        "skillKey": SKILL,
        "type": "multiple_choice",
        "question": "Where is Sarah's family from?",
        "options": ["Spain", "Italy", "Peru"],
        "acceptedAnswers": ["Italy"],
    }
    # READ: sin estímulo, como siempre.
    read = _validate_exercise(mc, _slot("multiple_choice", "READ"))
    assert read is not None and read.stimulus is None
    # LISTEN: el estímulo es obligatorio.
    assert _validate_exercise(mc, _slot("multiple_choice")) is None
    listen = _validate_exercise(
        {**mc, "stimulus": "Sarah's family is from Italy."}, _slot("multiple_choice")
    )
    assert listen is not None and listen.stimulus == "Sarah's family is from Italy."

    # fill_blank LISTEN: la oración con hueco es la misma que se escucha.
    fill = {
        "skillKey": SKILL,
        "type": "fill_blank",
        "question": "My sister ___ a nurse.",
        "stimulus": "My sister is a nurse.",
        "acceptedAnswers": ["is"],
    }
    assert _validate_exercise(fill, _slot("fill_blank")) is not None

    # El estímulo no puede aparecer escrito en la consigna (se respondería sin escuchar).
    rewrite = {
        "skillKey": SKILL,
        "type": "rewrite",
        "instruction": "Make the sentence negative.",
        "question": "They are at home.",
        "stimulus": "They are at home.",
        "acceptedAnswers": ["They are not at home."],
    }
    assert _validate_exercise(rewrite, _slot("rewrite")) is None
    ok = _validate_exercise(
        {**rewrite, "question": "Write the sentence you hear in the negative form."}, _slot("rewrite")
    )
    assert ok is not None


def test_engine_assigns_presentation_and_guarantees_listening() -> None:
    level = get_level("A1")
    rng = random.Random(1)
    grammar = [s for s in level.skills if s.area_key == "grammar"]
    slots = [slot_for(s, rng) for s in grammar[:6]]
    for slot in slots:
        slot["presentation"] = "READ"
    ensure_listening(slots, grammar, 2, rng)
    assert sum(1 for s in slots if s["presentation"] == "LISTEN") == 2
    assert all(s["response"] in ("WRITE", "SELECT") for s in slots)


def test_listening_class_flow_and_ability_progress(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    listened = [e for e in klass["exercises"] if e["presentation"] == "LISTEN"]
    assert listened, "cada clase trae al menos un ejercicio escuchado"
    item = listened[0]
    assert item["type"] in EXERCISE_TYPES
    assert item["stimulus"]["mode"] == "LISTEN" and item["stimulus"]["text"]
    assert item["stimulus"]["lang"] == "en-US" and item["stimulus"]["rate"] == 0.85
    if item["type"].endswith("multiple_choice"):
        assert item["response"] == "SELECT"
    else:
        assert item["response"] in ("WRITE", "SPEAK")

    with SessionLocal() as db:
        answers = {}
        for e in klass["exercises"]:
            exercise = db.get(Exercise, e["id"])
            if exercise.exercise_type == "short_writing":
                answers[str(e["id"])] = "My name is Ana. I live in Rosario and I work in an office."
            elif exercise.exercise_type == "conversation":
                answers[str(e["id"])] = "Hi! I'm Ana. I'm fine, thanks."
            else:
                answers[str(e["id"])] = exercise.answer_key["acceptedAnswers"][0]
    result = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    ).json()
    corrected = next(e for e in result["exercises"] if e["id"] == item["id"])
    assert corrected["result"]["score"] == 100

    progress = client.get(f"{API}/progress", headers=headers).json()
    assert "modalities" not in progress  # reemplazado por habilidades (T-034)
    abilities = {a["key"]: a for a in progress["abilities"]}
    assert abilities["LISTENING"]["evidenceCount"] >= len(listened)
    assert abilities["LISTENING"]["score"] == 100  # sin señales de esfuerzo: sin descuento
    spoken = [e for e in klass["exercises"] if e["response"] == "SPEAK"]
    if spoken:
        assert abilities["SPEAKING"]["evidenceCount"] == len(spoken)
