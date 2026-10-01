"""Evaluación híbrida (documento funcional §11).

persistir intento → normalizar →
  acceptedAnswers coincide  → RULE_MATCH
  hablada, suena parecido   → correcto + PRONUNCIATION_ERROR (RULE_MATCH)
  commonErrors coincide     → COMMON_ERROR_MATCH
  escrita, tipeo menor      → parcial + SPELLING_ERROR (RULE_MATCH, T-021)
  modo DETERMINISTIC        → incorrecto por regla (RULE_MATCH); hablada → IA
  caché de IA               → AI
  evaluación con IA         → AI  (si no hay IA: queda pendiente)

El backend tiene la última palabra: el score sale de los conceptos, no del
"scoreSuggested" de la IA, y las sugerencias de estilo no descuentan.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import utcnow
from app.ai.service import NoAIAvailable, connection_snapshot, run_json_task
from app.classes.normalize import fill_blank_variants, normalize_answer
from app.classes.prompts import EVALUATION_SYSTEM, evaluation_user_prompt
from app.classes.spelling import SPELLING_SCORE, spelling_slips
from app.classes.spoken import normalize_spoken, pronunciation_slips
from app.curriculum.service import find_skill
from app.learning.models import (
    AIEvaluationCache,
    Attempt,
    EvaluationMode,
    EvaluationSource,
    Exercise,
)

CHOICE_TYPES = {"multiple_choice", "reading_multiple_choice"}
STATUS_SCORE = {"correct": 100.0, "partially_correct": 50.0, "incorrect": 0.0}
ERROR_TYPES = {"GRAMMAR_ERROR", "VOCABULARY_ERROR", "SPELLING_ERROR", "WORD_ORDER_ERROR", "PRONUNCIATION_ERROR"}
SUGGESTION_TYPES = {
    "STYLE_SUGGESTION",
    "NATURALNESS_SUGGESTION",
    "SHORTER_ALTERNATIVE",
    "MECHANICS_NOTE",  # mayúsculas / puntuación: se señala, no descuenta (T-043)
}
# Puntaje fino por concepto (T-043): la IA da 0-100 y se respeta dentro de la banda de su
# estado, así un error chico no vale lo mismo que no saber el tema.
STATUS_BANDS = {"correct": (85.0, 100.0), "partially_correct": (35.0, 84.0), "incorrect": (0.0, 34.0)}


@dataclass
class Evaluation:
    source: EvaluationSource
    result: dict
    score: float


def _concept_score(concept: dict) -> float:
    """Puntaje de un concepto: el fino de la IA (acotado a la banda de su estado) o el del estado."""
    status = concept["status"]
    value = concept.get("score")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        low, high = STATUS_BANDS[status]
        return min(high, max(low, float(value)))
    return STATUS_SCORE[status]


def score_from_result(result: dict) -> float:
    concepts = [
        c for c in result.get("conceptResults") or [] if isinstance(c, dict) and c.get("status") in STATUS_SCORE
    ]
    if concepts:
        return round(sum(_concept_score(c) for c in concepts) / len(concepts), 1)
    return STATUS_SCORE.get(result.get("result"), 0.0)


def ai_score(exercise: Exercise, result: dict) -> float:
    """Puntaje de una corrección de la IA. En ejercicios con respuesta cerrada, si el único
    problema es ortografía, vale lo mismo que por regla (T-021): parcial, no 100 ni 0."""
    score = score_from_result(result)
    errors = result.get("errors") or []
    closed = bool(exercise.answer_key.get("acceptedAnswers"))
    if closed and errors and all(e.get("type") == "SPELLING_ERROR" for e in errors):
        score = min(score, SPELLING_SCORE)
        result["result"] = _result_label(score)
    return score


def _result_label(score: float) -> str:
    if score >= 99.9:
        return "correct"
    if score <= 0.1:
        return "incorrect"
    return "partially_correct"


def _accepted(exercise: Exercise) -> list[str]:
    accepted = list(exercise.answer_key.get("acceptedAnswers") or [])
    if exercise.exercise_type == "fill_blank":
        accepted += fill_blank_variants(exercise.prompt, accepted)
    return [a for a in accepted if a]


def _accepted_normalized(exercise: Exercise, normalize=normalize_answer) -> set[str]:
    return {normalize(a) for a in _accepted(exercise)}


def _pronunciation_slip_result(exercise: Exercise, slips: list[tuple[str, str]]) -> dict:
    """Dijo la respuesta correcta con una palabra mal pronunciada (think → sink)."""
    result = _rule_correct(exercise)
    result["errors"] = [
        {
            "type": "PRONUNCIATION_ERROR",
            "fragment": said,
            "correction": expected,
            "explanation": f"Se entendió \"{said}\": cuidá la pronunciación de \"{expected}\".",
        }
        for said, expected in slips
    ]
    result["feedback"] = "Respuesta correcta; revisá la pronunciación de una palabra."
    return result


def _correct_answer(exercise: Exercise) -> str | None:
    accepted = exercise.answer_key.get("acceptedAnswers") or []
    return accepted[0] if accepted else None


def _rule_correct(exercise: Exercise) -> dict:
    return {
        "result": "correct",
        "conceptResults": [
            {"concept": c, "status": "correct"} for c in exercise.expected_concepts or []
        ],
        "errors": [],
        "correctAnswer": _correct_answer(exercise),
        "feedback": "¡Correcto!",
        "suggestions": [],
    }


def _rule_incorrect(exercise: Exercise, answer: str) -> dict:
    empty = not answer.strip()
    # La respuesta correcta ya se muestra aparte: no se duplica como "error".
    return {
        "result": "incorrect",
        "conceptResults": [
            {"concept": c, "status": "incorrect"} for c in exercise.expected_concepts or []
        ],
        "errors": [],
        "correctAnswer": _correct_answer(exercise),
        "feedback": "Sin respuesta." if empty else "No es la opción correcta.",
        "suggestions": [],
    }


def _spelling_result(exercise: Exercise, slips: list[tuple[str, str]]) -> dict:
    """Concepto correcto escrito con un error de tipeo menor (taxy → taxi): parcial, nunca 0 %."""
    result = _rule_correct(exercise)
    result["result"] = _result_label(SPELLING_SCORE)
    result["errors"] = [
        {
            "type": "SPELLING_ERROR",
            "fragment": typed,
            "correction": expected,
            "explanation": "Ortografía.",
        }
        for typed, expected in slips
    ]
    words = ", ".join(f"\"{expected}\"" for _, expected in slips)
    result["feedback"] = f"La respuesta es correcta, pero revisá la ortografía: {words}."
    return result


def _common_error_result(exercise: Exercise, error: dict) -> dict:
    listed = {
        c.get("concept"): c.get("status")
        for c in error.get("conceptResults") or []
        if isinstance(c, dict)
    }
    concepts = [
        {"concept": c, "status": listed.get(c, "correct")}
        for c in exercise.expected_concepts or listed.keys()
    ]
    # Conceptos del error que no estaban en expectedConcepts también cuentan.
    concepts += [
        {"concept": c, "status": s}
        for c, s in listed.items()
        if c not in (exercise.expected_concepts or [])
    ]
    result = {
        "result": "incorrect",
        "conceptResults": concepts,
        "errors": [
            {
                "type": "GRAMMAR_ERROR",
                "fragment": error.get("answer"),
                "correction": _correct_answer(exercise),
                "explanation": error.get("feedback", ""),
            }
        ],
        "correctAnswer": _correct_answer(exercise),
        "feedback": error.get("feedback") or "Revisá la respuesta.",
        "suggestions": [],
    }
    # La etiqueta sigue al puntaje: un error común con conceptos parciales es "Parcial".
    result["result"] = _result_label(score_from_result(result))
    return result


def _is_mechanics(error: dict) -> bool:
    """Solo mayúsculas o puntuación ("i" → "I", "game" → "game."): no es gramática."""
    fragment, correction = error.get("fragment"), error.get("correction")
    if not fragment or not correction:
        return False
    return fragment != correction and normalize_spoken(fragment) == normalize_spoken(correction)


def _dedupe_errors(errors: list[dict]) -> list[dict]:
    """El mismo error repetido ("like play", "like drink", "like read") se informa una vez."""
    merged: dict[tuple, dict] = {}
    for error in errors:
        key = (error["type"], (error.get("explanation") or "").strip().lower() or error.get("correction"))
        if key in merged:
            first = merged[key]
            fragments = [f for f in (first.get("fragment"), error.get("fragment")) if f]
            if error.get("fragment") and error["fragment"] not in (first.get("fragment") or ""):
                first["fragment"] = " · ".join(fragments)
            first["occurrences"] = first.get("occurrences", 1) + 1
            continue
        merged[key] = dict(error)
    return list(merged.values())


def _sanitize_ai_result(exercise: Exercise, data: dict) -> dict:
    concepts = []
    for item in data.get("conceptResults") or []:
        if isinstance(item, dict) and item.get("status") in STATUS_SCORE:
            concept = {"concept": str(item.get("concept") or "concept"), "status": item["status"]}
            if isinstance(item.get("score"), (int, float)) and not isinstance(item.get("score"), bool):
                concept["score"] = item["score"]
            concepts.append(concept)
    raw_errors = [
        {
            "type": e.get("type") if e.get("type") in ERROR_TYPES else "GRAMMAR_ERROR",
            "fragment": e.get("fragment"),
            "correction": e.get("correction"),
            "explanation": e.get("explanation", ""),
        }
        for e in data.get("errors") or []
        if isinstance(e, dict)
    ]
    # Mayúsculas y puntuación: una sola observación, sin descontar (T-043).
    mechanics = [e for e in raw_errors if _is_mechanics(e)]
    errors = _dedupe_errors([e for e in raw_errors if not _is_mechanics(e)])
    suggestions = [
        {
            "type": s.get("type") if s.get("type") in SUGGESTION_TYPES else "STYLE_SUGGESTION",
            "text": s.get("text", ""),
        }
        for s in data.get("suggestions") or []
        if isinstance(s, dict) and s.get("text")
    ]
    if mechanics and not any(s["type"] == "MECHANICS_NOTE" for s in suggestions):
        suggestions.append(
            {
                "type": "MECHANICS_NOTE",
                "text": "Ojo con las mayúsculas y la puntuación: \"I\" va siempre en mayúscula y cada "
                "oración empieza con mayúscula y termina con punto.",
            }
        )
    result = {
        "result": data.get("result") if data.get("result") in STATUS_SCORE else None,
        "conceptResults": concepts,
        "errors": errors,
        "correctAnswer": data.get("correctAnswer"),
        "feedback": str(data.get("feedback") or ""),
        "suggestions": suggestions,
        "scoreSuggestedByAI": data.get("scoreSuggested"),
    }
    score = score_from_result(result)
    result["result"] = _result_label(score)
    return result


def _ai_payload(exercise: Exercise, answer: str) -> dict:
    skill = find_skill(exercise.skill_key or "")
    return {
        "level": exercise.level,
        "skill": skill.name if skill else exercise.skill_key,
        "objectives": list(skill.objectives) if skill else [],
        "type": exercise.exercise_type,
        "instruction": exercise.instruction,
        "question": exercise.prompt,
        "passage": (exercise.content or {}).get("passage"),
        # Modalidades (T-025): con LISTEN, el estímulo lo escuchó (no lo vio escrito).
        "presentation": exercise.presentation_mode.value if exercise.presentation_mode else "READ",
        "response": exercise.response_mode.value if exercise.response_mode else "WRITE",
        "stimulus": (exercise.content or {}).get("stimulus"),
        "options": (exercise.content or {}).get("options"),
        "referenceAnswers": exercise.answer_key.get("acceptedAnswers") or [],
        "expectedConcepts": exercise.expected_concepts or [],
        "studentAnswer": answer,
    }


def evaluate_with_ai(db: Session, account: Account, exercise: Exercise, answer: str) -> dict:
    payload = _ai_payload(exercise, answer)
    result = run_json_task(
        db,
        account,
        system=EVALUATION_SYSTEM,
        user=evaluation_user_prompt(payload),
        task={
            "kind": "evaluate_answer",
            "exercise": {
                "type": exercise.exercise_type,
                "acceptedAnswers": payload["referenceAnswers"],
                "expectedConcepts": payload["expectedConcepts"],
            },
            "answer": answer,
        },
    )
    sanitized = _sanitize_ai_result(exercise, result.data)
    # Se guarda con la corrección (y en caché) el motor que realmente produjo
    # el resultado; no depende de la configuración actual de la cuenta.
    return {**sanitized, "ai": connection_snapshot(result.connection)}


def _cache_get(db: Session, exercise: Exercise, normalized: str) -> dict | None:
    row = db.scalar(
        select(AIEvaluationCache).where(
            AIEvaluationCache.exercise_id == exercise.id,
            AIEvaluationCache.normalized_answer == normalized,
        )
    )
    return row.evaluation_result if row else None


def _cache_put(db: Session, exercise: Exercise, normalized: str, result: dict) -> None:
    try:
        with db.begin_nested():
            db.add(
                AIEvaluationCache(
                    exercise_id=exercise.id,
                    normalized_answer=normalized,
                    evaluation_result=result,
                )
            )
    except IntegrityError:
        pass


def evaluate(
    db: Session, account: Account, exercise: Exercise, answer: str, *, spoken: bool = False
) -> Evaluation | None:
    """Devuelve la evaluación, o None si hace falta IA y no hay ninguna disponible.

    Con respuesta hablada (`spoken`) se compara la transcripción sin puntuación, y una
    palabra que suena parecida a la esperada es error de pronunciación, no de contenido.
    """
    normalize = normalize_spoken if spoken else normalize_answer
    normalized = normalize(answer)

    if not normalized:
        result = _rule_incorrect(exercise, "")
        return Evaluation(EvaluationSource.RULE_MATCH, result, 0.0)

    if exercise.evaluation_mode != EvaluationMode.AI:
        if normalized in _accepted_normalized(exercise, normalize):
            return Evaluation(EvaluationSource.RULE_MATCH, _rule_correct(exercise), 100.0)
        if spoken:
            slips = pronunciation_slips(_accepted(exercise), answer)
            if slips:
                result = _pronunciation_slip_result(exercise, slips)
                return Evaluation(EvaluationSource.RULE_MATCH, result, score_from_result(result))
        for error in exercise.answer_key.get("commonErrors") or []:
            if normalize(error.get("answer")) == normalized:
                result = _common_error_result(exercise, error)
                return Evaluation(
                    EvaluationSource.COMMON_ERROR_MATCH, result, score_from_result(result)
                )
        if not spoken and exercise.exercise_type not in CHOICE_TYPES:
            slips = spelling_slips(_accepted(exercise), answer)
            if slips:
                return Evaluation(
                    EvaluationSource.RULE_MATCH, _spelling_result(exercise, slips), SPELLING_SCORE
                )
        # Una transcripción puede diferir por cosas del habla: decide la IA si la hay.
        if exercise.evaluation_mode == EvaluationMode.DETERMINISTIC and not spoken:
            return Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0)

    cached = _cache_get(db, exercise, normalized)
    if cached is not None:
        return Evaluation(EvaluationSource.AI, cached, ai_score(exercise, cached))

    try:
        result = evaluate_with_ai(db, account, exercise, answer)
    except NoAIAvailable:
        if spoken and exercise.evaluation_mode == EvaluationMode.DETERMINISTIC:
            return Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0)
        return None
    _cache_put(db, exercise, normalized, result)
    return Evaluation(EvaluationSource.AI, result, ai_score(exercise, result))


def apply_evaluation(attempt: Attempt, evaluation: Evaluation) -> None:
    attempt.evaluation_source = evaluation.source
    attempt.evaluation_result = {**evaluation.result, "score": evaluation.score}
    attempt.score = evaluation.score
    attempt.evaluated_at = utcnow()
