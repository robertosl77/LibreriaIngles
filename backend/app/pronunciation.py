"""Pronunciación estimada por IA (T-027).

La misma conexión de IA que transcribe la respuesta hablada devuelve, en la misma
llamada, una estimación de pronunciación. Acá se valida y se adapta al contrato
estable que consume T-034:

    {score, words[{word, score}], phonemes[{phoneme, word, score}], fluency,
     provider, estimated, assessedAt}

Se evalúa lo que el alumno DIJO (la transcripción), no la respuesta esperada:
contenido y pronunciación no se mezclan. Si el proveedor no ofrece la estimación o
viene inválida, el resultado es None: nunca se inventa un puntaje y nunca hace
fallar la respuesta.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

MAX_WORDS = 80
MAX_PHONEMES = 30


def _score(value: Any) -> int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return round(max(0.0, min(100.0, numeric)))


def normalize_ai_pronunciation(raw: Any, transcript: str, provider: str) -> dict | None:
    if not isinstance(raw, dict) or not transcript.strip():
        return None
    score = _score(raw.get("score"))
    if score is None:
        return None

    words = []
    for item in (raw.get("words") or [])[:MAX_WORDS]:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        word_score = _score(item.get("score"))
        if word and word_score is not None:
            words.append({"word": word, "score": word_score})

    phonemes = []
    for item in (raw.get("phonemes") or [])[:MAX_PHONEMES]:
        if not isinstance(item, dict):
            continue
        phoneme = str(item.get("phoneme") or "").strip()
        phoneme_score = _score(item.get("score"))
        if phoneme and phoneme_score is not None:
            phonemes.append(
                {"phoneme": phoneme, "word": str(item.get("word") or "").strip(), "score": phoneme_score}
            )

    return {
        "score": score,
        "words": words,
        "phonemes": phonemes,
        "fluency": _score(raw.get("fluency")),
        "provider": provider,
        "estimated": True,
        "assessedAt": datetime.now(timezone.utc).isoformat(),
    }
