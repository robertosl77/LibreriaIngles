"""Exporta los intentos de escritura libre para revisar la corrección (T-043).

Uso (desde la carpeta backend, con el venv activo):

    python scripts/export_writing.py                 # todos los perfiles
    python scripts/export_writing.py --email vos@mail.com

Genera `writing_attempts.json` en la carpeta actual. Incluye solo lo necesario para el
diagnóstico: consigna, respuesta, puntaje y la corrección de la IA. No incluye API keys
ni datos de la cuenta (salvo que se filtre por email, que no se escribe en el archivo).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.accounts.models import Account  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.learning.models import Attempt, ClassSession, Exercise  # noqa: E402

TYPES = ("short_writing", "rewrite")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", help="solo los intentos de esta cuenta")
    parser.add_argument("--out", default="writing_attempts.json")
    args = parser.parse_args()

    with SessionLocal() as db:
        query = (
            select(Attempt, Exercise, ClassSession)
            .join(Exercise, Exercise.id == Attempt.exercise_id)
            .join(ClassSession, ClassSession.id == Exercise.class_session_id)
            .where(Exercise.exercise_type.in_(TYPES), Attempt.score.is_not(None))
            .order_by(Attempt.evaluated_at)
        )
        if args.email:
            account = db.scalar(select(Account).where(Account.email == args.email))
            if account is None:
                sys.exit(f"No existe la cuenta {args.email}")
            query = query.where(Attempt.account_id == account.id)

        rows = []
        for attempt, exercise, session in db.execute(query).all():
            result = attempt.evaluation_result or {}
            rows.append(
                {
                    "attemptId": attempt.id,
                    "date": attempt.evaluated_at.isoformat() if attempt.evaluated_at else None,
                    "kind": session.kind.value,
                    "level": exercise.level,
                    "skill": exercise.skill_key,
                    "type": exercise.exercise_type,
                    "response": attempt.response_mode.value if attempt.response_mode else None,
                    "instruction": exercise.instruction,
                    "question": exercise.prompt,
                    "acceptedAnswers": (exercise.answer_key or {}).get("acceptedAnswers") or [],
                    "expectedConcepts": exercise.expected_concepts or [],
                    "answer": attempt.raw_answer,
                    "assistance": attempt.assistance.value if attempt.assistance else None,
                    "source": attempt.evaluation_source.value if attempt.evaluation_source else None,
                    "score": attempt.score,
                    "result": result.get("result"),
                    "conceptResults": result.get("conceptResults") or [],
                    "errors": result.get("errors") or [],
                    "suggestions": result.get("suggestions") or [],
                    "feedback": result.get("feedback"),
                    "correctAnswer": result.get("correctAnswer"),
                    "appeal": result.get("appeal"),
                }
            )

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    writing = sum(1 for r in rows if r["type"] == "short_writing")
    print(f"{len(rows)} intentos exportados ({writing} de escritura libre) → {args.out}")


if __name__ == "__main__":
    main()
