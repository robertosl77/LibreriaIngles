"""Evidencias por habilidad (T-034): un ejercicio genera varias evidencias.

Cada ejercicio tiene un foco principal (su área: Grammar, Vocabulary, Reading,
Writing, Listening) y puede dejar señales en otras habilidades, cada una medida
a su manera (no se copia el mismo puntaje):

- LISTEN: Listening = resultado ponderado por el esfuerzo para entender
  (escuchas extra y uso de "lento").
- SPEAK: Speaking = resultado del contenido; Pronunciation = estimación final
  (y un error de pronunciación tipo think/sink la limita).
- Writing se mide solo con ejercicios del área Writing (el alumno arma la oración).
  Reescribir una oración que ya se da (rewrite de gramática) es Grammar, no Writing:
  contarlo inflaba Writing con aciertos fáciles.
- Pedir lección (ayuda) reduce el peso de la evidencia y la marca como asistida:
  es señal de debilidad aunque la respuesta sea correcta.
- Asistencia continua: escuchar muchas veces o en lento marca Listening como
  asistido (además de bajar su puntaje); practicar la pronunciación más de
  PRACTICE_FREE_TRIALS veces marca Pronunciation como asistida y pesa menos
  (practicar no castiga el puntaje). Regrabar la respuesta hablada más de una vez marca
  Speaking como asistido, sin bajar la nota (T-046 v2).

Los parámetros están juntos para poder configurarlos más adelante (T-036).
"""

from dataclasses import dataclass

from app.learning.models import Assistance

# Orden de presentación en el dashboard.
ABILITIES: list[tuple[str, str]] = [
    ("GRAMMAR", "Grammar"),
    ("VOCABULARY", "Vocabulary"),
    ("LISTENING", "Listening"),
    ("SPEAKING", "Speaking"),
    ("PRONUNCIATION", "Pronunciation"),
    ("READING", "Reading"),
    ("WRITING", "Writing"),
]
AREA_TO_ABILITY = {
    "grammar": "GRAMMAR",
    "vocabulary": "VOCABULARY",
    "listening": "LISTENING",
    "reading": "READING",
    "writing": "WRITING",
}

ASSISTED_WEIGHT = 0.5  # respuesta con lección o pista
EXTRA_PLAY_PENALTY = 0.15  # Listening: cada escucha extra
SLOW_PENALTY = 0.20  # Listening: usó modo lento
LISTEN_FLOOR = 0.40  # Listening: aunque costó, entendió
PRONUNCIATION_SLIP_CAP = 50  # palabra dicha como otra parecida (think → sink)
LISTEN_FREE_PLAYS = 2  # más escuchas que esto (o usar lento) = asistencia continua
PRACTICE_FREE_TRIALS = 2  # más prácticas que esto = asistencia continua
SPEAK_FREE_RETAKES = 1  # regrabar más que esto = asistencia continua (T-046 v2)


@dataclass(frozen=True)
class Evidence:
    ability: str
    score: float
    weight: float
    assisted: bool = False


def listening_factor(signals: dict | None) -> float:
    """1.0 con una sola escucha normal; baja con escuchas extra y con modo lento."""
    signals = signals or {}
    plays = int(signals.get("listenPlays") or 0)
    slow = int(signals.get("listenSlowPlays") or 0)
    if plays <= 0:
        return 1.0  # sin datos (respuestas anteriores a T-034): no se penaliza
    factor = 1.0 - EXTRA_PLAY_PENALTY * max(0, plays - 1) - (SLOW_PENALTY if slow else 0.0)
    return round(max(LISTEN_FLOOR, factor), 2)


def _has_pronunciation_slip(evaluation_result: dict | None) -> bool:
    errors = (evaluation_result or {}).get("errors") or []
    return any(isinstance(e, dict) and e.get("type") == "PRONUNCIATION_ERROR" for e in errors)


def attempt_evidence(attempt, exercise) -> list[Evidence]:
    """Evidencias que deja un intento corregido, una por habilidad (sin duplicar)."""
    if attempt.score is None:
        return []
    score = float(attempt.score)
    assisted = (attempt.assistance or Assistance.NONE) != Assistance.NONE
    weight = ASSISTED_WEIGHT if assisted else 1.0
    signals = attempt.signals or {}
    listened = bool(exercise.presentation_mode and exercise.presentation_mode.value == "LISTEN")
    spoken = bool(attempt.response_mode and attempt.response_mode.value == "SPEAK")
    area = AREA_TO_ABILITY.get(exercise.area or "")

    evidence: dict[str, Evidence] = {}

    if listened:
        replays = int(signals.get("listenPlays") or 0) > LISTEN_FREE_PLAYS
        slow = int(signals.get("listenSlowPlays") or 0) > 0
        evidence["LISTENING"] = Evidence(
            "LISTENING",
            round(score * listening_factor(signals), 1),
            weight,
            assisted or replays or slow,
        )

    # Foco principal (área). Lo escuchado no es lectura; lo hablado no es escritura.
    if area and area not in evidence:
        skip = (area == "READING" and listened) or (area == "WRITING" and spoken)
        if not skip:
            evidence[area] = Evidence(area, score, weight, assisted)

    # T-183: el dictado se escucha Y se escribe entero: también es evidencia de Writing.
    if exercise.exercise_type == "dictation" and not spoken and "WRITING" not in evidence:
        evidence["WRITING"] = Evidence("WRITING", score, weight, assisted)

    if spoken:
        # Regrabar mucho = le costó decirlo: se marca, pero no baja la nota (T-046 v2).
        retakes = int(signals.get("speakRetakes") or 0)
        evidence["SPEAKING"] = Evidence(
            "SPEAKING", score, weight, assisted or retakes > SPEAK_FREE_RETAKES
        )
        pronunciation = (attempt.pronunciation_result or {}).get("score")
        if _has_pronunciation_slip(attempt.evaluation_result):
            pronunciation = min(
                PRONUNCIATION_SLIP_CAP,
                pronunciation if pronunciation is not None else PRONUNCIATION_SLIP_CAP,
            )
        if pronunciation is not None:
            practiced = len(signals.get("practiceScores") or []) > PRACTICE_FREE_TRIALS
            evidence["PRONUNCIATION"] = Evidence(
                "PRONUNCIATION",
                float(pronunciation),
                weight * (ASSISTED_WEIGHT if practiced else 1.0),
                assisted or practiced,
            )

    return list(evidence.values())
