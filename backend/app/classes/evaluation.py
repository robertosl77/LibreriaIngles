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
from app.ai.usage import AIUsageContext
from app.classes.reference import exercise_display_number
from app.classes.normalize import fill_blank_variants, normalize_answer
from app.classes.prompts import (
    BATCH_EVALUATION_NOTE,
    EVALUATION_BATCH_SCHEMA,
    EVALUATION_SCHEMA,
    evaluation_batch_user_prompt,
    evaluation_system,
    evaluation_user_prompt,
    short_skill_key,
)
from app.classes.spelling import SPELLING_SCORE, spelling_slips
from app.classes.spoken import normalize_spoken, pronunciation_slips
from app.core.config import settings
from app.curriculum.service import find_skill, get_level
from app.learning.models import (
    AIEvaluationCache,
    Attempt,
    ClassSession,
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


ORTHOGRAPHY_SKILLS = {
    "capitalization": "writing.orthography.capitalization",
    "spelling": "writing.orthography.basic_spelling",
    "punctuation": "writing.orthography.punctuation",
    "apostrophes": "writing.orthography.apostrophes",
}
SECONDARY_MAX = 3


def _secondary_areas(exercise: Exercise) -> list[str]:
    """Áreas del catálogo que pueden recibir evidencia incidental de esta respuesta (T-170)."""
    level = getattr(exercise, "level", None)
    response_mode = getattr(exercise, "response_mode", None)
    if not level or not response_mode or response_mode.value == "SELECT":
        return []
    if get_level(level) is None:
        return []
    areas = ["grammar", "vocabulary"]
    if response_mode.value == "WRITE":
        areas.append("writing")
    return areas


def _full_skill_key(exercise: Exercise, key: str) -> str:
    """La IA usa claves cortas del catálogo (sin nivel); se completan con el nivel del ejercicio."""
    prefix = f"{(getattr(exercise, 'level', None) or '').lower()}."
    if prefix != "." and not key.startswith(prefix):
        return prefix + key
    return key


def _secondary_skill_candidates(exercise: Exercise) -> list[dict]:
    """Skills que la IA puede observar incidentalmente en una respuesta productiva.

    Ya no viajan en cada pedido (T-170): el catálogo va en el system prompt del nivel. Se usan
    para filtrar lo que devuelve la IA y para el proveedor simulado.
    """
    areas = set(_secondary_areas(exercise))
    if not areas:
        return []
    curriculum = get_level(exercise.level)
    candidates = []
    for skill in curriculum.skills:
        if skill.key == exercise.skill_key or skill.area_key not in areas:
            continue
        candidates.append(
            {
                "skillKey": skill.key,
                "name": f"{skill.topic_name} · {skill.name}",
                "objectives": list(skill.objectives),
            }
        )
    return candidates


def _sanitize_secondary(exercise: Exercise, data: dict) -> list[dict]:
    allowed = {item["skillKey"] for item in _secondary_skill_candidates(exercise)}
    result = []
    seen = set()
    for item in data.get("secondarySkillResults") or []:
        if not isinstance(item, dict):
            continue
        key = _full_skill_key(exercise, str(item.get("skillKey") or ""))
        status = item.get("status")
        if key not in allowed or key in seen or status not in STATUS_SCORE:
            continue
        score = item.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = STATUS_SCORE[status]
        low, high = STATUS_BANDS[status]
        result.append(
            {
                "skillKey": key,
                "status": status,
                "score": round(min(high, max(low, float(score))), 1),
                "reason": str(item.get("reason") or "")[:300],
            }
        )
        seen.add(key)
        if len(result) >= SECONDARY_MAX:
            break
    return result


def _orthography_key(exercise: Exercise, suffix: str) -> str | None:
    level = (exercise.level or "").lower()
    if not level:
        return None
    key = f"{level}.{ORTHOGRAPHY_SKILLS[suffix]}"
    return key if find_skill(key) else None


def _merge_secondary(result: dict, item: dict) -> None:
    current = {
        row.get("skillKey"): row
        for row in result.setdefault("secondarySkillResults", [])
        if isinstance(row, dict) and row.get("skillKey")
    }
    current[item["skillKey"]] = item
    result["secondarySkillResults"] = list(current.values())


def _surface_normalize(value: str) -> str:
    return " ".join(value.replace("’", "'").split())


def _orthography_primary(exercise: Exercise, answer: str) -> Evaluation | None:
    """Capitalización, puntuación y apóstrofes necesitan comparar la forma escrita, no solo significado."""
    key = getattr(exercise, "skill_key", None) or ""
    if ".writing.orthography." not in key or key.endswith(".basic_spelling"):
        return None
    accepted = _accepted(exercise)
    if not accepted:
        return None
    surface = _surface_normalize(answer)
    if surface in {_surface_normalize(item) for item in accepted}:
        return Evaluation(EvaluationSource.RULE_MATCH, _rule_correct(exercise), 100.0)

    # Si las palabras son correctas pero falla justo la convención ortográfica objetivo,
    # conserva evidencia parcial en lugar de convertirlo en un error gramatical.
    if any(normalize_spoken(answer) == normalize_spoken(item) for item in accepted):
        result = {
            "result": "partially_correct",
            "conceptResults": [
                {"concept": concept, "status": "partially_correct", "score": 60}
                for concept in exercise.expected_concepts or ["orthography"]
            ],
            "errors": [],
            "correctAnswer": accepted[0],
            "feedback": "El contenido está bien, pero revisá la convención ortográfica que practica este ejercicio.",
            "suggestions": [
                {"type": "MECHANICS_NOTE", "text": "Revisá mayúsculas, puntuación o apóstrofes según la consigna."}
            ],
        }
        return Evaluation(EvaluationSource.RULE_MATCH, result, 60.0)
    return Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0)


