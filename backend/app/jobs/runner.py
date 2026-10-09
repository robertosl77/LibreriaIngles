"""T-220 · Ejecuta las tareas vencidas, cada una bajo su lease."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.jobs.models import JobLease, utcnow
from app.jobs.registry import PeriodicJob, registered_jobs

logger = logging.getLogger(__name__)


@dataclass
class JobOutcome:
    name: str
    ran: bool
    ok: bool | None = None
    processed: int | None = None
    error: str | None = None


def _acquire(job: PeriodicJob, now: datetime) -> bool:
    """Toma el lease si está libre. Con varias réplicas, solo una gana por ciclo."""
    until = now + timedelta(seconds=job.every_seconds)
    with SessionLocal() as db:
        if db.get(JobLease, job.name) is None:
            db.add(JobLease(name=job.name))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        result = db.execute(
            update(JobLease)
            .where(
                JobLease.name == job.name,
                or_(JobLease.locked_until.is_(None), JobLease.locked_until <= now),
            )
            .values(locked_until=until, last_started_at=now)
        )
        db.commit()
        return result.rowcount == 1


def _finish(job: PeriodicJob, *, ok: bool, processed: int | None, error: str | None) -> None:
    with SessionLocal() as db:
        lease = db.get(JobLease, job.name)
        if lease is None:
            return
        lease.last_finished_at = utcnow()
        lease.last_ok = ok
        lease.last_processed = processed
        lease.last_error = (error or "")[:500] or None
        db.commit()


def run_job(job: PeriodicJob, *, now: datetime | None = None, force: bool = False) -> JobOutcome:
    now = now or utcnow()
    if not force and not _acquire(job, now):
        return JobOutcome(job.name, ran=False)
    try:
        with SessionLocal() as db:
            processed = job.run(db)
            db.commit()
    except Exception as exc:  # una tarea rota no frena a las demás
        logger.exception("Falló la tarea periódica %s", job.name)
        _finish(job, ok=False, processed=None, error=f"{type(exc).__name__}: {exc}")
        return JobOutcome(job.name, ran=True, ok=False, error=str(exc))
    _finish(job, ok=True, processed=processed, error=None)
    return JobOutcome(job.name, ran=True, ok=True, processed=processed)


def run_due_jobs(*, now: datetime | None = None, force: bool = False) -> list[JobOutcome]:
    return [run_job(job, now=now, force=force) for job in registered_jobs()]
