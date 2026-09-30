"""Evaluación híbrida (documento funcional §11).

persistir intento → normalizar →
  acceptedAnswers coincide  → RULE_MATCH
  commonErrors coincide     → COMMON_ERROR_MATCH
  modo DETERMINISTIC        → incorrecto por regla (RULE_MATCH)
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
from app.ai.service import NoAIAvailable, run_json_task
from app.classes.normalize import fill_blank_variants, normalize_answer
from app.classes.prompts import EVALUATION_SYSTEM, evaluation_user_prompt
from app.curriculum.service import find_skill
from app.learning.models import (
    AIEvaluationCache,
    Attempt,
    EvaluationMode,
    EvaluationSource,
    Exercise,
)

STATUS_SCORE = {"correct": 100.0, "partially_correct": 50.0, "incorrect": 0.0}
ERROR_TYPES = {"GRAMMAR_ERROR", "VOCABULARY_ERROR", "SPELLING_ERROR", "WORD_ORDER_ERROR", "PRONUNCIATION_ERROR"}
SUGGESTION_TYPES = {"STYLE_SUGGESTION", "NATURALNESS_SUGGESTION", "SHORTER_ALTERNATIVE"}


@dataclass
class Evaluation:
    source: EvaluationSource
    result: dict
    score: float


def score_from_result(result: dict) -> float:
    concepts = [
        c for c in result.get("conceptResults") or [] if isinstance(c, dict) and c.get("status") in STATUS_SCORE
    ]
    if concepts:
        return round(sum(STATUS_SCORE[c["status"]] for c in concepts) / len(concepts), 1)
    return STATUS_SCORE.get(result.get("result"), 0.0)


def _result_label(score: float) -> str:
    if score >= 99.9:
        return "correct"
    if score <= 0.1:
        return "incorrect"
    return "partially_correct"


def _accepted_normalized(exercise: Exercise) -> set[str]:
    accepted = list(exercise.answer_key.get("acceptedAnswers") or [])
    if exercise.exercise_type == "fill_blank":
        accepted += fill_blank_variants(exercise.prompt, accepted)
    return {normalize_answer(a) for a in accepted if a}


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
    return {
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


def _sanitize_ai_result(exercise: Exercise, data: dict) -> dict:
    concepts = []
    for item in data.get("conceptResults") or []:
        if isinstance(item, dict) and item.get("status") in STATUS_SCORE:
            concepts.append({"concept": str(item.get("concept") or "concept"), "status": item["status"]})
    errors = [
        {
            "type": e.get("type") if e.get("type") in ERROR_TYPES else "GRAMMAR_ERROR",
            "fragment": e.get("fragment"),
            "correction": e.get("correction"),
            "explanation": e.get("explanation", ""),
        }
        for e in data.get("errors") or []
        if isinstance(e, dict)
    ]
    suggestions = [
        {
            "type": s.get("type") if s.get("type") in SUGGESTION_TYPES else "STYLE_SUGGESTION",
            "text": s.get("text", ""),
        }
        for s in data.get("suggestions") or []
        if isinstance(s, dict) and s.get("text")
    ]
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
    return _sanitize_ai_result(exercise, result.data)


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


def evaluate(db: Session, account: Account, exercise: Exercise, answer: str) -> Evaluation | None:
    """Devuelve la evaluación, o None si hace falta IA y no hay ninguna disponible."""
    normalized = normalize_answer(answer)

    if not normalized:
        result = _rule_incorrect(exercise, "")
        return Evaluation(EvaluationSource.RULE_MATCH, result, 0.0)

    if exercise.evaluation_mode != EvaluationMode.AI:
        if normalized in _accepted_normalized(exercise):
            return Evaluation(EvaluationSource.RULE_MATCH, _rule_correct(exercise), 100.0)
        for error in exercise.answer_key.get("commonErrors") or []:
            if normalize_answer(error.get("answer")) == normalized:
                result = _common_error_result(exercise, error)
                return Evaluation(
                    EvaluationSource.COMMON_ERROR_MATCH, result, score_from_result(result)
                )
        if exercise.evaluation_mode == EvaluationMode.DETERMINISTIC:
            return Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0)

    cached = _cache_get(db, exercise, normalized)
    if cached is not None:
        return Evaluation(EvaluationSource.AI, cached, score_from_result(cached))

    try:
        result = evaluate_with_ai(db, account, exercise, answer)
    except NoAIAvailable:
        return None
    _cache_put(db, exercise, normalized, result)
    return Evaluation(EvaluationSource.AI, result, score_from_result(result))


def apply_evaluation(attempt: Attempt, evaluation: Evaluation) -> None:
    attempt.evaluation_source = evaluation.source
    attempt.evaluation_result = {**evaluation.result, "score": evaluation.score}
    attempt.score = evaluation.score
    attempt.evaluated_at = utcnow()