def _add_mechanics_evidence(exercise: Exercise, answer: str, result: dict, *, spoken: bool) -> dict:
    """Capitalización/puntuación observables: evidencia curricular, sin tocar la nota principal."""
    response_mode = getattr(exercise, "response_mode", None)
    if spoken or not answer.strip() or not response_mode or response_mode.value != "WRITE":
        return result
    # Solo producción de oraciones; un fill_blank de una palabra no demuestra puntuación.
    if exercise.exercise_type not in {"short_writing", "conversation"} and getattr(exercise, "area", None) != "writing":
        return result

    text = answer.strip()
    words = text.split()
    cap_key = _orthography_key(exercise, "capitalization")
    if cap_key and cap_key != exercise.skill_key:
        first_alpha = next((ch for ch in text if ch.isalpha()), "")
        lowercase_i = any(token.strip(".,!?;:'\"()") == "i" for token in words)
        ok = bool(first_alpha) and first_alpha.isupper() and not lowercase_i
        _merge_secondary(
            result,
            {
                "skillKey": cap_key,
                "status": "correct" if ok else "partially_correct",
                "score": 100.0 if ok else 60.0,
                "reason": "Mayúsculas correctas." if ok else "Revisá mayúscula inicial, nombres propios y el pronombre I.",
            },
        )

    punctuation_key = _orthography_key(exercise, "punctuation")
    if punctuation_key and punctuation_key != exercise.skill_key and len(words) >= 2:
        ok = text.endswith((".", "?", "!"))
        _merge_secondary(
            result,
            {
                "skillKey": punctuation_key,
                "status": "correct" if ok else "partially_correct",
                "score": 100.0 if ok else 60.0,
                "reason": "Puntuación de cierre correcta." if ok else "Falta o no corresponde la puntuación de cierre.",
            },
        )

    spelling_key = _orthography_key(exercise, "spelling")
    if spelling_key and spelling_key != exercise.skill_key:
        spelling_errors = [e for e in result.get("errors") or [] if e.get("type") == "SPELLING_ERROR"]
        if spelling_errors:
            _merge_secondary(
                result,
                {
                    "skillKey": spelling_key,
                    "status": "partially_correct",
                    "score": 65.0,
                    "reason": "La respuesta contiene un error ortográfico reconocible.",
                },
            )
    return result


def _conversation_context(db: Session, exercise: Exercise) -> list[dict]:
    meta = (exercise.content or {}).get("conversation") or {}
    group = meta.get("group")
    if not group:
        return []
    siblings = list(
        db.scalars(
            select(Exercise)
            .where(Exercise.class_session_id == exercise.class_session_id)
            .order_by(Exercise.position)
        ).all()
    )
    siblings = [
        item for item in siblings
        if ((item.content or {}).get("conversation") or {}).get("group") == group
        and item.position <= exercise.position
    ]
    session = db.get(ClassSession, exercise.class_session_id)
    attempt_number = session.current_attempt if session else 1
    attempts = {
        a.exercise_id: a
        for a in db.scalars(
            select(Attempt).where(
                Attempt.exercise_id.in_([item.id for item in siblings]),
                Attempt.attempt_number == attempt_number,
            )
        ).all()
    } if siblings else {}
    history = []
    for item in siblings:
        partner = (
            (item.content or {}).get("stimulus")
            if item.presentation_mode and item.presentation_mode.value == "LISTEN"
            else item.prompt
        )
        row = {"partner": partner}
        if item.id != exercise.id and item.id in attempts:
            row["student"] = attempts[item.id].raw_answer
        history.append(row)
    return history


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
        "secondarySkillResults": _sanitize_secondary(exercise, data),
        "scoreSuggestedByAI": data.get("scoreSuggested"),
    }
    score = score_from_result(result)
    result["result"] = _result_label(score)
    return result


