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
    assert slots[1]["response"] == "WRITE"  # T-207: completar una palabra nunca se habla
    assert slots[2]["response"] == "SPEAK"
    assert all(slot["allowedTypes"][0] != "speaking_prompt" for slot in slots)


def test_audio_is_transcribed_to_draft_and_never_persisted(client, monkeypatch) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()

    with SessionLocal() as db:
        exercises = db.scalars(
            select(Exercise).where(Exercise.class_session_id == klass["id"])
        ).all()
        exercise = next(
            item
            for item in exercises
            if item.exercise_type in {"fill_blank", "rewrite", "short_writing", "conversation"}
        )
        exercise.response_mode = ResponseMode.SPEAK
        expected = (
            exercise.answer_key["acceptedAnswers"][0]
            if exercise.answer_key.get("acceptedAnswers")
            else "I live in Buenos Aires and I work every day."
        )
        exercise_id = exercise.id
        db.commit()

    expected_pronunciation = {
        "score": 82,
        "words": [{"word": "hello", "score": 91}],
        "phonemes": [{"phoneme": "h", "word": "hello", "score": 94}],
        "fluency": None,
        "provider": "GEMINI",
        "estimated": True,
        "assessedAt": "2026-10-01T00:00:00+00:00",
    }
    monkeypatch.setattr(
        "app.classes.api.normalize_ai_pronunciation",
        lambda *args, **kwargs: expected_pronunciation,
    )

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
    assert response.json()["pronunciationResult"] == expected_pronunciation

    with SessionLocal() as db:
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
        assert draft is not None
        assert draft.answer_text == expected
        assert draft.audio_duration_ms == 2400
        assert draft.pronunciation_result == expected_pronunciation

    detail = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    answers = {str(item["id"]): item["answer"] for item in detail["exercises"]}
    result = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    )
    assert result.status_code == 200
    completed_exercise = next(
        item for item in result.json()["exercises"] if item["id"] == exercise_id
    )
    assert completed_exercise["pronunciationResult"] == expected_pronunciation

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
        assert attempt.pronunciation_result == expected_pronunciation
        # No existe columna/blob de audio: solo resultados derivados.
        assert not hasattr(attempt, "audio")


def test_pronunciation_result_is_null_when_service_is_unavailable(client, monkeypatch) -> None:
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
        exercise_id = exercise.id
        db.commit()

    from app.ai.mock import MockProvider
    from app.ai.providers import SpeechAnalysis

    # Proveedor que transcribe pero no estima pronunciación (como OpenAI).
    monkeypatch.setattr(
        MockProvider,
        "analyze_speech",
        lambda self, audio, mime_type: SpeechAnalysis(audio.decode("utf-8"), None),
    )
    response = client.post(
        f"{API}/classes/{klass['id']}/answers/{exercise_id}/transcribe",
        content=b"I work every day",
        headers={
            **headers,
            "content-type": "audio/webm",
            "x-audio-duration-ms": "1800",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["pronunciationResult"] is None

    with SessionLocal() as db:
        draft = db.scalar(select(DraftAnswer).where(DraftAnswer.exercise_id == exercise_id))
        assert draft is not None
        assert draft.pronunciation_result is None
        assert not hasattr(draft, "audio")


def test_single_word_fill_blank_is_never_spoken() -> None:
    """T-207: completar una palabra va por texto aunque la clase tenga habla habilitada."""
    import random

    from app.classes.generation import select_slots, slot_for
    from app.curriculum.service import get_level

    skills = list(get_level("A1").skills)
    fill = [s for s in skills if "fill_blank" in s.exercise_types]
    rng = random.Random(1)
    for _ in range(200):
        slot = slot_for(rng.choice(fill), rng, allow_speaking=True, types={"fill_blank"})
        assert slot["response"] != "SPEAK"
    for seed in range(40):
        slots = select_slots(skills, {}, allow_speaking=True,
                             focus=[{"key": "SPEAKING", "kind": "ability"}], rng=random.Random(seed))
        assert not any(s["allowedTypes"][0] == "fill_blank" and s["response"] == "SPEAK" for s in slots)
        assert any(s["response"] == "SPEAK" for s in slots)  # el habla se cubre con otros tipos


def test_slow_transcription_does_not_freeze_other_requests(client, monkeypatch) -> None:
    """T-211 (#258): mientras la IA transcribe, otra pestaña (GET /me) sigue respondiendo."""
    import threading
    import time

    from app.ai.mock import MockProvider

    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    with SessionLocal() as db:
        exercise = next(
            e for e in db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"])).all()
            if e.exercise_type in {"rewrite", "short_writing", "conversation", "fill_blank"}
        )
        exercise.response_mode = ResponseMode.SPEAK
        exercise_id = exercise.id
        db.commit()

    real = MockProvider.transcribe_audio

    def slow(self, *args, **kwargs):
        time.sleep(1.5)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(MockProvider, "transcribe_audio", slow)
    result = {}

    def speak():
        result["r"] = client.post(
            f"{API}/classes/{klass['id']}/answers/{exercise_id}/transcribe",
            content=b"hello", headers={**headers, "content-type": "audio/webm", "x-audio-duration-ms": "900"},
        )

    worker = threading.Thread(target=speak)
    worker.start()
    time.sleep(0.3)
    started = time.monotonic()
    assert client.get(f"{API}/me", headers=headers).status_code == 200
    elapsed = time.monotonic() - started
    worker.join()
    assert result["r"].status_code == 200, result["r"].text
    assert elapsed < 1.0  # antes: esperaba los 1,5 s de la transcripción
