"""T-020: "Necesito lección" dentro de la clase."""

from conftest import login

from app.curriculum.lessons import get_lesson
from app.curriculum.service import get_level
from app.progress.service import _ema

API = "/api/v1"


def _class(client) -> tuple[dict, dict]:
    headers = login(client)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    response = client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    created = client.post(f"{API}/classes", headers=headers)
    assert created.status_code == 201, created.text
    return headers, created.json()


def test_every_a1_skill_has_a_lesson() -> None:
    missing = [s.key for s in get_level("A1").skills if get_lesson(s.key) is None]
    assert missing == []
    for skill in get_level("A1").skills:
        lesson = get_lesson(skill.key)
        assert lesson["title"] and lesson["rules"] and lesson["examples"]


def test_lesson_is_registered_and_carried_to_the_attempt(client) -> None:
    headers, klass = _class(client)
    first, second = klass["exercises"][0], klass["exercises"][1]
    assert first["hasLesson"] is True
    assert first["assistance"] == "NONE"

    opened = client.post(
        f"{API}/classes/{klass['id']}/exercises/{first['id']}/lesson", headers=headers
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["registered"] is True
    assert body["lesson"]["skillKey"] == first["skillKey"]
    assert body["lesson"]["rules"]

    # Sigue en la misma clase: el ejercicio queda marcado y se puede responder.
    detail = client.get(f"{API}/classes/{klass['id']}", headers=headers).json()
    assert detail["status"] == "IN_PROGRESS"
    assert detail["exercises"][0]["assistance"] == "LESSON"
    assert detail["exercises"][1]["assistance"] == "NONE"

    # Escribir la respuesta después no borra la marca.
    client.put(
        f"{API}/classes/{klass['id']}/answers/{first['id']}",
        json={"answer": "algo"},
        headers=headers,
    )
    submitted = client.post(f"{API}/classes/{klass['id']}/submit", json={}, headers=headers).json()
    assert submitted["status"] == "COMPLETED"
    assert submitted["exercises"][0]["assistance"] == "LESSON"
    assert submitted["exercises"][0]["answer"] == "algo"
    assert submitted["exercises"][1]["assistance"] == "NONE"

    # Después de corregir se puede consultar, pero ya no se registra.
    again = client.post(
        f"{API}/classes/{klass['id']}/exercises/{second['id']}/lesson", headers=headers
    ).json()
    assert again["registered"] is False

    # Al rehacer, la ronda nueva arranca sin ayuda.
    retaken = client.post(f"{API}/classes/{klass['id']}/retake", headers=headers).json()
    assert all(e["assistance"] == "NONE" for e in retaken["exercises"])

    progress = client.get(f"{API}/progress", headers=headers).json()
    skills = {s["key"]: s for a in progress["areas"] for t in a["topics"] for s in t["skills"]}
    assert skills[first["skillKey"]]["assistedRecent"] >= 1


def test_lesson_of_other_account_class_is_not_found(client) -> None:
    _, klass = _class(client)
    other = login(client, "otra@example.com")
    response = client.post(
        f"{API}/classes/{klass['id']}/exercises/{klass['exercises'][0]['id']}/lesson",
        headers=other,
    )
    assert response.status_code == 404


def test_assisted_attempts_move_the_score_less() -> None:
    plain = _ema([40, 100])
    assisted = _ema([40, 100], [1.0, 0.5])
    assert plain == 70
    assert 40 < assisted < plain
