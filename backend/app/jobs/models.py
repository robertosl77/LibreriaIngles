"""T-220 · Estado de las tareas periódicas del framework."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobLease(Base):
    """Una fila por tarea: quién la tiene tomada y cómo terminó la última corrida.

    `locked_until` es el *lease*: con varias réplicas, solo la que logra moverlo corre la tarea
    en ese ciclo. Si una réplica se cae a mitad de camino, el lease vence solo.
    """

    __tablename__ = "job_leases"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
