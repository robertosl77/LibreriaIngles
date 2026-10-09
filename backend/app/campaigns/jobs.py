"""T-220 (E-02) · Tareas periódicas de campañas.

Antes `GET /me` reconciliaba las campañas FIRST_LOGIN que el login no llegó a aplicar. Ahora lo
hace esta tarea para las cuentas que ingresaron por primera vez en las últimas 48 h.
"""

import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountStatus, PlatformRole
from app.campaigns.service import reconcile_first_login_campaigns, utcnow
from app.jobs.registry import periodic_job

logger = logging.getLogger(__name__)

RECONCILE_WINDOW = timedelta(hours=48)


@periodic_job(
    "campaigns.reconcile_first_login",
    every_seconds=300,
    description="Aplica campañas de primer ingreso que el login no alcanzó a aplicar.",
)
def reconcile_recent_first_logins(db: Session) -> int:
    since = utcnow() - RECONCILE_WINDOW
    accounts = db.scalars(
        select(Account).where(
            Account.first_login_at.is_not(None),
            Account.first_login_at >= since,
            Account.status == AccountStatus.ACTIVE,
            or_(
                Account.platform_role.is_(None),
                Account.platform_role != PlatformRole.PLATFORM_OWNER,
            ),
        )
    ).all()
    granted = 0
    for account in accounts:
        try:
            with db.begin_nested():
                granted += len(reconcile_first_login_campaigns(db, account))
        except Exception:
            logger.exception("Falló la reconciliación FIRST_LOGIN para account_id=%s", account.id)
    return granted
