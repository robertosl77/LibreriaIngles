"""Certificados de nivel (T-024).

Se guardan los datos para siempre; el PDF no se almacena: se vuelve a generar
idéntico desde estos datos con la plantilla fija (sin IA).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LevelCertificate(Base):
    __tablename__ = "level_certificates"
    __table_args__ = (
        UniqueConstraint("study_profile_id", "level", name="uq_level_certificates_profile_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Código público de verificación (ej.: LI-A1-7K3Q-9XWD).
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    study_profile_id: Mapped[int] = mapped_column(ForeignKey("study_profiles.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    exam_session_id: Mapped[int] = mapped_column(ForeignKey("class_sessions.id"))
    holder_name: Mapped[str] = mapped_column(String(160))
    level: Mapped[str] = mapped_column(String(2))
    score: Mapped[float] = mapped_column(Float)
    area_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
