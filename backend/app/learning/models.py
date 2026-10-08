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


class PresentationMode(str, Enum):
    """Cómo recibe el alumno el ejercicio (independiente del tipo de ejercicio)."""

    READ = "READ"
    LISTEN = "LISTEN"


class ResponseMode(str, Enum):
    """Cómo responde el alumno. SPEAK: la transcripción entra al evaluador como texto."""

    WRITE = "WRITE"
    SELECT = "SELECT"
    SPEAK = "SPEAK"


# T-183: los tipos de elección comparten la respuesta SELECT; read_aloud siempre se habla.
SELECT_TYPES = {"multiple_choice", "reading_multiple_choice", "dialogue_choice", "minimal_pairs", "word_stress"}
SPEAK_ONLY_TYPES = {"read_aloud"}


def default_response_mode(exercise_type: str) -> "ResponseMode":
    if exercise_type in SPEAK_ONLY_TYPES:
        return ResponseMode.SPEAK
    return ResponseMode.SELECT if exercise_type in SELECT_TYPES else ResponseMode.WRITE


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
    # Modalidades (T-025): el tipo no cambia; cambia cómo se presenta y cómo se responde.
    presentation_mode: Mapped[PresentationMode] = mapped_column(
        SqlEnum(PresentationMode, native_enum=False, length=10),
        default=PresentationMode.READ,
        server_default=PresentationMode.READ.value,
    )
    response_mode: Mapped[ResponseMode] = mapped_column(
        SqlEnum(ResponseMode, native_enum=False, length=10),
        default=ResponseMode.WRITE,
        server_default=ResponseMode.WRITE.value,
    )
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        SqlEnum(EvaluationMode, native_enum=False)
    )
    # T-214: tanda de la práctica continua (1 en clases clásicas y exámenes).
    batch: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    # T-212: ítem del banco del que sale (o al que se guardó) este ejercicio. Sirve para no repetir.
    bank_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercise_bank_items.id", ondelete="SET NULL", name="fk_exercises_bank_item_id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class BankItemStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ExerciseBankItem(Base):
    """T-212: banco de ejercicios compartido por nivel · tema · tipo.

    Se llena con el uso: cada ejercicio que la IA genera y pasa la validación queda acá para que lo
    reusen otros alumnos (sin volver a gastar tokens). Las clases y exámenes actuales no cambian.
    """

    __tablename__ = "exercise_bank_items"
    __table_args__ = (
        Index("ix_exercise_bank_items_pick", "level", "skill_key", "exercise_type", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Huella del contenido (nivel + tema + tipo + consigna + contenido): evita duplicados.
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    level: Mapped[str] = mapped_column(String(2))
    area: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skill_key: Mapped[str] = mapped_column(String(160))
    exercise_type: Mapped[str] = mapped_column(String(80))
    presentation_mode: Mapped[PresentationMode] = mapped_column(
        SqlEnum(PresentationMode, native_enum=False, length=10)
    )
    response_mode: Mapped[ResponseMode] = mapped_column(
        SqlEnum(ResponseMode, native_enum=False, length=10)
    )
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_concepts: Mapped[list] = mapped_column(JSON, default=list)
    answer_key: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        SqlEnum(EvaluationMode, native_enum=False)
    )
    status: Mapped[BankItemStatus] = mapped_column(
        SqlEnum(BankItemStatus, native_enum=False, length=10), default=BankItemStatus.ACTIVE
    )
    retired_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Origen (auditoría): qué motor lo generó y en qué clase apareció primero.
    source_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Calidad (T-216): se actualizan con el uso.
    times_served: Mapped[int] = mapped_column(Integer, default=1)
    appeals: Mapped[int] = mapped_column(Integer, default=0)
    appeals_accepted: Mapped[int] = mapped_column(Integer, default=0)
    repeat_reports: Mapped[int] = mapped_column(Integer, default=0)
    wrong_reports: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExerciseReportReason(str, Enum):
    REPEATED = "REPEATED"  # "Este ejercicio se repite"
    WRONG = "WRONG"  # "Este ejercicio está mal"


class ExerciseReport(Base):
    """T-216: reporte del alumno sobre un ejercicio (alimenta la calidad del banco)."""

    __tablename__ = "exercise_reports"
    __table_args__ = (
        UniqueConstraint("exercise_id", "study_profile_id", "reason", name="uq_exercise_reports_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE", name="fk_exercise_reports_exercise_id"), index=True
    )
    study_profile_id: Mapped[int] = mapped_column(Integer)
    bank_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reason: Mapped[ExerciseReportReason] = mapped_column(SqlEnum(ExerciseReportReason, native_enum=False, length=10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    # Solo SPEAK: duración del audio original. El archivo nunca se persiste.
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Evaluación fonética final normalizada (T-027). Nunca contiene audio.
    pronunciation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Señales de la respuesta (T-034): escuchas, uso de lento, prácticas de pronunciación.
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    # Modalidad con la que respondió efectivamente (SPEAK → raw_answer es la transcripción).
    response_mode: Mapped[ResponseMode] = mapped_column(
        SqlEnum(ResponseMode, native_enum=False, length=10),
        default=ResponseMode.WRITE,
        server_default=ResponseMode.WRITE.value,
    )
    # SPEAK: metadato de la grabación; el audio ya fue descartado.
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Resultado fonético final, independiente de la evaluación de contenido.
    pronunciation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Señales copiadas del borrador al enviar (T-034); alimentan las evidencias por habilidad.
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
