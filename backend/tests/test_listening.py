"""T-025: ejercicios de listening (voz sintética del navegador)."""

from conftest import login

from app.classes.generation import _validate_exercise
from app.curriculum.service import LISTENING_TYPES, get_level
from app.db import SessionLocal
from app.learning.models import Exercise

API = "/api/v1"


def _slot(exercise_type: str) -> dict:
    return {"skillKey": "a1.listening.everyday_audio.numbers_times", "allowedTypes": [exercise_type]}


def test_a1_has_listening_area_with_seeds_and_lessons() -> None:
    skills = [s for s in get_level("A1").skills if s.area_key == "listening"]
    assert len(skills) >= 4
    for skill in skills:
        assert set(skill.exercise_types) <= LISTENING_TYPES
        assert skill.examples and all(e.get("audioText") for e in skill.examples)


def test_listening_validation_requires_audio_text() -> None:
    base = {
        "skillKey": "a1.listening.everyday_audio.numbers_times",
        "type": "listening_multiple_choice",
        "question": "How much is the coffee?",
        "options": ["$3", "$5", "$8"],
        "acceptedAnswers": ["$3"],
    }
    assert _validate_exercise(base, _slot("listening_multiple_choice")) is None
    ok = _validate_exercise({**base, "audioText": "The coffee is three dollars."}, _slot("listening_multiple_choice"))
    assert ok is not None and ok.audioText == "The coffee is three dollars."

    fill = {
        "skillKey": "a1.listening.everyday_audio.numbers_times",
        "type": "listening_fill_blank",
        "question": "The train leaves at ___.",
        "audioText": "The train leaves at half past eight.",
        "acceptedAnswers": ["half past eight", "8:30"],
    }
    assert _validate_exercise(fill, _slot("listening_fill_blank")) is not None
    assert _validate_exercise({**fill, "question": "The train leaves at eight."}, _slot("listening_fill_blank")) is None
    # En otros tipos el audio se descarta.
    other = _validate_exercise(
        {**fill, "type": "fill_blank", "skillKey": "a1.listening.everyday_audio.numbers_times"},
        {"skillKey": "a1.listening.everyday_audio.numbers_times", "allowedTypes": ["fill_blank"]},
    )
    assert other is not None and other.audioText is None


def test_listening_exercise_flow(client) -> None:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    # Generar clases hasta que aparezca un ejercicio de listening.
    klass, item = None, None
    for _ in range(15):
        klass = client.post(f"{API}/classes", headers=headers).json()
        item = next((e for e in klass["exercises"] if e["type"] in LISTENING_TYPES), None)
        if item:
            break
    assert item is not None, "ninguna clase trajo listening"
    assert item["audio"]["text"] and item["audio"]["lang"] == "en-US"
    assert item["audio"]["rate"] == 0.85
    assert item["area"] == "listening"
    assert item["hasLesson"] is True

    with SessionLocal() as db:
        answer = db.get(Exercise, item["id"]).answer_key["acceptedAnswers"][0]
    result = client.post(
        f"{API}/classes/{klass['id']}/submit",
        json={"answers": {str(item["id"]): answer}},
        headers=headers,
    ).json()
    corrected = next(e for e in result["exercises"] if e["id"] == item["id"])
    assert corrected["result"]["score"] == 100
    assert corrected["audio"]["text"]

    progress = client.get(f"{API}/progress", headers=headers).json()
    area = next(a for a in progress["areas"] if a["key"] == "listening")
    assert area["name"] == "Listening"
    assert area["attemptCount"] >= 1
