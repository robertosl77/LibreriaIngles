"""Tipos de ejercicio y sus reglas (T-183).

Concentra lo que distingue a cada tipo: cómo se presenta, cómo se responde, qué arma el
backend (fichas, columnas mezcladas) y cómo se corrige por regla, sin IA.

Las respuestas siguen siendo texto. Los tipos con varias partes guardan JSON:
  match_pairs → {"kitchen": "cocina", ...}
  listen_form → {"Name": "Anna", ...}
  gap_text    → ["get", "have", "go"]
"""

from __future__ import annotations

import json
import random
import re
from difflib import SequenceMatcher

from app.classes.normalize import normalize_answer
from app.classes.spelling import is_minor_typo
from app.classes.spoken import normalize_spoken, sounds_alike

# ---------------------------------------------------------------- catálogo

BASE_TYPES = {
    "fill_blank",
    "multiple_choice",
    "reading_multiple_choice",
    "rewrite",
    "short_writing",
    "conversation",
}
NEW_TYPES = {
    "dictation",
    "word_order",
    "dialogue_choice",
    "read_aloud",
    "minimal_pairs",
    "match_pairs",
    "listen_form",
    "gap_text",
    "error_correction",
    "word_stress",
}
ALL_TYPES = BASE_TYPES | NEW_TYPES

# Se elige una opción: corrección exacta por regla.
CHOICE_TYPES = {"multiple_choice", "reading_multiple_choice", "dialogue_choice", "minimal_pairs", "word_stress"}
# Respuesta con varias partes (JSON).
STRUCTURED_TYPES = {"match_pairs", "listen_form", "gap_text"}
# Se corrigen siempre por regla (nunca IA, tampoco al apelar).
# word_stress: las opciones difieren solo en mayúsculas (ba-NA-na): se compara exacto.
RULE_ONLY_TYPES = {"dictation", "word_order", "read_aloud", "word_stress"} | STRUCTURED_TYPES
CASE_SENSITIVE_TYPES = {"word_stress"}
# Presentación fija: el tipo no tiene sentido de otra forma.
LISTEN_ONLY_TYPES = {"dictation", "minimal_pairs", "word_stress", "listen_form"}
READ_ONLY_TYPES = {"word_order", "match_pairs", "gap_text", "read_aloud", "error_correction"}
SPEAK_ONLY_TYPES = {"read_aloud"}
# El estímulo escuchado puede aparecer en las opciones (es justamente lo que se elige).
STIMULUS_MAY_REPEAT = {"fill_blank", "minimal_pairs", "word_stress"}
# La apelación usa IA: no tiene sentido en tipos de corrección exacta por regla.
NO_APPEAL_TYPES = RULE_ONLY_TYPES | {"dialogue_choice", "minimal_pairs", "word_stress"}

TYPE_NAMES = {
    "dictation": "Dictado",
    "word_order": "Ordenar palabras",
    "dialogue_choice": "Elegir la respuesta",
    "read_aloud": "Leer en voz alta",
    "minimal_pairs": "Sonidos parecidos",
    "match_pairs": "Emparejar",
    "listen_form": "Formulario escuchado",
    "gap_text": "Texto con huecos",
    "error_correction": "Corregir el error",
    "word_stress": "Acento de la palabra",
}

WORD_ORDER_MIN, WORD_ORDER_MAX = 3, 12
PAIRS_MIN, PAIRS_MAX = 3, 6
FIELDS_MIN, FIELDS_MAX = 2, 5
GAPS_MIN, GAPS_MAX = 2, 5
SLIP_CREDIT = 0.75  # palabra con tipeo menor o que "suena parecido": cuenta, pero no completa


def fixed_presentation(exercise_type: str) -> str | None:
    if exercise_type in LISTEN_ONLY_TYPES:
        return "LISTEN"
    if exercise_type in READ_ONLY_TYPES:
        return "READ"
    return None


# ---------------------------------------------------------------- armado (backend, sin IA)

_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def sentence_words(sentence: str) -> list[str]:
    return _WORD.findall(sentence or "")


def _seeded(seed_text: str) -> random.Random:
    return random.Random(sum(ord(c) * (i + 1) for i, c in enumerate(seed_text)))


def shuffled(items: list[str], seed_text: str) -> list[str]:
    """Mezcla determinística y distinta del orden original (si hay más de un elemento distinto)."""
    result = list(items)
    if len(set(items)) < 2:
        return result
    rng = _seeded(seed_text)
    for _ in range(10):
        rng.shuffle(result)
        if result != items:
            break
    return result


def word_tiles(sentence: str) -> list[str]:
    """Fichas de word_order: las palabras de la oración, mezcladas y sin la mayúscula inicial."""
    words = sentence_words(sentence)
    if words and words[0] != "I" and not words[0].isupper():
        words[0] = words[0][:1].lower() + words[0][1:]
    return shuffled(words, sentence)


