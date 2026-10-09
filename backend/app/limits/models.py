"""T-220 (N-01) · Valores de límites a nivel plataforma."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlatformLimit(Base):
    """Valor por defecto de un límite para toda la plataforma (lo configura el dueño).

    Antes era `ai_platform_limits` (T-217). Se generaliza: cualquier límite declarado en
    `app.limits.registry` guarda acá su valor de plataforma; cada plan puede pisarlo en `Plan.limits`.
    """

    __tablename__ = "platform_limits"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
