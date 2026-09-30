"""Lecciones por skill (T-020): el "manual" que el alumno consulta durante la clase.

Una lección por skill y nivel, cargada como datos (sin IA): se revisa una vez y
sirve para todos los alumnos. Agregar un nivel = agregar data/lessons/<nivel>.json.
"""

import json
from functools import lru_cache
from pathlib import Path

from app.curriculum.service import find_skill

LESSONS_DIR = Path(__file__).parent / "data" / "lessons"


def _clean_lesson(key: str, raw: dict) -> dict:
    title = (raw.get("title") or "").strip()
    if not title:
        raise ValueError(f"La lección {key} no tiene título.")
    return {
        "title": title,
        "explanation": (raw.get("explanation") or "").strip(),
        "rules": [str(r) for r in raw.get("rules") or []],
        "examples": [
            {"en": str(e.get("en", "")), "es": str(e.get("es", ""))}
            for e in raw.get("examples") or []
        ],
        "commonMistakes": [
            {
                "wrong": str(m.get("wrong", "")),
                "right": str(m.get("right", "")),
                "why": str(m.get("why", "")),
            }
            for m in raw.get("commonMistakes") or []
        ],
        "tip": (raw.get("tip") or "").strip() or None,
    }


@lru_cache
def _all_lessons() -> dict[str, dict]:
    lessons: dict[str, dict] = {}
    for path in sorted(LESSONS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, raw in data.get("lessons", {}).items():
            if find_skill(key) is None:
                raise ValueError(f"Lección para una skill inexistente en {path.name}: {key}")
            lessons[key] = _clean_lesson(key, raw)
    return lessons


def get_lesson(skill_key: str | None) -> dict | None:
    if not skill_key:
        return None
    return _all_lessons().get(skill_key)


def lesson_payload(skill_key: str) -> dict | None:
    """Lección lista para el frontend, con el contexto de la skill."""
    lesson = get_lesson(skill_key)
    if lesson is None:
        return None
    skill = find_skill(skill_key)
    return {
        "skillKey": skill_key,
        "topic": skill.topic_name if skill else None,
        "skill": skill.name if skill else None,
        **lesson,
    }
