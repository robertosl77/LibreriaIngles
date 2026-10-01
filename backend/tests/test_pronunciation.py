"""T-027: pronunciación estimada por IA en la misma llamada que transcribe."""

import json

import httpx
from conftest import login
from sqlalchemy import select

from app.ai.providers import GeminiProvider, OpenAIProvider, SpeechAnalysis
from app.db import SessionLocal
from app.learning.models import Exercise, ResponseMode
from app.pronunciation import normalize_ai_pronunciation

API = "/api/v1"


def test_normalize_validates_and_clamps() -> None:
    raw = {
        "score": 104,
        "words": [{"word": "think", "score": 35.6}, {"word": "", "score": 90}, {"word": "so", "score": "x"}],
        "phonemes": [{"phoneme": "θ", "word": "think", "score": -5}, "basura"],
        "fluency": "70",
    }
    result = normalize_ai_pronunciation(raw, "I think so", "GEMINI")
    assert result["score"] == 100
    assert result["words"] == [{"word": "think", "score": 36}]
    assert result["phonemes"] == [{"phoneme": "θ", "word": "think", "score": 0}]
    assert result["fluency"] == 70
    assert result["provider"] == "GEMINI" and result["estimated"] is True
    assert result["assessedAt"]


def test_normalize_returns_none_without_valid_score() -> None:
    assert normalize_ai_pronunciation(None, "hello", "GEMINI") is None
    assert normalize_ai_pronunciation({"words": []}, "hello", "GEMINI") is None
    assert normalize_ai_pronunciation({"score": 80}, "   ", "GEMINI") is None


def _gemini_response(text: str) -> httpx.Response:
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "https://x"))


def test_gemini_returns_transcript_and_pronunciation_in_one_call(monkeypatch) -> None:
    calls = []
    payload = {"transcript": "He do his homework", "pronunciation": {"score": 77, "words": [], "phonemes": [], "fluency": 70}}

    def fake(method, url, **kwargs):
        calls.append(kwargs["json"])
        return _gemini_response(json.dumps(payload))

    monkeypatch.setattr("app.ai.providers.httpx.request", fake)
    analysis = GeminiProvider("key", "gemini-2.5-flash").analyze_speech(b"audio", "audio/webm")
    assert analysis.text == "He do his homework"  # literal: no corrige la gramática
    assert analysis.pronunciation["score"] == 77
    assert len(calls) == 1


def test_gemini_invalid_json_falls_back_to_plain_transcription(monkeypatch) -> None:
    responses = iter([_gemini_response("esto no es json"), _gemini_response("I work every day")])
    monkeypatch.setattr("app.ai.providers.httpx.request", lambda *a, **k: next(responses))
    analysis = GeminiProvider("key", "gemini-2.5-flash").analyze_speech(b"audio", "audio/webm")
    assert analysis == SpeechAnalysis("I work every day", None)


def test_openai_transcribes_without_pronunciation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.providers.httpx.request",
        lambda *a, **k: httpx.Response(200, json={"text": "I work every day"}, request=httpx.Request("POST", "https://x")),
    )
    analysis = OpenAIProvider("key", "gpt-4o-mini").analyze_speech(b"audio", "audio/webm")
    assert analysis == SpeechAnalysis("I work every day", None)


def test_spoken_answer_gets_estimated_pronunciation_end_to_end(client) -> None:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    klass = client.post(f"{API}/classes", headers=headers).json()
    with SessionLocal() as db:
        exercise = next(
            e for e in db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"]))
            if e.exercise_type in {"fill_blank", "rewrite", "short_writing"}
        )
        exercise.response_mode = ResponseMode.SPEAK
        exercise_id = exercise.id
        db.commit()

    response = client.post(
        f"{API}/classes/{klass['id']}/answers/{exercise_id}/transcribe",
        content=b"I think so",
        headers={**headers, "content-type": "audio/webm", "x-audio-duration-ms": "1500"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["pronunciationResult"]
    assert result["score"] == 80 and result["provider"] == "MOCK" and result["estimated"] is True
    assert [w["word"] for w in result["words"]] == ["I", "think", "so"]
