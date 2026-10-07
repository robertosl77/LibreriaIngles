"""Lista TODAS las conexiones de IA de la base (de cualquier dueño) y cuáles usa una cuenta.

Uso (desde la carpeta backend, con el venv activo):

    python scripts/ver_conexiones.py
    python scripts/ver_conexiones.py --email vos@mail.com   # además: cuáles usa esa cuenta y por qué

No muestra API keys: solo los últimos caracteres (los mismos que muestra la pantalla IA).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.accounts.models import Account  # noqa: E402
from app.ai.models import AIConnection, AIUsageEvent  # noqa: E402
from app.ai.service import ai_sources, candidate_connections  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email")
    args = parser.parse_args()

    with SessionLocal() as db:
        emails = dict(db.execute(select(Account.id, Account.email)).all())
        uses = dict(
            db.execute(select(AIUsageEvent.connection_id, func.count(AIUsageEvent.id)).group_by(AIUsageEvent.connection_id)).all()
        )
        print(f"{'id':>3}  {'dueño':<32} {'nombre':<26} {'modelo':<24} {'activa':<6} {'estado':<15} {'key':<6} {'usos':>5}  creada")
        for c in db.scalars(select(AIConnection).order_by(AIConnection.id)).all():
            owner_type = getattr(c.owner_type, "value", c.owner_type)
            owner = "PLATAFORMA (portal)" if owner_type == "PLATFORM" else f"{owner_type} {emails.get(c.owner_id, c.owner_id)}"
            status = getattr(c.status, "value", c.status)
            print(f"{c.id:>3}  {owner:<32} {c.name[:26]:<26} {(c.model or '(por defecto)')[:24]:<24} "
                  f"{'sí' if c.active else 'NO':<6} {str(status):<15} {(c.credential_hint or '')[-4:]:<6} "
                  f"{uses.get(c.id, 0):>5}  {c.created_at:%d/%m/%Y %H:%M}")

        if args.email:
            account = db.scalar(select(Account).where(Account.email == args.email.strip().lower()))
            if account is None:
                print(f"\nNo existe la cuenta {args.email}.")
                return 1
            own, platform = ai_sources(db, account)
            print(f"\n{account.email}: usa propias={own}, usa plataforma={platform}")
            for c in candidate_connections(db, account, include_backoff=True):
                print(f"  → usa conexión {c.id} · {c.name} · {c.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
