"""Simula poco cupo de IA para probar T-191 sin esperar a que el proveedor rechace (solo local/dev).

Uso (desde la carpeta backend, con el venv activo):

    python scripts/simular_cupo.py clase   --email vos@mail.com   # la próxima clase sale reducida
    python scripts/simular_cupo.py examen  --email vos@mail.com   # sin pedidos: el examen no se crea
    python scripts/simular_cupo.py limpiar --email vos@mail.com   # borra lo simulado

Escribe límites "aprendidos" con source=SIMULATED en las conexiones habilitadas de la cuenta.
`limpiar` borra solo esas filas; los límites reales aprendidos no se tocan.
"""

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.accounts.models import Account  # noqa: E402
from app.ai import limits as quota  # noqa: E402
from app.ai.models import AIQuotaLimit  # noqa: E402
from app.ai.service import candidate_connections  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402

SIMULATED = "SIMULATED"


def _upsert(db, connection, model, dimension, limit_value):
    row = db.scalar(
        select(AIQuotaLimit).where(
            AIQuotaLimit.connection_id == connection.id,
            AIQuotaLimit.model == model,
            AIQuotaLimit.dimension == dimension,
            AIQuotaLimit.window == "DAY",
        )
    )
    if row is None:
        row = AIQuotaLimit(connection_id=connection.id, model=model, dimension=dimension, window="DAY")
        db.add(row)
    row.kind = quota.RENEWABLE
    row.limit_value = limit_value
    row.remaining = None
    row.reset_at = None
    row.source = SIMULATED
    row.tier = "simulated"
    row.observed_at = quota.utcnow()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("modo", choices=["clase", "examen", "limpiar"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    if not settings.dev_account_purge_allowed:
        print("Solo se puede usar en local/dev.")
        return 1

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == args.email.strip().lower()))
        if account is None:
            print(f"No existe la cuenta {args.email}.")
            return 1
        connections = candidate_connections(db, account, include_backoff=True)
        if not connections:
            print("La cuenta no tiene conexiones de IA habilitadas.")
            return 1

        for connection in connections:
            model = quota.connection_model(connection)
            label = f"{connection.provider} · {model} (conexión {connection.id})"
            if args.modo == "limpiar":
                db.execute(
                    delete(AIQuotaLimit).where(
                        AIQuotaLimit.connection_id == connection.id, AIQuotaLimit.source == SIMULATED
                    )
                )
                print(f"{label}: simulación borrada.")
                continue

            rules = quota.provider_rules(db, connection.provider)
            since = quota._day_reset(rules, quota.utcnow()) - quota.timedelta(days=1)
            if args.modo == "examen":
                used = quota._used(db, connection, model, "REQUESTS", since)
                _upsert(db, connection, model, "REQUESTS", used)  # 0 pedidos libres
                print(f"{label}: tope de pedidos del día = {used} (ya usados). No queda ninguno.")
            else:
                per_item = quota.estimate(db, connection.provider, model, "generate_class", items=1).output_tokens
                used = quota._used(db, connection, model, "OUTPUT_TOKENS", since)
                room = per_item * (settings.ai_class_min_exercises + 1)  # entra una clase mínima, no una completa
                limit_value = math.ceil((used + room) / settings.ai_quota_margin) + 1
                _upsert(db, connection, model, "OUTPUT_TOKENS", limit_value)
                print(f"{label}: tope de tokens de salida del día = {limit_value} "
                      f"(usados {used}, quedan ~{room} ≈ {settings.ai_class_min_exercises + 1} ejercicios).")
        db.commit()
    if args.modo != "limpiar":
        print("\nATENCIÓN: la simulación queda activa hasta las 04:00 o hasta correr "
              f"'python scripts/simular_cupo.py limpiar --email {args.email}'. "
              "Si son conexiones de plataforma, afecta a todos los alumnos que las usan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
