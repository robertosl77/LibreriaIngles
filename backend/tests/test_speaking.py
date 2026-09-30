"""T-026: SPEAK es modalidad de respuesta sobre los ejercicios existentes."""

from conftest import login
from sqlalchemy import select

from app.ai.providers import PROVIDERS
from app.classes.generation import ensure_speaking
from app.db import SessionLocal
from app.learning.models import Attempt, DraftAnswer, Exercise, ResponseMode

API = "/api/v1"


def _setup(client) -> dict:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Audio simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    return headers


def test_provider_audio_capabilities() -> None:
    assert PROVIDERS["OPENAI"].supports_audio_input
    assert PROVIDERS["GEMINI"].supports_audio_input
    assert PROVIDERS["MOCK"].supports_audio_input
    assert not PROVIDERS["ANTHROPIC"].supports_audio_input


def test_speaking_keeps_existing_exercise_types() -> None:
    slots = [
        {"allowedTypes": ["multiple_choice"], "response": "SELECT"},
        {"allowedTypes": ["fill_blank"], "response": "WRITE"},
        {"allowedTypes": ["rewrite"], "response": "WRITE"},
    ]

    class _Rng:
        def shuffle(self, values):
            return None

    ensure_speaking(slots, 1, _Rng())
    assert slots[0]["response"] == "SELECT"
    assert slots[1]["response"] == "SPEAK"
    assert all(slot["allowedTypes"][0] != "speaking_prompt" for slot in slots)


def test_audio_is_transcribed_to_draft_and_never_persisted(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()

    with SessionLocal() as db:
        exercises = db.scalars(
            select(Exercise).where(Exercise.class_session_id == klass["id"])
        ).all()
        exercise = next(
            item
            for item in exercises
            if item.exercise_type in {"fill_blank", "rewrite", "short_writing"}
        )
        exercise.response_mode = ResponseMode.SPEAK
        expected = (
            exercise.answer_key["acceptedAnswers"][0]
            if exercise.answer_key.get("acceptedAnswers")
            else "I live in Buenos Aires and I work every day."
        )
        exercise_id = exercise.id
        db.commit()

    response = client.post(
        f"{API}/classes/{klass['id']}/answers/{exercise_id}/transcribe",
        content=expected.encode("utf-8"),
        headers={
            **headers,
            "content-type": "audio/webm",
            "x-audio-duration-ms": "2400",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["transcript"] == expected

    with SessionLocal() as db:
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
        assert draft is not None
        assert draft.answer_text == expected
        assert draft.audio_duration_ms == 2400

    detail = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    answers = {str(item["id"]): item["answer"] for item in detail["exercises"]}
    result = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    )
    assert result.status_code == 200

    with SessionLocal() as db:
        attempt = db.scalar(
            select(Attempt)
            .where(Attempt.exercise_id == exercise_id)
            .order_by(Attempt.id.desc())
        )
        assert attempt is not None
        assert attempt.response_mode == ResponseMode.SPEAK
        assert attempt.raw_answer == expected
        assert attempt.audio_duration_ms == 2400
        # No existe columna/blob de audio: solo transcripción + duración.
        assert not hasattr(attempt, "audio")
