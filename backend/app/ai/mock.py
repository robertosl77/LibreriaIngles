"""Proveedor simulado para desarrollo y tests (MOCK_AI_ENABLED=true).

- Genera clases a partir de los ejemplos semilla de la currícula.
- Evalúa respuestas con reglas simples.
- Modelos especiales para probar failover: "mock-fail-quota", "mock-fail-down",
  "mock-fail-auth".
"""

import random

from app.ai.models import AIConnectionStatus
from app.ai.providers import ProviderError

_FAILURES = {
    "mock-fail-quota": (AIConnectionStatus.QUOTA_EXCEEDED, "Cuota agotada (simulado)."),
    "mock-fail-down": (AIConnectionStatus.PROVIDER_DOWN, "Proveedor caído (simulado)."),
    "mock-fail-auth": (AIConnectionStatus.INVALID_CREDENTIALS, "Credencial inválida (simulado)."),
}


class MockProvider:
    def __init__(self, model: str = "mock"):
        self.model = model

    def _maybe_fail(self) -> None:
        if self.model in _FAILURES:
            code, message = _FAILURES[self.model]
            raise ProviderError(code, message)

    def health_check(self) -> None:
        self._maybe_fail()

    def complete_json(self, system: str, user: str, task: dict) -> dict:
        self._maybe_fail()
        if task.get("kind") == "generate_class":
            return self._generate(task)
        if task.get("kind") == "evaluate_answer":
            return self._evaluate(task)
        raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Tarea desconocida para el mock.")

    def _generate(self, task: dict) -> dict:
        rng = random.Random()
        exercises = []
        for slot in task["slots"]:
            examples = slot.get("examples") or []
            if not examples:
                continue
            example = dict(rng.choice(examples))
            example["skillKey"] = slot["skillKey"]
            exercises.append(example)
        return {"title": f"Clase {task['level']} · práctica mixta", "exercises": exercises}

    def _evaluate(self, task: dict) -> dict:
        exercise = task["exercise"]
        answer = (task.get("answer") or "").strip()
        concepts = exercise.get("expectedConcepts") or ["task_completion"]

        if exercise.get("type") == "short_writing":
            words = len(answer.split())
            ok = words >= 6
            score = 85 if ok else 40
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
