"""Errores de ortografía menores (T-021), resueltos sin IA.

"taxy driver" por "taxi driver" no es un error de concepto: el alumno sabe el oficio y
lo escribió mal. Se marca SPELLING_ERROR y vale parcial (SPELLING_SCORE), nunca 0 %.

Para no perdonar errores reales, una palabra cuenta como error de tipeo solo si:
- la esperada tiene 4 letras o más (in/on/at, do/is/are… nunca se perdonan);
- la diferencia no está en una terminación que se enseña como gramática (-s/-es/-ies,
  -ed, -ing): "watchs" por "watches" es un error de la regla de tercera persona;
- la diferencia es mínima: 1 cambio (2 en palabras de 8+ letras); una transposición
  ("freind") cuenta como 1;
- lo escrito NO es otra palabra que la app conoce ("sleep" por "sheep" es otra palabra,
  no un tipeo). El diccionario sale del propio currículo y las lecciones.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.classes.normalize import normalize_answer

SPELLING_SCORE = 80.0  # concepto bien, ortografía con error: parcial
MIN_WORD_LENGTH = 4
# Terminaciones que son gramática (tercera persona, pasado, gerundio), no ortografía.
GRAMMAR_ENDINGS = ("ies", "ied", "ing", "es", "ed", "s")
MAX_SLIPS = 2

DATA_DIR = Path(__file__).resolve().parent.parent / "curriculum" / "data"
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


# Campos que guardan formas EQUIVOCADAS a propósito: no son palabras válidas.
_WRONG_FIELDS = {"wrong", "commonErrors"}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, v in value.items():
            if key not in _WRONG_FIELDS:
                yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


@lru_cache
def known_words() -> frozenset[str]:
    """Palabras en inglés que aparecen en el currículo y las lecciones."""
    words: set[str] = set()
    for path in DATA_DIR.rglob("*.json"):
        for text in _strings(json.loads(path.read_text(encoding="utf-8"))):
            words.update(_WORD.findall(text.lower()))
    return frozenset(words)


def edit_distance(a: str, b: str) -> int:
    """Distancia de Damerau-Levenshtein (versión OSA): una transposición cuenta 1."""
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def _ending_mistake(expected: str, typed: str) -> bool:
    """La diferencia está en una terminación gramatical (watches → watchs, studied → studyed)."""
    for ending in GRAMMAR_ENDINGS:
        if expected.endswith(ending) or typed.endswith(ending):
            stem = len(expected) - len(ending) - 1
            if stem > 0 and expected[:stem] == typed[:stem]:
                return True
    return False


def is_minor_typo(expected: str, typed: str) -> bool:
    if expected == typed or len(expected) < MIN_WORD_LENGTH:
        return False
    if typed in known_words():
        return False  # es otra palabra, no un error de tipeo
    if _ending_mistake(expected, typed):
        return False
    allowed = 2 if len(expected) >= 8 else 1
    return edit_distance(expected, typed) <= allowed


_CASED_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")


def _words(text: str) -> list[str]:
    """Palabras con su forma original (para mostrarlas), en el mismo orden que se comparan."""
    return _CASED_WORD.findall(text or "")


def spelling_slips(accepted: list[str], answer: str) -> list[tuple[str, str]] | None:
    """Si la respuesta coincide con una aceptada salvo errores de tipeo menores, devuelve
    los pares (escrito, correcto) tal como se escribieron. Si no, None."""
    typed = _words(answer)
    for option in accepted:
        expected = _words(option)
        if len(expected) != len(typed):
            continue
        slips = []
        for e, t in zip(expected, typed):
            el, tl = normalize_answer(e), normalize_answer(t)
            if el == tl:
                continue
            if not is_minor_typo(el, tl):
                break
            slips.append((t, e))
        else:
            if 0 < len(slips) <= MAX_SLIPS:
                return slips
    return None
