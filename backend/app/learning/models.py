from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClassSessionStatus(str, Enum):
    GENERATING = "GENERATING"
    GENERATION_FAILED = "GENERATION_FAILED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EVALUATION_PENDING = "EVALUATION_PENDING"
    COMPLETED = "COMPLETED"


class EvaluationMode(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    HYBRID = "HYBRID"
    AI = "AI"


class EvaluationSource(str, Enum):
    RULE_MATCH = "RULE_MATCH"
    COMMON_ERROR_MATCH = "COMMON_ERROR_MATCH"
    AI = "AI"


class ClassSession(Base):
    __tablename__ = "class_sessions"

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
    status: Mapped[ClassSessionStatus] = mapped_column(
        SqlEnum(ClassSessionStatus, native_enum=False),
        default=ClassSessionStatus.GENERATING,
    )
    generation_request: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id")
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
    exercise_type: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    answer_key: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        SqlEnum(EvaluationMode, native_enum=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    study_profile_id: Mapped[int] = mapped_column(
        ForeignKey("study_profiles.id")
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id"), nullable=True
    )
    raw_answer: Mapped[str] = mapped_column(Text)
    normalized_answer: Mapped[str] = mapped_column(Text)
    evaluation_source: Mapped[EvaluationSource | None] = mapped_column(
        SqlEnum(EvaluationSource, native_enum=False), nullable=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class StudySkillProgress(Base):
    __tablename__ = "study_skill_progress"
    __table_args__ = (
        UniqueConstraint(
            "study_profile_id",
            "skill_key",
            "organization_id",
            name="uq_study_skill_progress_scope",
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
    trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
