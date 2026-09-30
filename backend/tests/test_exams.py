"""T-024: examen de aprobación de nivel y certificado."""

from datetime import timedelta

from conftest import login
from sqlalchemy import select

from app.curriculum.service import get_level
from app.db import SessionLocal
from app.exams import service
from app.learning.models import Attempt, ClassSession, Exercise, StudySkillProgress

API = "/api/v1"


def _setup(client, email: str = "roberto@example.com") -> dict:
    headers = login(client, email)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers


def _make_eligible(client, headers, *, skills: int = 15, score: float = 80) -> None:
    profile_id = client.get(f"{API}/me", headers=headers).json()["studyProfile"]["id"]
    with SessionLocal() as db:
        for skill in get_level("A1").skills[:skills]:
            db.add(
                StudySkillProgress(
                    study_profile_id=profile_id,
                    skill_key=skill.key,
                    score=score,
                    attempt_count=3,
                    confidence="low",
                    status="LEARNING",
                )
            )
        db.commit()


def _answers(exam: dict, *, correct: bool) -> dict[str, str]:
    """Respuestas correctas (desde la answer key) o todas incorrectas."""
    answers = {}
    with SessionLocal() as db:
        for item in exam["exercises"]:
            exercise = db.get(Exercise, item["id"])
            if not correct:
                answers[str(item["id"])] = "zzz"
            elif exercise.exercise_type == "short_writing":
                answers[str(item["id"])] = "My name is Ana. I live in Rosario and I work in an office."
            else:
                answers[str(item["id"])] = exercise.answer_key["acceptedAnswers"][0]
    return answers


def test_exam_requires_eligibility(client) -> None:
    headers = _setup(client)
    status = client.get(f"{API}/exams/status", headers=headers).json()
    assert status["available"] is True
    assert status["eligible"] is False
    assert status["canStart"] is False
    assert [c["ok"] for c in status["checks"]] == [False, False]

    response = client.post(f"{API}/exams", headers=headers)
    assert response.status_code == 409


def test_pass_exam_issues_verifiable_certificate(client) -> None:
    headers = _setup(client)
    _make_eligible(client, headers)
    status = client.get(f"{API}/exams/status", headers=headers).json()
    assert status["eligible"] is True and status["canStart"] is True

    created = client.post(f"{API}/exams", headers=headers)
    assert created.status_code == 201, created.text
    exam = created.json()
    assert exam["kind"] == "EXAM"
    assert exam["status"] == "READY"
    assert exam["title"] == "Examen de nivel A1"
    assert len(exam["exercises"]) == 12
    assert {e["area"] for e in exam["exercises"]} == {"grammar", "vocabulary", "reading", "writing"}
    assert all(e["hasLesson"] is False for e in exam["exercises"])

    # Un solo examen abierto a la vez; sin lecciones.
    assert client.post(f"{API}/exams", headers=headers).status_code == 409
    first = exam["exercises"][0]["id"]
    lesson = client.post(f"{API}/classes/{exam['id']}/exercises/{first}/lesson", headers=headers)
    assert lesson.status_code == 409
    assert client.get(f"{API}/exams/status", headers=headers).json()["openExamId"] == exam["id"]

    progress_before = client.get(f"{API}/progress", headers=headers).json()

    submitted = client.post(
        f"{API}/classes/{exam['id']}/submit",
        json={"answers": _answers(exam, correct=True)},
        headers=headers,
    ).json()
    assert submitted["status"] == "COMPLETED"
    result = submitted["examResult"]
    assert result["passed"] is True
    assert result["score"] >= service.PASS_SCORE
    assert {a["key"] for a in result["areas"]} == {"grammar", "vocabulary", "reading", "writing"}
    code = submitted["certificateCode"]
    assert code and code.startswith("LI-A1-")

    # El examen no modifica el progreso de las clases.
    assert client.get(f"{API}/progress", headers=headers).json() == progress_before
    # No se rehace.
    assert client.post(f"{API}/classes/{exam['id']}/retake", headers=headers).status_code == 409

    # Verificación pública (sin sesión).
    public = client.get(f"{API}/certificates/{code.lower()}")
    assert public.status_code == 200
    body = public.json()
    assert body["level"] == "A1" and body["holderName"] == "Roberto"
    assert "No es una certificación oficial" in body["notice"]
    assert client.get(f"{API}/certificates/LI-A1-XXXX-XXXX").status_code == 404

    status = client.get(f"{API}/exams/status", headers=headers).json()
    assert status["passed"] is True
    assert status["certificateCode"] == code
    assert status["canStart"] is False
    assert status["nextLevel"] == {"level": "A2", "available": False}
    assert [c["code"] for c in client.get(f"{API}/certificates", headers=headers).json()] == [code]

    history = client.get(f"{API}/classes", headers=headers).json()
    assert history[0]["kind"] == "EXAM"


def test_failed_exam_has_no_certificate_and_waits_to_retry(client) -> None:
    headers = _setup(client)
    _make_eligible(client, headers)
    exam = client.post(f"{API}/exams", headers=headers).json()
    submitted = client.post(
        f"{API}/classes/{exam['id']}/submit",
        json={"answers": _answers(exam, correct=False)},
        headers=headers,
    ).json()
    assert submitted["examResult"]["passed"] is False
    assert submitted["certificateCode"] is None

    status = client.get(f"{API}/exams/status", headers=headers).json()
    assert status["passed"] is False
    assert status["cooldownUntil"] is not None
    assert status["canStart"] is False
    assert status["attempts"] == 1
    assert client.post(f"{API}/exams", headers=headers).status_code == 409

    # Pasado el plazo se puede volver a rendir.
    with SessionLocal() as db:
        session = db.get(ClassSession, exam["id"])
        session.evaluated_at = session.evaluated_at - service.RETRY_COOLDOWN - timedelta(minutes=1)
        db.commit()
    assert client.get(f"{API}/exams/status", headers=headers).json()["canStart"] is True


def test_area_minimum_is_required_even_with_good_average(client) -> None:
    headers = _setup(client)
    _make_eligible(client, headers)
    exam = client.post(f"{API}/exams", headers=headers).json()
    client.post(
        f"{API}/classes/{exam['id']}/submit",
        json={"answers": _answers(exam, correct=True)},
        headers=headers,
    )
    with SessionLocal() as db:
        session = db.get(ClassSession, exam["id"])
        rows = db.execute(
            select(Attempt, Exercise)
            .join(Exercise, Exercise.id == Attempt.exercise_id)
            .where(Exercise.class_session_id == session.id)
        ).all()
        for attempt, exercise in rows:
            attempt.score = 40 if exercise.area == "writing" else 100
        db.commit()
        # Promedio (10×100 + 2×40)/12 = 90, pero escritura queda en 40 < mínimo por área.
        result = service.finalize_exam(db, session)
    assert result["score"] == 90
    assert result["passed"] is False
    writing = next(a for a in result["areas"] if a["key"] == "writing")
    assert writing["passed"] is False


def test_exam_of_other_account_is_not_accessible(client) -> None:
    headers = _setup(client)
    _make_eligible(client, headers)
    exam = client.post(f"{API}/exams", headers=headers).json()
    other = login(client, "otra@example.com")
    assert client.get(f"{API}/classes/{exam['id']}", headers=other).status_code == 404
