"""T-021: errores de ortografía menores no son errores de concepto."""

from types import SimpleNamespace as NS

from app.classes.evaluation import ai_score, evaluate
from app.classes.spelling import edit_distance, is_minor_typo, known_words, spelling_slips
from app.learning.models import EvaluationMode


def _exercise(accepted, type_="fill_blank", prompt="A ___ drives a taxi.", mode=EvaluationMode.HYBRID,
              common=None):
    return NS(id=None, exercise_type=type_, prompt=prompt, evaluation_mode=mode,
              answer_key={"acceptedAnswers": accepted, "commonErrors": common or []},
              expected_concepts=["jobs_vocabulary"])


def test_edit_distance_counts_transposition_as_one() -> None:
    assert edit_distance("taxi", "taxy") == 1
    assert edit_distance("friend", "freind") == 1
    assert edit_distance("restaurant", "restaurent") == 1


def test_minor_typo_rules() -> None:
    assert is_minor_typo("friend", "freind")
    assert is_minor_typo("restaurant", "restorant")  # 2 cambios en palabra larga
    assert not is_minor_typo("in", "on")  # palabras cortas: nunca
    assert not is_minor_typo("does", "dose")
    assert not is_minor_typo("sheep", "sleep")  # otra palabra conocida, no un tipeo
    assert not is_minor_typo("teacher", "doctor")
    # Terminaciones que enseña la gramática: no son tipeo.
    assert not is_minor_typo("watches", "watchs")
    assert not is_minor_typo("studies", "studys")
    assert not is_minor_typo("playing", "playin")
    assert not is_minor_typo("stopped", "stoped")
    assert "sleep" in known_words()


def test_spelling_slips_needs_the_rest_to_match() -> None:
    assert spelling_slips(["taxi driver"], "taxy driver") == [("taxy", "taxi")]  # caso real de T-021
    assert spelling_slips(["My friend is a teacher."], "my freind is a teacher") == [("freind", "friend")]
    assert spelling_slips(["My friend is a teacher."], "my freind is a doctor") is None
    assert spelling_slips(["She is a nurse."], "she is a nurse") is None  # sin diferencias


def test_minor_spelling_is_partial_never_zero() -> None:
    ex = _exercise(["teacher"], prompt="My mother works in a school. She is a ___.")
    result = evaluate(None, None, ex, "techer")
    assert result.score == 80
    assert result.result["result"] == "partially_correct"
    assert result.result["errors"][0]["type"] == "SPELLING_ERROR"
    assert all(c["status"] == "correct" for c in result.result["conceptResults"])
    assert "ortografía" in result.result["feedback"]


def test_real_word_mistakes_still_wrong() -> None:
    ex = _exercise(["in"], prompt="My birthday is ___ June.", mode=EvaluationMode.DETERMINISTIC)
    assert evaluate(None, None, ex, "on").score == 0


def test_spoken_and_choice_answers_skip_spelling() -> None:
    choice = _exercise(["teacher"], type_="multiple_choice", mode=EvaluationMode.DETERMINISTIC)
    assert evaluate(None, None, choice, "techer").score == 0


def test_ai_spelling_only_result_is_capped_on_closed_items() -> None:
    ex = _exercise(["taxi driver"])
    ai = {"conceptResults": [{"concept": "jobs_vocabulary", "status": "correct"}],
          "errors": [{"type": "SPELLING_ERROR", "fragment": "taxy", "correction": "taxi"}]}
    assert ai_score(ex, ai) == 80 and ai["result"] == "partially_correct"
    open_ex = _exercise([], type_="short_writing")
    assert ai_score(open_ex, dict(ai)) == 100  # escritura libre: no se topea


def test_common_error_label_follows_score() -> None:
    ex = _exercise(
        ["She doesn't play tennis."], type_="rewrite", prompt="She plays tennis.",
        common=[{"answer": "She doesn't plays tennis.", "feedback": "Verbo base después de doesn't.",
                 "conceptResults": [{"concept": "doesnt", "status": "correct"},
                                    {"concept": "base_verb", "status": "incorrect"}]}],
    )
    ex.expected_concepts = ["doesnt", "base_verb"]
    result = evaluate(None, None, ex, "She doesn't plays tennis.")
    assert result.score == 50 and result.result["result"] == "partially_correct"
