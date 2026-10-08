"""T-214 · Práctica continua por tandas: Continuar corrige en segundo plano y muestra la siguiente;
Finalizar y comprobar muestra todo junto. La clase clásica y el examen no cambian."""

from conftest import correct_answer, login
from sqlalchemy import select

from app.db import SessionLocal
from app.learning.models import Attempt, ClassSession, Exercise

API = "/api/v1"


def _setup(client) -> dict:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(f"{API}/ai/connections",
                json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1}, headers=headers)
    return headers


def _answers(klass: dict, batch: int) -> dict:
    with SessionLocal() as db:
        rows = db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"], Exercise.batch == batch)).all()
        return {str(e.id): correct_answer(e) for e in rows}


def test_practice_starts_with_one_batch_and_prepares_the_next(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes/practice", headers=headers).json()
    assert klass["practice"] == {"batch": 1, "batchSize": 5, "finished": False}
    assert 3 <= len(klass["exercises"]) <= 5 and all(e["batch"] == 1 for e in klass["exercises"])
    with SessionLocal() as db:  # la tanda 2 ya quedó preparada (oculta)
        assert db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"], Exercise.batch == 2)).first()
    again = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    assert all(e["batch"] == 1 for e in again["exercises"])


def test_continue_shows_next_batch_and_hides_corrections_until_finish(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes/practice", headers=headers).json()
    response = client.post(f"{API}/classes/{klass['id']}/continue",
                           json={"answers": _answers(klass, 1)}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["practice"]["batch"] == 2 and body["status"] == "IN_PROGRESS"
    assert any(e["batch"] == 2 for e in body["exercises"])
    assert all(e["result"] is None for e in body["exercises"])  # se ven al finalizar
    with SessionLocal() as db:
        first = db.scalars(select(Attempt).join(Exercise).where(
            Exercise.class_session_id == klass["id"], Exercise.batch == 1)).all()
        assert first and all(a.score is not None for a in first)  # corregida en segundo plano
        assert db.get(ClassSession, klass["id"]).status.value != "COMPLETED"


def test_finish_shows_everything_and_drops_unused_prepared_batch(client) -> None:
    headers = _setup(client)
    klass = client.post(f"{API}/classes/practice", headers=headers).json()
    client.post(f"{API}/classes/{klass['id']}/continue", json={"answers": _answers(klass, 1)}, headers=headers)
    done = client.post(f"{API}/classes/{klass['id']}/submit", json={"answers": _answers(klass, 2)}, headers=headers)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "COMPLETED" and body["practice"]["finished"] is True
    assert {e["batch"] for e in body["exercises"]} == {1, 2}
    assert all(e["result"] is not None for e in body["exercises"])
    with SessionLocal() as db:  # la tanda 3 preparada y no mostrada no queda (no cuenta como vista)
        assert db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"], Exercise.batch == 3)).first() is None
        attempts = db.scalars(select(Attempt).join(Exercise).where(Exercise.class_session_id == klass["id"])).all()
        assert len(attempts) == len(body["exercises"])  # sin intentos duplicados


def test_continue_without_ai_or_bank_says_to_finish(client, monkeypatch) -> None:
    from app.classes import generation

    headers = _setup(client)
    klass = client.post(f"{API}/classes/practice", headers=headers).json()
    with SessionLocal() as db:  # sin tanda preparada y sin forma de armar otra
        for e in db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"], Exercise.batch == 2)):
            db.delete(e)
        db.commit()

    def nothing(*a, **k):
        raise generation.GenerationFailed("No hay más ejercicios disponibles por ahora.")

    monkeypatch.setattr(generation, "add_practice_batch", nothing)
    response = client.post(f"{API}/classes/{klass['id']}/continue", json={"answers": _answers(klass, 1)}, headers=headers)
    assert response.status_code == 409
    assert "Finalizar y comprobar" in response.json()["detail"]
