from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClassSessionStatus(str, Enum):
    """Ciclo de vida de una clase.

    GENERATING → READY | GENERATION_FAILED
    READY → IN_PROGRESS (primer autoguardado)
    IN_PROGRESS → AWAITING_EVALUATION (al enviar; respuestas ya persistidas)
    AWAITING_EVALUATION → COMPLETED (cuando todos los intentos quedan evaluados)
    COMPLETED → READY (rehacer: nuevo intento)
    """

    GENERATING = "GENERATING"
    GENERATION_FAILED = "GENERATION_FAILED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_EVALUATION = "AWAITING_EVALUATION"
    COMPLETED = "COMPLETED"


class EvaluationMode(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    HYBRID = "HYBRID"
    AI = "AI"


class EvaluationSource(str, Enum):
    RULE_MATCH = "RULE_MATCH"
    COMMON_ERROR_MATCH = "COMMON_ERROR_MATCH"
    AI = "AI"


class SessionKind(str, Enum):
    """Una sesión es una clase de práctica o un examen de nivel (T-024)."""

    CLASS = "CLASS"
    EXAM = "EXAM"


class Assistance(str, Enum):
    """Ayuda usada para responder un ejercicio (T-020; HINT queda para T-018).

    Orden de "fuerza": una lección pesa más que una pista.
    """

    NONE = "NONE"
    HINT = "HINT"
    LESSON = "LESSON"


ASSISTANCE_RANK = {Assistance.NONE: 0, Assistance.HINT: 1, Assistance.LESSON: 2}


def stronger_assistance(current: "Assistance | str | None", new: Assistance) -> Assistance:
    current = Assistance(current or Assistance.NONE)
    return new if ASSISTANCE_RANK[new] > ASSISTANCE_RANK[current] else current


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id"), index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", name="fk_class_sessions_account_id"), nullable=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id"), nullable=True
    )
    status: Mapped[ClassSessionStatus] = mapped_column(
        SqlEnum(ClassSessionStatus, native_enum=False),
        default=ClassSessionStatus.GENERATING,
    )
    kind: Mapped[SessionKind] = mapped_column(
        SqlEnum(SessionKind, native_enum=False, length=10),
        default=SessionKind.CLASS,
        server_default=SessionKind.CLASS.value,
    )
    # Solo exámenes: resultado por área y aprobación (T-024).
    exam_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_attempt: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_request: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "ai_connections.id",
            name="fk_class_sessions_generated_by_connection_id",
            ondelete="SET NULL",
        ), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id"), index=True
    )
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id")
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    area: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skill_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    exercise_type: Mapped[str] = mapped_column(String(80))
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    # Datos extra según el tipo: opciones, texto de lectura, etc.
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_concepts: Mapped[list] = mapped_column(JSON, default=list)
    answer_key: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        SqlEnum(EvaluationMode, native_enum=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DraftAnswer(Base):
    """Autoguardado: la respuesta en curso de cada ejercicio antes de enviar."""

    __tablename__ = "draft_answers"
    __table_args__ = (
        UniqueConstraint("exercise_id", name="uq_draft_answers_exercise"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    answer_text: Mapped[str] = mapped_column(Text, default="")
    assistance: Mapped[Assistance] = mapped_column(
        SqlEnum(Assistance, native_enum=False, length=20),
        default=Assistance.NONE,
        server_default=Assistance.NONE.value,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "attempt_number", name="uq_attempts_exercise_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id")
    )
    # Quién respondió: el perfil de estudio puede estar compartido entre cuentas.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", name="fk_attempts_account_id"), nullable=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id"), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    raw_answer: Mapped[str] = mapped_column(Text)
    normalized_answer: Mapped[str] = mapped_column(Text)
    # Si respondió después de consultar la lección (o una pista): no vale igual como evidencia.
    assistance: Mapped[Assistance] = mapped_column(
        SqlEnum(Assistance, native_enum=False, length=20),
        default=Assistance.NONE,
        server_default=Assistance.NONE.value,
    )
    evaluation_source: Mapped[EvaluationSource | None] = mapped_column(
        SqlEnum(EvaluationSource, native_enum=False), nullable=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    appealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StudySkillProgress(Base):
    """Progreso agregado por skill.

    organization_id NULL  → progreso GLOBAL del perfil (lo ve el usuario, define su nivel).
    organization_id NOT NULL → subconjunto generado bajo esa organización (lo ve el ADMIN).
    """

    __tablename__ = "study_skill_progress"
    __table_args__ = (
        Index(
            "uq_study_skill_progress_global",
            "study_profile_id",
            "skill_key",
            unique=True,
            sqlite_where=text("organization_id IS NULL"),
            postgresql_where=text("organization_id IS NULL"),
        ),
        Index(
            "uq_study_skill_progress_org",
            "study_profile_id",
            "skill_key",
            "organization_id",
            unique=True,
            sqlite_where=text("organization_id IS NOT NULL"),
            postgresql_where=text("organization_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id")
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id"), nullable=True
    )
    skill_key: Mapped[str] = mapped_column(String(160))
    score: Mapped[float] = mapped_column(Float, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str] = mapped_column(String(32), default="low")
    status: Mapped[str] = mapped_column(String(20), default="LEARNING")
    trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Cuántos de los últimos intentos se respondieron con ayuda (lección/pista):
    # el generador refuerza esas skills (T-020).
    assisted_recent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AIEvaluationCache(Base):
    __tablename__ = "ai_evaluation_cache"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id",
            "normalized_answer",
            name="uq_ai_evaluation_cache_answer",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    normalized_answer: Mapped[str] = mapped_column(Text)
    evaluation_result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
