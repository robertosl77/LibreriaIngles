"""T-220 (E-11) · Tareas periódicas del core de clases.

Las correcciones que quedaron pendientes (sin IA disponible al enviar) las reintenta esta tarea.
Antes dependían de que el alumno abriera Inicio y el navegador llamara a /process-pending.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountStatus
from app.classes.service import evaluate_pending
from app.jobs.registry import periodic_job
from app.learning.models import ClassSession, ClassSessionStatus

logger = logging.getLogger(__name__)

BATCH = 20


@periodic_job(
    "classes.process_pending_evaluations",
    every_seconds=120,
    description="Reintenta las correcciones pendientes de todas las cuentas.",
)
def process_pending_evaluations(db: Session) -> int:
    sessions = db.scalars(
        select(ClassSession)
        .where(ClassSession.status == ClassSessionStatus.AWAITING_EVALUATION)
        .order_by(ClassSession.submitted_at.asc().nulls_last(), ClassSession.id.asc())
        .limit(BATCH)
    ).all()
    completed = 0
    for session in sessions:
        account = db.get(Account, session.account_id) if session.account_id else None
        if account is None or account.status != AccountStatus.ACTIVE:
            continue
        try:
            if evaluate_pending(db, account, session):
                completed += 1
        except Exception:
            db.rollback()
            logger.exception("Falló la corrección pendiente de class_session_id=%s", session.id)
    return completed