def _ai_payload(db: Session, exercise: Exercise, answer: str) -> dict:
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
        "skillKey": short_skill_key(exercise.skill_key or ""),
        "secondaryAreas": _secondary_areas(exercise),
        "conversationContext": _conversation_context(db, exercise),
        "studentAnswer": answer,
    }


def _text_list_chars(values) -> int:
    return sum(len(str(value or "")) for value in (values or []))


def _evaluation_diagnostic(payload: dict) -> dict:
    """Métricas del payload real de evaluación, sin conservar su contenido textual."""
    conversation = [item for item in (payload.get("conversationContext") or []) if isinstance(item, dict)]
    conversation_chars = sum(
        len(str(item.get("partner") or "")) + len(str(item.get("student") or ""))
        for item in conversation
    )
    options = payload.get("options") or []
    references = payload.get("referenceAnswers") or []
    objectives = payload.get("objectives") or []
    return {
        "exerciseType": payload.get("type"),
        "presentationMode": payload.get("presentation"),
        "responseMode": payload.get("response"),
        "instructionChars": len(str(payload.get("instruction") or "")),
        "questionChars": len(str(payload.get("question") or "")),
        "passageChars": len(str(payload.get("passage") or "")),
        "stimulusChars": len(str(payload.get("stimulus") or "")),
        "answerChars": len(str(payload.get("studentAnswer") or "")),
        "optionCount": len(options),
        "optionsChars": _text_list_chars(options),
        "referenceAnswerCount": len(references),
        "referenceAnswersChars": _text_list_chars(references),
        "objectiveCount": len(objectives),
        "objectivesChars": _text_list_chars(objectives),
        "expectedConceptCount": len(payload.get("expectedConcepts") or []),
        "secondaryAreaCount": len(payload.get("secondaryAreas") or []),
        "conversationTurns": len(conversation),
        "conversationChars": conversation_chars,
    }


def evaluate_with_ai(db: Session, account: Account, exercise: Exercise, answer: str) -> dict:
    payload = _ai_payload(db, exercise, answer)
    result = run_json_task(
        db,
        account,
        system=evaluation_system(exercise.level),
        user=evaluation_user_prompt(payload),
        task={
            "kind": "evaluate_answer",
            "schema": EVALUATION_SCHEMA,
            "exercise": {
                "type": exercise.exercise_type,
                "acceptedAnswers": payload["referenceAnswers"],
                "expectedConcepts": payload["expectedConcepts"],
                "secondarySkillCandidates": _secondary_skill_candidates(exercise),
            },
            "answer": answer,
        },
        usage_context=AIUsageContext(
            organization_id=exercise.organization_id,
            membership_id=exercise.membership_id,
            subject_type="EXERCISE",
            subject_id=exercise.id,
            subject_label=(
                f"{'Examen' if (session := db.get(ClassSession, exercise.class_session_id)) and session.kind.value == 'EXAM' else 'Clase'} "
                f"#{exercise.class_session_id} · Ejercicio {exercise_display_number(db, exercise)}"
            ),
            subject_route=f"/app/clase/{exercise.class_session_id}",
            diagnostic=_evaluation_diagnostic(payload),
        ),
    )
    sanitized = _sanitize_ai_result(exercise, result.data)
    spoken = bool(
        getattr(exercise, "response_mode", None)
        and exercise.response_mode.value == "SPEAK"
    )
    sanitized = _add_mechanics_evidence(exercise, answer, sanitized, spoken=spoken)
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


def _finish(exercise: Exercise, answer: str, evaluation: Evaluation, *, spoken: bool) -> Evaluation:
    evaluation.result = _add_mechanics_evidence(
        exercise, answer, evaluation.result, spoken=spoken
    )
    return evaluation


# ---------------------------------------------------------------- T-172 reglas primero en cerrados

