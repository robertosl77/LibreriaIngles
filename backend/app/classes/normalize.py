"""Normalización de respuestas para la evaluación por reglas.

"doesn't" y "does not" deben considerarse iguales; también mayúsculas,
espacios, apóstrofes tipográficos y la puntuación final.
"""

import re

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
_QUOTES = "\"“”«»"

_IRREGULAR = {
    "won't": "will not",
    "can't": "can not",
    "cannot": "can not",
    "shan't": "shall not",
    "ain't": "am not",
}
_SUFFIXES = [
    (re.compile(r"\b(\w+)n't\b"), r"\1 not"),
    (re.compile(r"\b(\w+)'re\b"), r"\1 are"),
    (re.compile(r"\bi'm\b"), "i am"),
    (re.compile(r"\b(\w+)'ll\b"), r"\1 will"),
    (re.compile(r"\b(\w+)'ve\b"), r"\1 have"),
]
# "'s" y "'d" son ambiguos (is/has/posesivo, would/had): se dejan como están.


def normalize_answer(text: str | None) -> str:
    if not text:
        return ""
    value = text.translate(_APOSTROPHES).lower().strip()
    value = value.strip(_QUOTES).strip()
    value = re.sub(r"\s+", " ", value)
    for contraction, expanded in _IRREGULAR.items():
        value = re.sub(rf"\b{re.escape(contraction)}\b", expanded, value)
    # "'re running" (respuesta de un hueco) → "are running"
    value = re.sub(r"^'re\b", "are", value)
    value = re.sub(r"^'m\b", "am", value)
    for pattern, replacement in _SUFFIXES:
        value = pattern.sub(replacement, value)
    value = re.sub(r"\s+([,.!?;:])", r"\1", value)
    value = value.rstrip(".!?;: ").strip()
    return value


BLANK = "___"


def normalize_blank(question: str) -> str:
    """Unifica huecos escritos como ____ o …… en '___'."""
    return re.sub(r"_{2,}|…{2,}|\.{4,}", BLANK, question)


def fill_blank_variants(question: str, answers: list[str]) -> list[str]:
    """Si el alumno escribe la oración completa en vez de solo el hueco, también vale."""
    if BLANK not in question:
        return []
    variants = []
    for answer in answers:
        sentence = question.replace(BLANK, answer, 1)
        # "(watch)" es una pista del ejercicio, no parte de la respuesta.
        sentence = re.sub(r"\s*\([^)]*\)", "", sentence)
        variants.append(sentence)
    return variants
