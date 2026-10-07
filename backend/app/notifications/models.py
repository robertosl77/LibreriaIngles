from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationCase(Base):
    """Caso semántico de aviso reutilizable.

    El dominio consumidor conoce `code`; plantilla/remitente/provider se resuelven aquí.
    La administración PLATFORM_OWNER podrá editar estos datos más adelante sin acoplar
    los módulos consumidores al mecanismo físico de envío.
    """

    __tablename__ = "notification_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    channel: Mapped[str] = mapped_column(String(24), default="EMAIL")
    subject_template: Mapped[str] = mapped_column(String(300))
    body_template: Mapped[str] = mapped_column(String(4000))
    sender_profile: Mapped[str] = mapped_column(String(120))
    platform_only: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_override_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
