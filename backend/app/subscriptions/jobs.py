"""T-220 (E-02) · Tareas periódicas de suscripciones."""

from sqlalchemy.orm import Session

from app.jobs.registry import periodic_job
from app.subscriptions.service import expire_due_subscriptions


@periodic_job(
    "subscriptions.expire",
    every_seconds=300,
    description="Marca como vencidas las suscripciones cuya vigencia terminó.",
)
def expire_subscriptions(db: Session) -> int:
    return expire_due_subscriptions(db)
