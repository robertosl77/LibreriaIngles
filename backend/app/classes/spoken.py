"""Respuestas habladas (T-034): lo que se compara es la transcripción.

- La puntuación y las mayúsculas no existen al hablar: se ignoran.
- Una palabra dicha como otra parecida (think → sink, very → berry) no es un
  error de contenido: el alumno sabía la palabra, la pronunció mal. Se marca
  PRONUNCIATION_ERROR y el contenido cuenta como correcto. Esto se resuelve
  sin IA cuando la transcripción coincide palabra por palabra salvo esos
  pares; los casos más difusos los decide la IA (regla en EVALUATION_SYSTEM).
"""

import re

from app.classes.normalize import normalize_answer

# Pares mínimos frecuentes en hispanohablantes (ambos sentidos).
_PAIRS = {
    frozenset(p)
    for p in [
        ("ship", "sheep"), ("sit", "seat"), ("live", "leave"), ("bit", "beat"),
        ("fill", "feel"), ("hit", "heat"), ("full", "fool"), ("pull", "pool"),
        ("very", "berry"), ("vote", "boat"), ("van", "ban"), ("vest", "best"),
        ("yes", "jess"), ("year", "ear"), ("walk", "work"), ("hat", "hut"),
        ("cap", "cup"), ("cat", "cut"), ("man", "men"), ("bad", "bed"),
    ]
}
_TH_SWAPS = ("s", "t", "f", "d", "z")


def normalize_spoken(text: str | None) -> str:
    value = normalize_answer(text)
    value = re.sub(r"[^\w\s']", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def sounds_alike(expected: str, said: str) -> bool:
    """True si `said` es un error de pronunciación típico de `expected`."""
    if expected == said:
        return False
    if frozenset((expected, said)) in _PAIRS:
        return True
    if "th" in expected and any(expected.replace("th", s) == said for s in _TH_SWAPS):
        return True
    if "v" in expected and expected.replace("v", "b") == said:
        return True
    return False


def pronunciation_slips(accepted: list[str], transcript: str) -> list[tuple[str, str]] | None:
    """Si la transcripción coincide con una respuesta aceptada salvo pares que suenan
    parecido, devuelve esos pares (dicho, esperado). Si no, None."""
    said = normalize_spoken(transcript).split()
    for answer in accepted:
        expected = normalize_spoken(answer).split()
        if len(expected) != len(said):
            continue
        slips = []
        for e, s in zip(expected, said):
            if e == s:
                continue
            if not sounds_alike(e, s):
                break
            slips.append((s, e))
        else:
            if slips:
                return slips
    return None
