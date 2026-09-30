"""Currícula como datos: agregar un nivel = agregar un archivo JSON en data/."""

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
DATA_DIR = Path(__file__).parent / "data"

EXERCISE_TYPES = {
    "fill_blank",
    "multiple_choice",
    "reading_multiple_choice",
    "rewrite",
    "short_writing",
}

# Modalidades de presentación (T-025): cualquier tipo puede leerse o escucharse.
PRESENTATIONS = ("READ", "LISTEN")


@dataclass(frozen=True)
class Skill:
    key: str  # clave completa: a1.grammar.present_simple.questions_do_does
    level: str
    area_key: str
    area_name: str
    topic_key: str
    topic_name: str
    skill_key: str
    name: str
    objectives: tuple[str, ...]
    exercise_types: tuple[str, ...]
    examples: tuple[dict, ...] = field(default_factory=tuple)
    # Cómo se puede presentar: por defecto leído o escuchado; ["LISTEN"] = solo escucha.
    presentations: tuple[str, ...] = PRESENTATIONS


@dataclass(frozen=True)
class LevelCurriculum:
    level: str
    name: str
    description: str
    skills: tuple[Skill, ...]

    def skill(self, key: str) -> Skill | None:
        return next((s for s in self.skills if s.key == key), None)


def _load_level(path: Path) -> LevelCurriculum:
    data = json.loads(path.read_text(encoding="utf-8"))
    level = data["level"]
    skills: list[Skill] = []
    for area in data["areas"]:
        for topic in area["topics"]:
            for skill in topic["skills"]:
                types = tuple(skill["exerciseTypes"])
                unknown = set(types) - EXERCISE_TYPES
                if unknown:
                    raise ValueError(f"Tipos de ejercicio desconocidos en {path.name}: {unknown}")
                presentations = tuple(skill.get("presentations") or PRESENTATIONS)
                if set(presentations) - set(PRESENTATIONS):
                    raise ValueError(f"Presentación desconocida en {path.name}: {presentations}")
                skills.append(
                    Skill(
                        key=".".join(
                            [level.lower(), area["key"], topic["key"], skill["key"]]
                        ),
                        level=level,
                        area_key=area["key"],
                        area_name=area["name"],
                        topic_key=topic["key"],
                        topic_name=topic["name"],
                        skill_key=skill["key"],
                        name=skill["name"],
                        objectives=tuple(skill["objectives"]),
                        exercise_types=types,
                        examples=tuple(skill.get("examples", [])),
                        presentations=presentations,
                    )
                )
    return LevelCurriculum(
        level=level,
        name=data["name"],
        description=data.get("description", ""),
        skills=tuple(skills),
    )


@lru_cache
def _all_levels() -> dict[str, LevelCurriculum]:
    levels = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        curriculum = _load_level(path)
        levels[curriculum.level] = curriculum
    return levels


def available_levels() -> list[str]:
    return [level for level in CEFR_LEVELS if level in _all_levels()]


def get_level(level: str) -> LevelCurriculum | None:
    return _all_levels().get(level)


def find_skill(skill_key: str) -> Skill | None:
    level = skill_key.split(".", 1)[0].upper()
    curriculum = get_level(level)
    return curriculum.skill(skill_key) if curriculum else None
