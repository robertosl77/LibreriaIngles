"""Evaluación fonética local con OpenPronounce (T-027).

El audio del alumno se mantiene en memoria durante este request. No se crea un
archivo temporal del audio: ffmpeg recibe los bytes por stdin y devuelve PCM por
stdout. Si OpenPronounce o sus dependencias del sistema no están disponibles,
la evaluación fonética queda en null y nunca se inventa un puntaje.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

PROVIDER = "OPENPRONOUNCE"
TARGET_SR = 16_000
_WORD_RE = re.compile(r"\b[A-Za-z']+\b")


def _clamp_score(value: Any) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(numeric):
        return 0
    return round(max(0.0, min(100.0, numeric)))


def _score_from_error_confidence(value: Any) -> int:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 1.0
    confidence = max(0.0, min(1.0, confidence))
    return _clamp_score((1.0 - confidence) * 100.0)


def _normalize_phone_result(raw: dict, reference_text: str) -> dict | None:
    """Adapta la comparación fonema-a-fonema al contrato estable de T-034."""
    expected_groups = raw.get("expected_phones") or []
    heard = raw.get("heard_phones") or []
    if not any(expected_groups) or not heard:
        return None

    error_rate = raw.get("phone_error_rate")
    try:
        numeric_error_rate = float(error_rate)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_error_rate):
        return None

    errors = raw.get("errors") or []
    error_scores: dict[str, int] = {}
    phonemes: list[dict] = []

    for error in errors:
        word = str(error.get("word") or "").strip()
        if not word:
            continue
        word_score = _score_from_error_confidence(error.get("confidence"))
        key = word.lower()
        error_scores[key] = min(error_scores.get(key, 100), word_score)

        for phone in error.get("phones") or []:
            expected = str(phone.get("expected") or phone.get("heard") or "").strip()
            if not expected:
                continue
            phonemes.append(
                {
                    "phoneme": expected,
                    "word": word,
                    "score": _score_from_error_confidence(phone.get("confidence")),
                }
            )

    words = [
        {"word": word, "score": error_scores.get(word.lower(), 100)}
        for word in _WORD_RE.findall(reference_text)
    ]

    # T-027 mide pronunciación, no corrección de contenido. El score global sale
    # exclusivamente de la tasa de error de fonemas reconocidos por OpenPronounce.
    score = _clamp_score((1.0 - max(0.0, min(1.0, numeric_error_rate))) * 100.0)

    return {
        "score": score,
        "words": words,
        "phonemes": phonemes,
        "fluency": None,
        "provider": PROVIDER,
        "assessedAt": datetime.now(timezone.utc).isoformat(),
    }

def _find_ffmpeg() -> str | None:
    """Prefiere el FFmpeg portable incluido en el root del proyecto."""
    project_ffmpeg = Path(__file__).resolve().parents[2] / "ffmpeg" / "bin" / "ffmpeg.exe"
    if project_ffmpeg.is_file():
        return str(project_ffmpeg)
    return shutil.which("ffmpeg")


def _configure_espeak_portable() -> bool:
    """Configura phonemizer para usar eSpeak NG incluido en el root del proyecto."""
    project_espeak = Path(__file__).resolve().parents[2] / "espeak-ng"
    library = project_espeak / "libespeak-ng.dll"
    data = project_espeak / "espeak-ng-data"

    if not library.is_file() or not data.is_dir():
        return False

    # phonemizer admite ambas rutas explícitas; así no dependemos del PATH ni
    # de una instalación global de Windows.
    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = str(library)
    os.environ["PHONEMIZER_ESPEAK_DATA_PATH"] = str(data)

    # En Windows ayuda también a resolver DLLs auxiliares que vivan junto a
    # libespeak-ng.dll. El handle debe permanecer vivo durante el proceso.
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        global _ESPEAK_DLL_DIRECTORY
        if _ESPEAK_DLL_DIRECTORY is None:
            _ESPEAK_DLL_DIRECTORY = os.add_dll_directory(str(project_espeak))
    return True


_ESPEAK_DLL_DIRECTORY = None


def _decode_in_memory(audio: bytes):
    """Decodifica webm/ogg/wav a mono float32 16 kHz sin escribir audio a disco."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg no está disponible: se esperaba en root/ffmpeg/bin/ffmpeg.exe o en PATH"
        )

    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(TARGET_SR),
            "pipe:1",
        ],
        input=audio,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or "ffmpeg no pudo decodificar el audio")

    import numpy as np

    waveform = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if waveform.size == 0:
        raise RuntimeError("El audio decodificado está vacío")
    return waveform


def assess_pronunciation(*, audio: bytes, mime_type: str, reference_text: str) -> dict | None:
    """Evalúa pronunciación o devuelve None si OpenPronounce no está disponible."""
    del mime_type
    reference_text = reference_text.strip()
    if not audio or not reference_text:
        return None

    _configure_espeak_portable()

    try:
        from openpronounce import compare_phones, recognize_phones
    except ImportError:
        logger.info("OpenPronounce no está instalado; pronunciation_result queda en null.")
        return None

    try:
        waveform = _decode_in_memory(audio)
        recognition = recognize_phones(waveform, lang="en")
        raw = compare_phones(recognition, reference_text, lang="en")
        return _normalize_phone_result(raw, reference_text)
    except Exception as exc:
        logger.warning("OpenPronounce no pudo evaluar la grabación: %s", exc)
        return None