REWRITE_MIN_OVERLAP = 0.5  # rewrite que comparte menos de la mitad de las palabras: incorrecto por regla
CLOSED_RULE_FEEDBACK = (
    "No es la respuesta esperada. Si creés que tu respuesta es correcta, podés pedir que la revisen."
)


def _word_overlap(accepted: list[str], answer: str) -> float:
    """Mayor proporción de palabras de una respuesta aceptada que aparecen en la del alumno."""
    said = set(normalize_answer(answer).split())
    best = 0.0
    for item in accepted:
        words = set(normalize_answer(item).split())
        if words:
            best = max(best, len(words & said) / len(words))
    return best


def _closed_rule_incorrect(exercise: Exercise, answer: str) -> Evaluation | None:
    """fill_blank/rewrite ESCRITOS que no coinciden con nada conocido: incorrecto sin IA.

    `acceptedAnswers` es exhaustiva por regla de generación; si faltaba una variante válida,
    la apelación (IA) la corrige y la incorpora a la answer key.
    """
    if not settings.ai_rule_first_closed:
        return None
    if exercise.exercise_type == "fill_blank":
        pass
    elif exercise.exercise_type == "rewrite":
        if _word_overlap(_accepted(exercise), answer) >= REWRITE_MIN_OVERLAP:
            return None  # parecida: puede ser una variante válida, decide la IA
    else:
        return None
    result = _rule_incorrect(exercise, answer)
    result["feedback"] = CLOSED_RULE_FEEDBACK
    return Evaluation(EvaluationSource.RULE_MATCH, result, 0.0)


# ---------------------------------------------------------------- cascada


def _normalizer(spoken: bool):
    return normalize_spoken if spoken else normalize_answer


def evaluate_without_ai(
    db: Session, exercise: Exercise, answer: str, *, spoken: bool = False
) -> Evaluation | None:
    """Reglas, errores comunes, ortografía y caché. None = hace falta la IA."""
    normalize = _normalizer(spoken)
    normalized = normalize(answer)

    if not normalized:
        result = _rule_incorrect(exercise, "")
        return _finish(exercise, answer, Evaluation(EvaluationSource.RULE_MATCH, result, 0.0), spoken=spoken)

    if not spoken:
        orthography = _orthography_primary(exercise, answer)
        if orthography is not None:
            return _finish(exercise, answer, orthography, spoken=False)

    if exercise.evaluation_mode != EvaluationMode.AI:
        if normalized in _accepted_normalized(exercise, normalize):
            return _finish(exercise, answer, Evaluation(EvaluationSource.RULE_MATCH, _rule_correct(exercise), 100.0), spoken=spoken)
        if spoken:
            slips = pronunciation_slips(_accepted(exercise), answer)
            if slips:
                result = _pronunciation_slip_result(exercise, slips)
                return _finish(exercise, answer, Evaluation(EvaluationSource.RULE_MATCH, result, score_from_result(result)), spoken=spoken)
        for error in exercise.answer_key.get("commonErrors") or []:
            if normalize(error.get("answer")) == normalized:
                result = _common_error_result(exercise, error)
                return _finish(
                    exercise,
                    answer,
                    Evaluation(EvaluationSource.COMMON_ERROR_MATCH, result, score_from_result(result)),
                    spoken=spoken,
                )
        if not spoken and exercise.exercise_type not in CHOICE_TYPES:
            slips = spelling_slips(_accepted(exercise), answer)
            if slips:
                return _finish(
                    exercise,
                    answer,
                    Evaluation(EvaluationSource.RULE_MATCH, _spelling_result(exercise, slips), SPELLING_SCORE),
                    spoken=spoken,
                )
        # Una transcripción puede diferir por cosas del habla: decide la IA si la hay.
        if exercise.evaluation_mode == EvaluationMode.DETERMINISTIC and not spoken:
            return _finish(exercise, answer, Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0), spoken=spoken)
        if not spoken:
            closed = _closed_rule_incorrect(exercise, answer)
            if closed is not None:
                return _finish(exercise, answer, closed, spoken=False)

    cached = _cache_get(db, exercise, normalized)
    if cached is not None:
        return _finish(exercise, answer, Evaluation(EvaluationSource.AI, dict(cached), ai_score(exercise, cached)), spoken=spoken)
    return None


