"""Proveedor simulado para desarrollo y tests (MOCK_AI_ENABLED=true).

- Genera clases a partir de los ejemplos semilla de la currícula.
- Evalúa respuestas con reglas simples.
- Modelos especiales para probar failover: "mock-fail-quota", "mock-fail-down",
  "mock-fail-auth".
"""

import random

from app.ai.models import AIConnectionStatus
from app.ai.providers import ModelInfo, ProviderError

_FAILURES = {
    "mock-fail-quota": (AIConnectionStatus.QUOTA_EXCEEDED, "Cuota agotada (simulado)."),
    "mock-fail-down": (AIConnectionStatus.PROVIDER_DOWN, "Proveedor caído (simulado)."),
    "mock-fail-auth": (AIConnectionStatus.INVALID_CREDENTIALS, "Credencial inválida (simulado)."),
}


def _listen_version(example: dict) -> dict:
    """Adapta un ejemplo escrito a presentación LISTEN (solo para el simulado)."""
    question = example.get("question", "")
    answers = example.get("acceptedAnswers") or []
    kind = example.get("type")
    if kind == "fill_blank" and answers:
        return {"stimulus": question.replace("___", answers[0], 1).split(" (")[0]}
    if kind in ("multiple_choice", "reading_multiple_choice"):
        if example.get("passage"):
            return {"stimulus": example["passage"], "passage": None}
        if answers and "___" in question:
            return {"stimulus": question.replace("___", answers[0], 1)}
        return {"stimulus": question, "question": "Choose the correct option for what you hear."}
    if kind == "conversation":
        return {"stimulus": question, "question": "Listen and reply naturally."}
    # rewrite / short_writing: se escucha la oración o la pregunta y no se muestra escrita.
    return {"stimulus": question, "question": "Listen and do the task with what you hear."}


class MockProvider:
    def __init__(self, model: str = "mock"):
        self.model = model

    def _maybe_fail(self) -> None:
        if self.model in _FAILURES:
            code, message = _FAILURES[self.model]
            raise ProviderError(code, message)

    def health_check(self) -> None:
        self._maybe_fail()

    def list_models(self) -> list[ModelInfo]:
        self._maybe_fail()
        return [ModelInfo("mock", "Simulado")] + [
            ModelInfo(name, f"Simulado · {message.split(' (')[0].lower()}")
            for name, (_, message) in _FAILURES.items()
        ]

    def complete_json(self, system: str, user: str, task: dict) -> dict:
        self._maybe_fail()
        if task.get("kind") == "generate_class":
            return self._generate(task)
        if task.get("kind") == "evaluate_answer":
            return self._evaluate(task)
        raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Tarea desconocida para el mock.")

    def transcribe_audio(self, audio: bytes, mime_type: str) -> str:
        """Para tests, bytes UTF-8 representan la transcripción simulada."""
        self._maybe_fail()
        try:
            text = audio.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = ""
        return text or "This is a simulated spoken answer."

    def analyze_speech(self, audio: bytes, mime_type: str):
        """Transcripción simulada + pronunciación determinística (para tests y desarrollo)."""
        from app.ai.providers import SpeechAnalysis

        text = self.transcribe_audio(audio, mime_type)
        words = [w.strip(".,!?") for w in text.split() if w.strip(".,!?")]
        return SpeechAnalysis(
            text,
            {
                "score": 80,
                "words": [{"word": w, "score": 60 if i == 0 else 85} for i, w in enumerate(words)],
                "phonemes": [],
                "fluency": 75,
            },
        )

    def _generate(self, task: dict) -> dict:
        rng = random.Random()
        exercises = []
        for slot in task["slots"]:
            examples = slot.get("examples") or []
            if not examples:
                continue
            example = dict(rng.choice(examples))
            example["skillKey"] = slot["skillKey"]
            if slot.get("presentation") == "LISTEN" and not example.get("stimulus"):
                example.update(_listen_version(example))
            exercises.append(example)
        return {"title": f"Clase {task['level']} · práctica mixta", "exercises": exercises}

    def _evaluate(self, task: dict) -> dict:
        exercise = task["exercise"]
        answer = (task.get("answer") or "").strip()
        concepts = exercise.get("expectedConcepts") or ["task_completion"]

        if exercise.get("type") == "conversation":
            ok = bool(answer) and answer.lower() not in {"zzz", "xx", "no sé"}
            score = 100 if ok else 0
            return {
                "result": "correct" if ok else "incorrect",
                "scoreSuggested": score,
                "conceptResults": [
                    {"concept": c, "status": "correct" if ok else "incorrect", "score": score}
                    for c in concepts
                ],
                "errors": [],
                "correctAnswer": None,
                "feedback": "La respuesta mantiene el intercambio." if ok else "La respuesta no continúa la conversación.",
                "suggestions": [],
                "secondarySkillResults": [],
            }

        if exercise.get("type") == "short_writing":
            words = len(answer.split())
            ok = words >= 6
            # Puntaje fino por concepto (T-043): una respuesta bien hecha vale 100.
            score = 100 if ok else 40
            return {
                "result": "correct" if ok else "partially_correct",
                "scoreSuggested": score,
                "conceptResults": [
                    {"concept": c, "status": "correct" if ok else "partially_correct", "score": score}
                    for c in concepts
                ],
                "errors": [] if ok else [
                    {"type": "GRAMMAR_ERROR", "fragment": answer[:40], "correction": "", "explanation": "Escribí al menos dos oraciones completas."}
                ],
                "correctAnswer": None,
                "feedback": "Buen trabajo." if ok else "La respuesta es muy corta para la consigna.",
                "suggestions": [
                    {"type": "NATURALNESS_SUGGESTION", "text": "Podés conectar ideas con 'and', 'but' o 'because'."}
                ],
            }

        accepted = [a.lower() for a in exercise.get("acceptedAnswers") or []]
        ok = answer.lower() in accepted
        return {
            "result": "correct" if ok else "incorrect",
            "scoreSuggested": 100 if ok else 0,
            "conceptResults": [
                {"concept": c, "status": "correct" if ok else "incorrect", "score": 100 if ok else 0}
                for c in concepts
            ],
            "errors": [],
            "correctAnswer": (exercise.get("acceptedAnswers") or [None])[0],
            "feedback": "Correcto." if ok else "No es correcto.",
            "suggestions": [],
        }
