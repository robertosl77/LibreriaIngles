import random

from app.classes.evaluation import score_from_result
from app.classes.generation import _validate_exercise, select_slots
from app.classes.normalize import fill_blank_variants, normalize_answer
from app.curriculum.service import available_levels, get_level


def test_normalization_equivalences() -> None:
    assert normalize_answer("She doesn't play tennis.") == normalize_answer("she does not play tennis")
    assert normalize_answer("They’re at home!") == normalize_answer("They are at home")
    assert normalize_answer("  I   can't  ") == normalize_answer("I cannot")
    assert normalize_answer("'re running") == normalize_answer("are running")
    assert normalize_answer("") == ""


def test_fill_blank_accepts_full_sentence() -> None:
    variants = fill_blank_variants("Tom ___ (watch) TV every evening.", ["watches"])
    assert normalize_answer("Tom watches TV every evening.") in {normalize_answer(v) for v in variants}


def test_backend_scores_from_concepts_not_ai_suggestion() -> None:
    result = {
        "result": "incorrect",
        "scoreSuggested": 5,
        "conceptResults": [
            {"concept": "does", "status": "correct"},
            {"concept": "base_verb_after_does", "status": "incorrect"},
        ],
        "suggestions": [{"type": "STYLE_SUGGESTION", "text": "..."}],
    }
    assert score_from_result(result) == 50.0


def test_curriculum_loads_a1() -> None:
    assert "A1" in available_levels()
    curriculum = get_level("A1")
    assert len(curriculum.skills) >= 15
    assert all(skill.examples for skill in curriculum.skills)


def test_slot_selection_prioritizes_unpracticed_and_mixes_areas() -> None:
    skills = list(get_level("A1").skills)
    slots = select_slots(skills, {}, count=6, rng=random.Random(1))
    assert len(slots) == 6
    assert len({s["skillKey"] for s in slots}) == 6
    assert any(not s["skillKey"].startswith("a1.grammar") for s in slots)


def test_multiple_choice_answer_must_be_an_option() -> None:
    slot = {"skillKey": "a1.grammar.can.ability", "allowedTypes": ["multiple_choice"]}
    bad = {
        "skillKey": "a1.grammar.can.ability",
        "type": "multiple_choice",
        "question": "He ___ swim.",
        "options": ["can", "cans"],
        "acceptedAnswers": ["could"],
    }
    assert _validate_exercise(bad, slot) is None
    good = {**bad, "acceptedAnswers": ["Can"]}
    assert _validate_exercise(good, slot).acceptedAnswers == ["can"]


def test_skill_outside_request_is_rejected() -> None:
    slot = {"skillKey": "a1.grammar.can.ability", "allowedTypes": ["fill_blank"]}
    other = {
        "skillKey": "a1.grammar.to_be.affirmative",
        "type": "fill_blank",
        "question": "She ___ happy.",
        "acceptedAnswers": ["is"],
    }
    assert _validate_exercise(other, slot) is None
