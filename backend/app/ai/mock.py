"""Proveedor simulado para desarrollo y tests (MOCK_AI_ENABLED=true).

- Genera clases a partir de los ejemplos semilla de la currícula.
- Evalúa respuestas con reglas simples.
- Modelos especiales para probar failover: "mock-fail-quota", "mock-fail-down",
  "mock-fail-auth".
"""

import random
import re

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
        if task.get("kind") == "campaign_assist":
            return self._campaign_assist(task)
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

    def _campaign_assist(self, task: dict) -> dict:
        """Borrador determinístico para probar el asistente de campañas en local."""
        description = str(task.get("description") or "").strip()
        lower = description.lower()
        benefits = task.get("benefits") or []
        wants_benefit = any(
            term in lower
            for term in (
                "beneficio",
                "días gratis",
                "dias gratis",
                "días de plataforma",
                "dias de plataforma",
            )
        )
        benefit_id = benefits[0].get("id") if benefits and wants_benefit else None
        warnings = []

        trigger = "FIRST_LOGIN" if any(
            word in lower for word in ("bienvenida", "primer login", "primera vez", "nuevo usuario")
        ) else "LOGIN"
        rules = [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}]
        if "sin membres" in lower:
            rules.append({"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False})
        elif "con membres" in lower:
            rules.append({"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": True})

        source = None
        if "byok" in lower or "propias" in lower:
            source = "BYOK"
        elif "híbr" in lower or "hibr" in lower:
            source = "HYBRID"
        elif "plataforma" in lower:
            source = "PLATFORM"
        if source:
            rules.append({"field": "SERVICE_SOURCE", "operator": "EQ", "value": source})

        payment_tenure = any(
            phrase in lower
            for phrase in ("servicio pago", "servicio pagado", "membresía paga", "membresia paga")
        )
        if not payment_tenure:
            account_age_days = None
            months_match = re.search(r"(\d+)\s+mes(?:es)?", lower)
            days_since_register_match = re.search(
                r"(\d+)\s+d[ií]as?[^.]{0,45}(?:registro|registrad|en la app|de antig[uü]edad)",
                lower,
            )
            if "año" in lower or "365" in lower:
                account_age_days = 365
            elif months_match:
                account_age_days = int(months_match.group(1)) * 30
            elif days_since_register_match:
                account_age_days = int(days_since_register_match.group(1))
            if account_age_days is not None and any(
                term in lower
                for term in ("antigü", "antigu", "registro", "registrad", "en la app", "desde que creó", "desde que creo")
            ):
                rules.append(
                    {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": account_age_days}
                )

        if "nunca" in lower and ("estudi" in lower or "clase" in lower):
            rules.append({"field": "NEVER_STUDIED", "operator": "EQ", "value": True})
        elif any(word in lower for word in ("inactiv", "sin estudiar", "no estudia", "no practica")):
            days = 60
            for candidate in (365, 180, 120, 90, 60, 30, 14, 7):
                if str(candidate) in lower:
                    days = candidate
                    break
            rules.append({"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "GTE", "value": days})

        if any(word in lower for word in ("vencido", "venció", "vencio", "vencimiento")):
            days = 30
            for candidate in (365, 180, 120, 90, 60, 30, 14, 7):
                if str(candidate) in lower:
                    days = candidate
                    break
            rules.append({"field": "DAYS_SINCE_SERVICE_EXPIRED", "operator": "GTE", "value": days})

        for level in ("A1", "A2", "B1", "B2", "C1", "C2"):
            if level.lower() in lower:
                rules.append({"field": "CURRENT_LEVEL", "operator": "EQ", "value": level})
                break

        window_match = re.search(
            r"(?:últim(?:os|as)?|ultim(?:os|as)?|durante|por|en)\s+(?:los\s+)?(\d+)\s+d[ií]as",
            lower,
        )
        window_days = int(window_match.group(1)) if window_match else None

        classes_match = re.search(r"(\d+(?:[\.,]\d+)?)\s+clases?", lower)
        daily_average = (
            "promedio" in lower
            and any(
                phrase in lower
                for phrase in ("clases diarias", "clase diaria", "por día", "por dia", "al día", "al dia")
            )
        )
        strict_daily = (
            not daily_average
            and any(
                phrase in lower
                for phrase in (
                    "todos los días",
                    "todos los dias",
                    "cada día",
                    "cada dia",
                    "clases diarias",
                    "clase diaria",
                )
            )
        )
        low_bound = any(
            phrase in lower
            for phrase in ("como máximo", "como maximo", "máximo", "maximo", "menos de", "no más de", "no mas de")
        )
        metric_operator = "LTE" if low_bound else "GTE"

        if classes_match:
            raw_count = float(classes_match.group(1).replace(",", "."))
            class_count = int(raw_count) if raw_count.is_integer() else raw_count
            if daily_average:
                metric_window = window_days or 30
                rules.append(
                    {
                        "field": "AVERAGE_CLASSES_PER_DAY",
                        "operator": metric_operator,
                        "value": class_count,
                        "windowDays": metric_window,
                    }
                )
                if window_days is None:
                    warnings.append(
                        "No se indicó el período del promedio diario; "
                        "se propusieron 30 días como ventana editable."
                    )
            elif strict_daily:
                metric_window = window_days or 30
                rules.append(
                    {
                        "field": "MIN_CLASSES_PER_ACTIVE_DAY",
                        "operator": metric_operator,
                        "value": class_count,
                        "windowDays": metric_window,
                    }
                )
                if metric_operator == "GTE":
                    rules.append(
                        {
                            "field": "ACTIVE_STUDY_DAYS",
                            "operator": "GTE",
                            "value": metric_window,
                            "windowDays": metric_window,
                        }
                    )
                if window_days is None:
                    warnings.append(
                        "No se indicó durante cuántos días sostener la frecuencia diaria; "
                        "se propusieron 30 días como ventana editable."
                    )
            elif window_days is not None:
                rules.append(
                    {
                        "field": "CLASSES_COMPLETED",
                        "operator": metric_operator,
                        "value": class_count,
                        "windowDays": window_days,
                    }
                )

        active_days_match = re.search(r"(\d+)\s+d[ií]as?\s+(?:activos?|con actividad)", lower)
        if active_days_match:
            active_days = int(active_days_match.group(1))
            metric_window = window_days or max(active_days, 30)
            rules.append(
                {
                    "field": "ACTIVE_STUDY_DAYS",
                    "operator": "GTE",
                    "value": active_days,
                    "windowDays": metric_window,
                }
            )

        streak_match = re.search(r"racha(?:\s+de)?\s+(\d+)\s+d[ií]as", lower)
        if streak_match:
            rules.append(
                {
                    "field": "STUDY_STREAK_DAYS",
                    "operator": "GTE",
                    "value": int(streak_match.group(1)),
                }
            )
        if any(term in lower for term in ("reclamo", "queja", "ticket de soporte")):
            warnings.append(
                "El motor actual no tiene datos de reclamos o soporte para segmentar esta campaña."
            )
            benefit_id = None
        if any(term in lower for term in ("referid", "invitó a", "invito a", "invitaron a", "invitar a", "recomendó a", "recomendo a")):
            warnings.append(
                "El motor actual no registra referidos o invitaciones exitosas como métrica de campaña."
            )
            benefit_id = None

        if "%" in description or "descuento" in lower or "bonific" in lower:
            warnings.append(
                "El motor actual de campañas no configura descuentos o precios; "
                "solo puede otorgar un beneficio existente."
            )
        if payment_tenure:
            warnings.append(
                "El motor actual no tiene una condición por antigüedad de una suscripción paga."
            )

        notification = "EMAIL" if "email" in lower or "correo" in lower else "IN_APP"
        requirements = [
            {
                "text": f"Condición {rule['field']}",
                "kind": "RULE",
                "status": "REPRESENTED",
                "capability": rule["field"],
            }
            for rule in rules
        ]
        requirements.append(
            {
                "text": f"Disparador {trigger}",
                "kind": "TRIGGER",
                "status": "REPRESENTED",
                "capability": trigger,
            }
        )
        if wants_benefit:
            requirements.append(
                {
                    "text": "Otorgar un beneficio existente",
                    "kind": "BENEFIT",
                    "status": "REPRESENTED" if benefit_id is not None else "UNSUPPORTED",
                    "capability": "BENEFIT" if benefit_id is not None else None,
                }
            )
            requirements.append(
                {
                    "text": "Otorgar beneficio",
                    "kind": "ACTION",
                    "status": "REPRESENTED",
                    "capability": "GRANT_BENEFIT",
                }
            )
        if notification == "EMAIL":
            requirements.append(
                {
                    "text": "Enviar por email",
                    "kind": "DELIVERY",
                    "status": "REPRESENTED",
                    "capability": "EMAIL",
                }
            )
        if any(term in lower for term in ("reclamo", "queja", "ticket de soporte")):
            requirements.append(
                {
                    "text": "Segmentar por reclamo o soporte",
                    "kind": "RULE",
                    "status": "UNSUPPORTED",
                    "capability": None,
                }
            )
        if any(term in lower for term in ("referid", "invitó a", "invito a", "invitaron a", "invitar a", "recomendó a", "recomendo a")):
            requirements.append(
                {
                    "text": "Segmentar por referido o invitación exitosa",
                    "kind": "RULE",
                    "status": "UNSUPPORTED",
                    "capability": None,
                }
            )
        if "%" in description or "descuento" in lower or "bonific" in lower:
            requirements.append(
                {
                    "text": "Aplicar descuento o precio promocional",
                    "kind": "ACTION",
                    "status": "UNSUPPORTED",
                    "capability": None,
                }
            )
        if payment_tenure:
            requirements.append(
                {
                    "text": "Segmentar por antigüedad de pago o suscripción",
                    "kind": "RULE",
                    "status": "UNSUPPORTED",
                    "capability": None,
                }
            )

        return {
            "draft": {
                "name": "Campaña sugerida por IA",
                "benefitId": benefit_id,
                "action": "GRANT_BENEFIT",
                "actionConfig": {},
                "trigger": trigger,
                "rules": rules,
                "priority": 100,
                "stackable": False,
                "maxRecipients": None,
                "startsAt": None,
                "endsAt": None,
                "notification": notification,
                "message": description[:500] if description else None,
            },
            "requirements": requirements,
            "warnings": warnings,
            "summary": "Borrador generado con las capacidades actuales del motor de campañas.",
        }

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