def evaluate(
    db: Session, account: Account, exercise: Exercise, answer: str, *, spoken: bool = False
) -> Evaluation | None:
    """Devuelve la evaluación, o None si hace falta IA y no hay ninguna disponible.

    Con respuesta hablada (`spoken`) se compara la transcripción sin puntuación, y una
    palabra que suena parecida a la esperada es error de pronunciación, no de contenido.
    """
    evaluation = evaluate_without_ai(db, exercise, answer, spoken=spoken)
    if evaluation is not None:
        return evaluation
    try:
        result = evaluate_with_ai(db, account, exercise, answer)
    except NoAIAvailable:
        if spoken and exercise.evaluation_mode == EvaluationMode.DETERMINISTIC:
            return _finish(exercise, answer, Evaluation(EvaluationSource.RULE_MATCH, _rule_incorrect(exercise, answer), 0.0), spoken=spoken)
        return None
    _cache_put(db, exercise, _normalizer(spoken)(answer), result)
    return _finish(exercise, answer, Evaluation(EvaluationSource.AI, result, ai_score(exercise, result)), spoken=spoken)


# ---------------------------------------------------------------- T-171 corrección por lote


def evaluate_batch_with_ai(
    db: Session,
    account: Account,
    session: ClassSession,
    items: list[tuple[Exercise, str, bool]],
) -> dict[int, Evaluation]:
    """Corrige en UNA llamada varias respuestas que necesitan IA. Devuelve lo que la IA resolvió;
    lo que falte (o si la llamada falla) lo corrige el llamador uno por uno, como antes."""
    if not items:
        return {}
    level = items[0][0].level
    payloads = []
    for exercise, answer, _spoken in items:
        payload = _ai_payload(db, exercise, answer)
        payload.pop("level", None)
        payloads.append({"id": exercise.id, **payload})
    exam = session.kind.value == "EXAM"
    try:
        result = run_json_task(
            db,
            account,
            system=evaluation_system(level) + BATCH_EVALUATION_NOTE,
            user=evaluation_batch_user_prompt(level, payloads),
            task={
                "kind": "evaluate_batch",
                "schema": EVALUATION_BATCH_SCHEMA,
                "items": [
                    {
                        "id": exercise.id,
                        "type": exercise.exercise_type,
                        "acceptedAnswers": exercise.answer_key.get("acceptedAnswers") or [],
                        "expectedConcepts": exercise.expected_concepts or [],
                        "secondarySkillCandidates": _secondary_skill_candidates(exercise),
                        "answer": answer,
                    }
                    for exercise, answer, _spoken in items
                ],
            },
            usage_context=AIUsageContext(
                organization_id=session.organization_id,
                membership_id=session.membership_id,
                subject_type=session.kind.value,
                subject_id=session.id,
                subject_label=f"{'Examen' if exam else 'Clase'} #{session.id} · corrección de {len(items)} ejercicios",
                subject_route=f"/app/clase/{session.id}",
                diagnostic=_batch_diagnostic(payloads),
            ),
        )
    except NoAIAvailable:
        return {}

    raw: dict[int, dict] = {}
    for row in result.data.get("results") or []:
        if not isinstance(row, dict):
            continue
        try:
            raw.setdefault(int(row.get("id")), row)
        except (TypeError, ValueError):
            continue

    snapshot = connection_snapshot(result.connection)
    evaluations: dict[int, Evaluation] = {}
    for exercise, answer, spoken in items:
        data = raw.get(exercise.id)
        if data is None:
            continue
        sanitized = _sanitize_ai_result(exercise, data)
        sanitized = _add_mechanics_evidence(exercise, answer, sanitized, spoken=spoken)
        sanitized = {**sanitized, "ai": snapshot}
        _cache_put(db, exercise, _normalizer(spoken)(answer), sanitized)
        evaluations[exercise.id] = _finish(
            exercise, answer, Evaluation(EvaluationSource.AI, sanitized, ai_score(exercise, sanitized)), spoken=spoken
        )
    return evaluations


def _batch_diagnostic(payloads: list[dict]) -> dict:
    types: dict[str, int] = {}
    for payload in payloads:
        key = str(payload.get("type"))
        types[key] = types.get(key, 0) + 1
    return {
        "itemCount": len(payloads),
        "typeCounts": types,
        "answerChars": sum(len(str(p.get("studentAnswer") or "")) for p in payloads),
        "conversationTurns": sum(len(p.get("conversationContext") or []) for p in payloads),
    }


def apply_evaluation(attempt: Attempt, evaluation: Evaluation) -> None:
    attempt.evaluation_source = evaluation.source
    attempt.evaluation_result = {**evaluation.result, "score": evaluation.score}
    attempt.score = evaluation.score
    attempt.evaluated_at = utcnow()
