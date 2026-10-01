"""T-034 etapa 3: la clase refuerza las habilidades débiles (o que necesitan ayuda)."""

import random

from conftest import login

from app.classes.generation import select_slots, weak_abilities
from app.curriculum.service import get_level

API = "/api/v1"
SKILLS = list(get_level("A1").skills)


def _ab(key, score, evidence=5, assisted=0, status="LEARNING"):
    return {"key": key, "name": key.title(), "score": score, "evidenceCount": evidence,
            "assistedRecent": assisted, "status": status}


def test_weak_abilities_picks_low_or_helped_up_to_two() -> None:
    focus = weak_abilities([
        _ab("GRAMMAR", 95),
        _ab("LISTENING", 55),
        _ab("WRITING", 90, assisted=3),  # acierta, pero con ayuda: también se refuerza
        _ab("VOCABULARY", 65),
        _ab("READING", None, 0),
    ])
    assert [f["key"] for f in focus] == ["WRITING", "LISTENING"]  # 0.85 vs 0.45 de necesidad; máx. 2
    assert "ayuda" in focus[0]["reason"] and "55%" in focus[1]["reason"]


def test_weak_abilities_ignores_little_evidence_and_speech_without_audio() -> None:
    assert weak_abilities([_ab("LISTENING", 40, evidence=1)]) == []
    assert weak_abilities([_ab("PRONUNCIATION", 40)]) == []
    assert [f["key"] for f in weak_abilities([_ab("PRONUNCIATION", 40)], allow_speaking=True)] == ["PRONUNCIATION"]


def test_writing_focus_forces_a_written_sentence_exercise() -> None:
    for seed in range(30):
        slots = select_slots(SKILLS, {}, rng=random.Random(seed), allow_speaking=True,
                             focus=[{"key": "WRITING"}])
        writing = [s for s in slots if s["skillKey"].startswith("a1.writing.")]
        assert writing, seed
        assert all(s["response"] == "WRITE" for s in writing)  # hablado no es Writing


def test_listening_and_speech_focus_raise_minimums() -> None:
    for seed in range(30):
        slots = select_slots(SKILLS, {}, rng=random.Random(seed), allow_speaking=True,
                             focus=[{"key": "LISTENING"}, {"key": "PRONUNCIATION"}])
        assert sum(s["presentation"] == "LISTEN" for s in slots) >= 2
        assert sum(s["response"] == "SPEAK" for s in slots) >= 2


def test_no_focus_keeps_previous_minimums() -> None:
    slots = select_slots(SKILLS, {}, rng=random.Random(4))
    assert sum(s["presentation"] == "LISTEN" for s in slots) >= 1
    assert not any(s["response"] == "SPEAK" for s in slots)


def test_class_shows_what_it_reinforces(client) -> None:
    headers = login(client)
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(f"{API}/ai/connections",
                json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1}, headers=headers)
    first = client.post(f"{API}/classes", headers=headers).json()
    assert first["focus"] == []  # sin datos todavía

    # Todo mal: la siguiente clase refuerza lo que va peor.
    answers = {str(e["id"]): "xx" for e in first["exercises"]}
    client.post(f"{API}/classes/{first['id']}/submit", json={"answers": answers}, headers=headers)
    second = client.post(f"{API}/classes", headers=headers).json()
    assert 1 <= len(second["focus"]) <= 2
    assert all(f["reason"] for f in second["focus"])
    detail = client.get(f"{API}/classes/{second['id']}", headers=headers).json()
    assert detail["focus"] == second["focus"]
