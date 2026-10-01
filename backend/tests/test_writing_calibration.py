"""T-043: la corrección de escritura libre es proporcional (casos con la forma de los reales)."""

from types import SimpleNamespace as NS

from app.classes.evaluation import _sanitize_ai_result, score_from_result
from app.learning.models import EvaluationMode

EXERCISE = NS(id=None, exercise_type="short_writing", prompt="Describe your hobbies.",
              evaluation_mode=EvaluationMode.AI, answer_key={"acceptedAnswers": []},
              expected_concepts=["present_simple_use", "sentence_structure", "task_completion"])

LIKE = "Después de 'like' o 'love', el verbo va con 'to' o en '-ing'."
PERIOD = "Recordá terminar las oraciones con punto."
CAPITAL = "El pronombre 'I' siempre va en mayúscula."


def _err(fragment, correction, explanation, type_="GRAMMAR_ERROR"):
    return {"type": type_, "fragment": fragment, "correction": correction, "explanation": explanation}


def test_mechanics_become_one_note_and_repeated_errors_count_once() -> None:
    # Forma del caso real: 12 "errores", la mitad son mayúsculas y puntos.
    ai = {
        "conceptResults": [
            {"concept": "present_simple_use", "status": "correct", "score": 95},
            {"concept": "sentence_structure", "status": "partially_correct", "score": 60},
            {"concept": "task_completion", "status": "correct", "score": 100},
        ],
        "errors": [
            _err("i", "I", CAPITAL), _err("play", "to play", LIKE), _err("game", "game.", PERIOD),
            _err("i", "I", CAPITAL), _err("drink", "to drink", LIKE), _err("at the morning", "in the morning", "Partes del día con 'in'."),
            _err("morning", "morning.", PERIOD), _err("i", "I", CAPITAL), _err("read", "to read", LIKE),
            _err("book", "book.", PERIOD),
        ],
        "suggestions": [],
    }
    result = _sanitize_ai_result(EXERCISE, ai)
    assert len(result["errors"]) == 2  # like + verbo (una vez) y at → in
    like = next(e for e in result["errors"] if e["explanation"] == LIKE)
    assert like["occurrences"] == 3 and "drink" in like["fragment"]
    notes = [s for s in result["suggestions"] if s["type"] == "MECHANICS_NOTE"]
    assert len(notes) == 1
    assert score_from_result(result) == 85.0  # (95 + 60 + 100) / 3


def test_one_small_slip_is_not_minus_33() -> None:
    # Forma del caso real: texto bien escrito con un solo "at the morning".
    old = {"conceptResults": [{"concept": "present_simple_use", "status": "partially_correct"},
                              {"concept": "sentence_structure", "status": "correct"},
                              {"concept": "task_completion", "status": "partially_correct"}]}
    assert score_from_result(old) == 66.7  # antes: saltos de 100 / 50 / 0
    new = {"conceptResults": [{"concept": "present_simple_use", "status": "correct", "score": 92},
                              {"concept": "sentence_structure", "status": "partially_correct", "score": 80},
                              {"concept": "task_completion", "status": "correct", "score": 95}]}
    assert score_from_result(new) == 89.0


def test_fine_score_cannot_contradict_status() -> None:
    weird = {"conceptResults": [{"concept": "a", "status": "incorrect", "score": 90},
                                {"concept": "b", "status": "correct", "score": 10}]}
    assert score_from_result(weird) == round((34 + 85) / 2, 1)  # acotado a la banda de su estado


def test_real_errors_still_count() -> None:
    ai = {
        "conceptResults": [{"concept": "present_simple_use", "status": "incorrect", "score": 20}],
        "errors": [_err("she live", "she lives", "Tercera persona: -s.")],
    }
    result = _sanitize_ai_result(EXERCISE, ai)
    assert result["errors"] and score_from_result(result) == 20.0
    assert not any(s["type"] == "MECHANICS_NOTE" for s in result["suggestions"])


def test_without_fine_scores_keeps_previous_behaviour() -> None:
    plain = {"conceptResults": [{"concept": "a", "status": "correct"}, {"concept": "b", "status": "incorrect"}]}
    assert score_from_result(plain) == 50.0
