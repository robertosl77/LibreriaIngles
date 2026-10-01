"""T-034 etapa 1: un ejercicio genera varias evidencias por habilidad."""

from types import SimpleNamespace as NS

from conftest import login
from sqlalchemy import select

from app.db import SessionLocal
from app.learning.models import (
    Assistance,
    Attempt,
    Exercise,
    PresentationMode,
    ResponseMode,
)
from app.progress.evidence import attempt_evidence, listening_factor

API = "/api/v1"


def _attempt(score=100, *, assistance=Assistance.NONE, response="WRITE", signals=None,
             pronunciation=None, errors=None):
    return NS(
        score=score,
        assistance=assistance,
        response_mode=ResponseMode(response),
        signals=signals,
        pronunciation_result=pronunciation,
        evaluation_result={"errors": errors or []},
    )


def _exercise(area="grammar", presentation="READ", type_="fill_blank"):
    return NS(area=area, presentation_mode=PresentationMode(presentation), exercise_type=type_)


def _by_ability(items):
    return {e.ability: e for e in items}


def test_listening_factor() -> None:
    assert listening_factor(None) == 1.0
    assert listening_factor({"listenPlays": 1}) == 1.0
    assert listening_factor({"listenPlays": 3}) == 0.7
    assert listening_factor({"listenPlays": 2, "listenSlowPlays": 1}) == 0.65
    assert listening_factor({"listenPlays": 20, "listenSlowPlays": 5}) == 0.4  # piso


def test_read_and_written_fill_blank_is_only_grammar() -> None:
    items = _by_ability(attempt_evidence(_attempt(), _exercise()))
    assert set(items) == {"GRAMMAR"}


def test_listened_exercise_feeds_topic_and_listening_with_effort() -> None:
    items = _by_ability(
        attempt_evidence(_attempt(100, signals={"listenPlays": 3, "listenSlowPlays": 1}),
                         _exercise(presentation="LISTEN"))
    )
    assert items["GRAMMAR"].score == 100  # la gramática estaba bien
    assert items["LISTENING"].score == 50  # pero costó entender: 3 escuchas y lento


def test_listened_reading_is_not_reading() -> None:
    items = _by_ability(
        attempt_evidence(_attempt(), _exercise(area="reading", presentation="LISTEN",
                                               type_="reading_multiple_choice"))
    )
    assert set(items) == {"LISTENING"}


def test_spoken_answer_feeds_speaking_pronunciation_and_topic() -> None:
    items = _by_ability(
        attempt_evidence(_attempt(0, response="SPEAK", pronunciation={"score": 90}),
                         _exercise(presentation="LISTEN"))
    )
    # "he do" bien pronunciado: contenido mal, pronunciación bien (no se mezclan).
    assert items["GRAMMAR"].score == 0
    assert items["SPEAKING"].score == 0
    assert items["PRONUNCIATION"].score == 90
    assert "LISTENING" in items and "WRITING" not in items


def test_pronunciation_slip_limits_pronunciation_not_topic() -> None:
    items = _by_ability(
        attempt_evidence(
            _attempt(100, response="SPEAK", pronunciation={"score": 95},
                     errors=[{"type": "PRONUNCIATION_ERROR", "fragment": "sink"}]),
            _exercise(),
        )
    )
    assert items["GRAMMAR"].score == 100
    assert items["PRONUNCIATION"].score == 50


def test_written_sentence_is_secondary_writing_evidence() -> None:
    items = _by_ability(attempt_evidence(_attempt(40), _exercise(type_="rewrite")))
    assert items["GRAMMAR"].weight == 1.0
    assert items["WRITING"].score == 40 and items["WRITING"].weight == 0.5


def test_lesson_halves_every_evidence() -> None:
    items = attempt_evidence(_attempt(100, assistance=Assistance.LESSON), _exercise(presentation="LISTEN"))
    assert items and all(e.weight == 0.5 for e in items)


# ------------------------------------------------------------------ flujo completo


def _setup(client) -> dict:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    return headers


def test_signals_are_recorded_copied_and_drive_listening_score(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    with SessionLocal() as db:
        exercises = db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"])).all()
        target = next(e for e in exercises if e.exercise_type in {"fill_blank", "multiple_choice"})
        target.presentation_mode = PresentationMode.LISTEN
        target.response_mode = ResponseMode.SELECT if target.exercise_type == "multiple_choice" else ResponseMode.WRITE
        target.content = {**(target.content or {}), "stimulus": "My sister is a nurse."}
        target_id = target.id
        answers = {
            str(e.id): (e.answer_key.get("acceptedAnswers") or ["My name is Ana. I live in Rosario."])[0]
            for e in exercises
        }
        db.commit()

    url = f"{API}/classes/{klass['id']}/exercises/{target_id}/signals"
    for slow in (False, False, True):
        assert client.post(url, json={"kind": "listen", "slow": slow}, headers=headers).status_code == 200
    body = client.post(url, json={"kind": "practice", "score": 62}, headers=headers).json()
    assert body["signals"] == {"listenPlays": 3, "listenSlowPlays": 1, "practiceScores": [62]}
    assert client.post(url, json={"kind": "practice"}, headers=headers).status_code == 422

    # Guardar la respuesta no borra las señales.
    client.put(f"{API}/classes/{klass['id']}/answers/{target_id}", json={"answer": answers[str(target_id)]}, headers=headers)
    detail = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    assert next(e for e in detail["exercises"] if e["id"] == target_id)["signals"]["listenPlays"] == 3

    submitted = client.post(f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers)
    assert submitted.status_code == 200
    # Enviada la clase, la evidencia ya no cambia.
    assert client.post(url, json={"kind": "listen"}, headers=headers).status_code == 409

    with SessionLocal() as db:
        attempt = db.scalar(select(Attempt).where(Attempt.exercise_id == target_id))
        assert attempt.signals["listenPlays"] == 3

    abilities = {a["key"]: a for a in client.get(f"{API}/progress", headers=headers).json()["abilities"]}
    assert [a for a in abilities] == ["GRAMMAR", "VOCABULARY", "LISTENING", "SPEAKING", "PRONUNCIATION", "READING", "WRITING"]
    listening = abilities["LISTENING"]
    assert listening["evidenceCount"] >= 1
    assert listening["score"] is not None and listening["score"] < 100  # costó entender
    assert abilities["PRONUNCIATION"]["practiceTrials"] == 1
    assert all(a["status"] in {"NOT_STARTED", "LEARNING", "MASTERED", "NEEDS_REVIEW"} for a in abilities.values())