def same_words(a: str, b: str) -> bool:
    return sorted(normalize_answer(w) for w in sentence_words(a)) == sorted(
        normalize_answer(w) for w in sentence_words(b)
    )


def parse_structured(text: str | None, kind: str):
    """Respuesta JSON de un tipo estructurado; None si no se puede leer."""
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError):
        return None
    if kind == "gap_text":
        return [str(v) if v is not None else "" for v in value] if isinstance(value, list) else None
    if isinstance(value, dict):
        return {str(k): str(v) if v is not None else "" for k, v in value.items()}
    return None


def format_answer(exercise_type: str, text: str | None) -> str:
    """Respuesta legible para mostrar (los estructurados se guardan como JSON)."""
    if exercise_type not in STRUCTURED_TYPES:
        return text or ""
    value = parse_structured(text, exercise_type)
    if value is None:
        return text or ""
    if isinstance(value, list):
        return " · ".join(v or "—" for v in value)
    joiner = " = " if exercise_type == "match_pairs" else ": "
    return " · ".join(f"{k}{joiner}{v or '—'}" for k, v in value.items())


# ---------------------------------------------------------------- corrección por regla


def _status(score: float) -> str:
    if score >= 99.9:
        return "correct"
    if score >= 35:
        return "partially_correct"
    return "incorrect"


def _result(exercise, score: float, *, errors: list[dict], correct_answer: str | None, feedback: str) -> dict:
    score = round(max(0.0, min(100.0, score)), 1)
    status = _status(score)
    return {
        "result": status,
        "conceptResults": [
            {"concept": c, "status": status, "score": score}
            for c in (exercise.expected_concepts or ["task_completion"])
        ],
        "errors": errors,
        "correctAnswer": correct_answer,
        "feedback": feedback,
        "suggestions": [],
        "_score": score,
    }


def _align(expected: list[str], said: list[str], tolerant) -> tuple[float, list[dict]]:
    """Compara dos listas de palabras. Devuelve (aciertos ponderados, errores)."""
    matcher = SequenceMatcher(a=expected, b=said, autojunk=False)
    credit = 0.0
    errors: list[dict] = []
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            credit += a1 - a0
            continue
        exp, got = expected[a0:a1], said[b0:b1]
        if op == "replace" and len(exp) == len(got):
            for e, g in zip(exp, got):
                kind = tolerant(e, g)
                if kind:
                    credit += SLIP_CREDIT
                    errors.append({"type": kind, "fragment": g, "correction": e, "explanation": _SLIP_TEXT[kind]})
                else:
                    errors.append({"type": "VOCABULARY_ERROR", "fragment": g, "correction": e, "explanation": "Palabra distinta."})
            continue
        if exp and got:
            errors.append({"type": "VOCABULARY_ERROR", "fragment": " ".join(got), "correction": " ".join(exp), "explanation": "No coincide con lo esperado."})
        elif exp:
            errors.append({"type": "VOCABULARY_ERROR", "fragment": "—", "correction": " ".join(exp), "explanation": "Faltan palabras."})
        else:
            errors.append({"type": "VOCABULARY_ERROR", "fragment": " ".join(got), "correction": "—", "explanation": "Sobran palabras."})
    return credit, errors


_SLIP_TEXT = {
    "SPELLING_ERROR": "Ortografía.",
    "PRONUNCIATION_ERROR": "Se entendió otra palabra parecida: cuidá la pronunciación.",
}


def _typo(expected: str, said: str) -> str | None:
    return "SPELLING_ERROR" if is_minor_typo(expected, said) else None


def _sound(expected: str, said: str) -> str | None:
    return "PRONUNCIATION_ERROR" if sounds_alike(expected, said) else None


def _sentence_score(accepted: list[str], answer: str, *, spoken: bool) -> tuple[float, list[dict], str]:
    """Mejor coincidencia palabra por palabra contra las respuestas aceptadas."""
    normalize = normalize_spoken if spoken else normalize_answer
    tolerant = _sound if spoken else _typo
    said = normalize(answer).split()
    best = (-1.0, [], accepted[0] if accepted else "")
    for option in accepted:
        expected = normalize(option).split()
        if not expected:
            continue
        credit, errors = _align(expected, said, tolerant)
        score = 100.0 * credit / max(len(expected), len(said))
        if score > best[0]:
            best = (score, errors, option)
    return best


