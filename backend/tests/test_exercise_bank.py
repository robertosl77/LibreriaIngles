"""T-212 · Banco de ejercicios: se llena con el uso, sin duplicados; exámenes y conversación afuera."""

from conftest import login
from sqlalchemy import select

from app.classes import bank
from app.db import SessionLocal
from app.learning.models import BankItemStatus, Exercise, ExerciseBankItem

API = "/api/v1"


def _setup(client) -> dict:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(f"{API}/ai/connections",
                json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1}, headers=headers)
    return headers


def test_generated_practice_exercises_fill_the_bank(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    assert klass["status"] == "READY"
    with SessionLocal() as db:
        exercises = db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"])).all()
        items = db.scalars(select(ExerciseBankItem)).all()
        bankable = [e for e in exercises if e.exercise_type not in bank.NOT_BANKED_TYPES]
        assert items and len(items) <= len(bankable)
        assert all(e.bank_item_id for e in bankable)
        assert all(e.bank_item_id is None for e in exercises if e.exercise_type in bank.NOT_BANKED_TYPES)
        item = items[0]
        assert item.status == BankItemStatus.ACTIVE and item.level == "A1"
        assert item.source_provider == "MOCK" and item.source_session_id == klass["id"]
        assert "conversation" not in (item.content or {})


def test_same_exercise_is_not_duplicated(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    with SessionLocal() as db:
        exercise = db.scalars(
            select(Exercise).where(Exercise.class_session_id == klass["id"], Exercise.bank_item_id.is_not(None))
        ).first()
        before = db.scalar(select(ExerciseBankItem).where(ExerciseBankItem.id == exercise.bank_item_id))
        served = before.times_served
        total = len(db.scalars(select(ExerciseBankItem)).all())
        twin = Exercise(
            class_session_id=exercise.class_session_id, study_profile_id=exercise.study_profile_id,
            level=exercise.level, area=exercise.area, skill_key=exercise.skill_key,
            exercise_type=exercise.exercise_type, instruction=exercise.instruction, prompt=exercise.prompt,
            content=exercise.content, answer_key=exercise.answer_key, expected_concepts=exercise.expected_concepts,
            presentation_mode=exercise.presentation_mode, response_mode=exercise.response_mode,
            evaluation_mode=exercise.evaluation_mode,
        )
        db.add(twin)
        item = bank.store(db, twin, provider="MOCK", model="mock", session_id=None)
        db.commit()
        assert item.id == before.id and item.times_served == served + 1
        assert len(db.scalars(select(ExerciseBankItem)).all()) == total


def test_exam_exercises_do_not_enter_the_bank(client) -> None:
    from test_exams import _make_eligible

    headers = _setup(client)
    _make_eligible(client, headers)
    with SessionLocal() as db:
        before = len(db.scalars(select(ExerciseBankItem)).all())
    exam = client.post(f"{API}/exams", headers=headers).json()
    with SessionLocal() as db:
        exam_exercises = db.scalars(select(Exercise).where(Exercise.class_session_id == exam["id"])).all()
        assert exam_exercises and all(e.bank_item_id is None for e in exam_exercises)
        assert len(db.scalars(select(ExerciseBankItem)).all()) == before
