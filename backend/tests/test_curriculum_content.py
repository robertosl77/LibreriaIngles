"""Calidad del contenido de la currícula (T-028 / T-032)."""

import pytest

from app.classes.generation import _validate_exercise
from app.classes.normalize import BLANK, normalize_answer
from app.curriculum.lessons import get_lesson
from app.curriculum.service import get_level

A1 = get_level("A1")
SKILLS = list(A1.skills)


def test_a1_covers_functional_doc_topics() -> None:
    keys = {s.key for s in SKILLS}
    for expected in [
        "a1.grammar.pronouns.subject_pronouns",
        "a1.grammar.nouns.plurals",
        "a1.grammar.have_got.basic",
        "a1.grammar.imperatives.basic",
        "a1.grammar.demonstratives.this_that",
        "a1.grammar.prepositions_place.basic",
        "a1.grammar.connectors.basic",
        "a1.vocabulary.greetings.introductions",
        "a1.vocabulary.numbers_dates.numbers",
        "a1.vocabulary.numbers_dates.days_months",
        "a1.vocabulary.colours_clothes.colours",
        "a1.vocabulary.colours_clothes.clothes",
        "a1.vocabulary.home.rooms_furniture",
    ]:
        assert expected in keys, expected


@pytest.mark.parametrize("skill", SKILLS, ids=lambda s: s.key)
def test_skill_has_lesson_and_enough_seeds(skill) -> None:
    assert get_lesson(skill.key) is not None
    assert len(skill.examples) >= 2
    seeded = {e["type"] for e in skill.examples}
    assert set(skill.exercise_types) <= seeded, f"tipos sin ejemplo: {set(skill.exercise_types) - seeded}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda s: s.key)
def test_seed_examples_are_valid_and_unambiguous(skill) -> None:
    for example in skill.examples:
        presentation = "LISTEN" if "READ" not in skill.presentations else "READ"
        slot = {"skillKey": skill.key, "allowedTypes": [example["type"]], "presentation": presentation}
        item = _validate_exercise({**example, "skillKey": skill.key}, slot)
        assert item is not None, f"ejemplo inválido: {example['question']}"
        text = f"{example.get('instruction', '')} {example['question']}".lower()
        assert "does not belong" not in text and "odd one out" not in text
        if example["type"] == "fill_blank":
            assert example["question"].count(BLANK) == 1
        if example["type"].endswith("multiple_choice"):
            options = {normalize_answer(o) for o in example["options"]}
            assert len(options) == len(example["options"]), "opciones repetidas"
            assert len(example["acceptedAnswers"]) == 1
