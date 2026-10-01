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


def test_grammar_rewrite_is_not_writing() -> None:
    # Reescribir una oración dada mide gramática; no debe inflar Writing.
    items = _by_ability(attempt_evidence(_attempt(100), _exercise(type_="rewrite")))
    assert set(items) == {"GRAMMAR"}


def test_writing_area_is_writing() -> None:
    for type_ in ("short_writing", "rewrite"):  # componer o armar la oración
        items = _by_ability(attempt_evidence(_attempt(56), _exercise(area="writing", type_=type_)))
        assert items["WRITING"].score == 56 and items["WRITING"].weight == 1.0


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


# ------------------------------------------------------------------ asistencia continua


def test_many_listens_or_slow_mark_listening_as_assisted() -> None:
    once = _by_ability(attempt_evidence(_attempt(signals={"listenPlays": 2}), _exercise(presentation="LISTEN")))
    many = _by_ability(attempt_evidence(_attempt(signals={"listenPlays": 3}), _exercise(presentation="LISTEN")))
    slow = _by_ability(attempt_evidence(_attempt(signals={"listenPlays": 1, "listenSlowPlays": 1}),
                                        _exercise(presentation="LISTEN")))
    assert not once["LISTENING"].assisted
    assert many["LISTENING"].assisted and slow["LISTENING"].assisted
    assert not many["GRAMMAR"].assisted  # la gramática no recibió ayuda


def test_continuous_practice_marks_pronunciation_without_lowering_score() -> None:
    def pron(trials):
        items = _by_ability(attempt_evidence(
            _attempt(100, response="SPEAK", pronunciation={"score": 88},
                     signals={"practiceScores": [60] * trials}),
            _exercise()))
        return items["PRONUNCIATION"]

    assert not pron(2).assisted and pron(2).weight == 1.0
    assert pron(3).assisted and pron(3).weight == 0.5
    assert pron(3).score == 88  # practicar no castiga el puntaje


def test_lesson_marks_every_evidence_as_assisted() -> None:
    items = attempt_evidence(_attempt(100, assistance=Assistance.LESSON), _exercise(presentation="LISTEN"))
    assert all(e.assisted for e in items)


def test_recent_help_blocks_mastered() -> None:
    from app.progress.service import _status

    assert _status(95, 6) == "MASTERED"
    assert _status(95, 6, assisted_recent=1) == "LEARNING"


# ------------------------------------------------------------------ think / sink sin IA


def test_spoken_sound_alike_is_pronunciation_error_not_content() -> None:
    from app.classes.spoken import pronunciation_slips, sounds_alike

    assert sounds_alike("think", "sink") and sounds_alike("three", "tree")
    assert sounds_alike("very", "berry") and sounds_alike("ship", "sheep")
    assert not sounds_alike("think", "drink")
    assert pronunciation_slips(["I think so."], "i sink so") == [("sink", "think")]
    assert pronunciation_slips(["I think so."], "I drink so") is None
    assert pronunciation_slips(["He does not work."], "He do not work") is None


def test_deterministic_spoken_answer_uses_pronunciation_rule() -> None:
    from app.classes.evaluation import evaluate
    from app.learning.models import EvaluationMode

    exercise = NS(
        id=None, exercise_type="short_answer", prompt="", evaluation_mode=EvaluationMode.DETERMINISTIC,
        answer_key={"acceptedAnswers": ["I think so."]}, expected_concepts=["opinion"],
    )
    # Sin puntuación ni mayúsculas, como sale de una transcripción.
    assert evaluate(None, None, exercise, "i think so", spoken=True).score == 100
    slip = evaluate(None, None, exercise, "I sink, so", spoken=True)
    assert slip.score == 100
    assert slip.result["errors"][0]["type"] == "PRONUNCIATION_ERROR"
    items = _by_ability(attempt_evidence(
        _attempt(slip.score, response="SPEAK", pronunciation={"score": 92}, errors=slip.result["errors"]),
        _exercise()))
    assert items["GRAMMAR"].score == 100 and items["PRONUNCIATION"].score == 50


def test_spoken_sink_through_full_class(client) -> None:
    from app.learning.models import DraftAnswer, EvaluationMode

    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    with SessionLocal() as db:
        exercises = db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"])).all()
        for e in exercises:  # el resto, escrito
            if e.response_mode == ResponseMode.SPEAK:
                e.response_mode = ResponseMode.WRITE
        target = next(e for e in exercises if e.exercise_type not in {"multiple_choice", "reading_multiple_choice"})
        target.response_mode = ResponseMode.SPEAK
        target.evaluation_mode = EvaluationMode.DETERMINISTIC
        target.answer_key = {"acceptedAnswers": ["I think so."], "commonErrors": []}
        target_id = target.id
        db.add(DraftAnswer(class_session_id=klass["id"], exercise_id=target_id, answer_text="i sink so",
                           pronunciation_result={"score": 90}))
        answers = {
            str(e.id): (e.answer_key.get("acceptedAnswers") or ["My name is Ana. I live in Rosario."])[0]
            for e in exercises if e.id != target_id
        }
        db.commit()

    assert client.post(f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers).status_code == 200
    with SessionLocal() as db:
        attempt = db.scalar(select(Attempt).where(Attempt.exercise_id == target_id))
        assert attempt.score == 100
        assert attempt.evaluation_result["errors"][0]["type"] == "PRONUNCIATION_ERROR"
    abilities = {a["key"]: a for a in client.get(f"{API}/progress", headers=headers).json()["abilities"]}
    assert abilities["PRONUNCIATION"]["score"] == 50
    assert abilities["SPEAKING"]["score"] == 100