def evaluate_rule_type(exercise, answer: str, *, spoken: bool = False) -> dict | None:
    """Corrección por regla de los tipos RULE_ONLY_TYPES. None si el tipo no es de esta familia.

    Devuelve el resultado con la nota en "_score" (el llamador la saca y arma la Evaluation).
    """
    kind = exercise.exercise_type
    key = exercise.answer_key or {}
    accepted = [a for a in key.get("acceptedAnswers") or [] if a]

    if kind in ("dictation", "read_aloud"):
        if not accepted:
            return None
        score, errors, target = _sentence_score(accepted, answer, spoken=spoken)
        if score >= 99.9:
            feedback = "¡Perfecto!" if kind == "dictation" else "¡Muy bien leído!"
        elif kind == "dictation":
            feedback = "Revisá las palabras marcadas: compará con lo que decía el audio."
        else:
            feedback = "Se entendió parte de la oración: repetí las palabras marcadas."
        return _result(exercise, score, errors=errors[:6], correct_answer=target, feedback=feedback)

    if kind == "word_order":
        if not accepted:
            return None
        said = normalize_answer(answer)
        if said in {normalize_answer(a) for a in accepted}:
            return _result(exercise, 100, errors=[], correct_answer=accepted[0], feedback="¡Correcto!")
        best = max(
            SequenceMatcher(a=normalize_answer(a).split(), b=said.split(), autojunk=False).ratio() for a in accepted
        )
        # Casi bien ordenada: parcial; nunca 100 si el orden no es válido.
        score = min(84.0, round(best * 100 - 15, 1)) if best >= 0.6 else 0.0
        return _result(
            exercise,
            score,
            errors=[{"type": "WORD_ORDER_ERROR", "fragment": answer, "correction": accepted[0], "explanation": "Revisá el orden de las palabras."}],
            correct_answer=accepted[0],
            feedback="El orden no es correcto." if score == 0 else "Casi: revisá el orden de algunas palabras.",
        )

    if kind == "word_stress":
        if not accepted:
            return None
        ok = answer.strip() in {a.strip() for a in accepted}
        return _result(
            exercise, 100 if ok else 0, errors=[], correct_answer=accepted[0],
            feedback="¡Correcto!" if ok else "La sílaba fuerte es otra: escuchá de nuevo el audio.",
        )

    if kind == "match_pairs":
        pairs: dict = key.get("pairs") or {}
        given = parse_structured(answer, kind) or {}
        if not pairs:
            return None
        wrong = [left for left, right in pairs.items() if normalize_answer(given.get(left)) != normalize_answer(right)]
        score = 100.0 * (len(pairs) - len(wrong)) / len(pairs)
        errors = [
            {"type": "VOCABULARY_ERROR", "fragment": f"{left} = {given.get(left) or '—'}", "correction": f"{left} = {pairs[left]}", "explanation": "Par incorrecto."}
            for left in wrong
        ]
        return _result(
            exercise, score, errors=errors,
            correct_answer=" · ".join(f"{k} = {v}" for k, v in pairs.items()),
            feedback="¡Todos los pares están bien!" if not wrong else f"{len(pairs) - len(wrong)} de {len(pairs)} pares correctos.",
        )

    if kind == "listen_form":
        fields: dict = key.get("fields") or {}
        given = parse_structured(answer, kind) or {}
        if not fields:
            return None
        credit, errors = 0.0, []
        for label, options in fields.items():
            value = given.get(label) or ""
            normalized = normalize_answer(value)
            if normalized and normalized in {normalize_answer(o) for o in options}:
                credit += 1
                continue
            slips = _field_slips(options, value)
            if slips:
                credit += SLIP_CREDIT
                errors.append({"type": "SPELLING_ERROR", "fragment": f"{label}: {value}", "correction": f"{label}: {options[0]}", "explanation": "Ortografía."})
            else:
                errors.append({"type": "VOCABULARY_ERROR", "fragment": f"{label}: {value or '—'}", "correction": f"{label}: {options[0]}", "explanation": "No coincide con el audio."})
        score = 100.0 * credit / len(fields)
        return _result(
            exercise, score, errors=errors,
            correct_answer=" · ".join(f"{k}: {v[0]}" for k, v in fields.items()),
            feedback="¡Formulario completo y correcto!" if not errors else "Revisá los datos marcados: volvé a escuchar el audio.",
        )

    if kind == "gap_text":
        gaps: list = key.get("gaps") or []
        given = parse_structured(answer, kind) or []
        if not gaps:
            return None
        errors = []
        correct = 0
        for index, options in enumerate(gaps):
            value = given[index] if index < len(given) else ""
            if normalize_answer(value) in {normalize_answer(o) for o in options}:
                correct += 1
            else:
                errors.append({"type": "GRAMMAR_ERROR", "fragment": f"{index + 1}. {value or '—'}", "correction": options[0], "explanation": f"Hueco {index + 1}."})
        score = 100.0 * correct / len(gaps)
        return _result(
            exercise, score, errors=errors,
            correct_answer=" · ".join(g[0] for g in gaps),
            feedback="¡Todos los huecos están bien!" if not errors else f"{correct} de {len(gaps)} huecos correctos.",
        )
    return None


def _field_slips(options: list[str], value: str) -> bool:
    said = normalize_answer(value).split()
    for option in options:
        expected = normalize_answer(option).split()
        if len(expected) != len(said) or not expected:
            continue
        diffs = [(e, s) for e, s in zip(expected, said) if e != s]
        if diffs and len(diffs) <= 1 and all(is_minor_typo(e, s) for e, s in diffs):
            return True
    return False
