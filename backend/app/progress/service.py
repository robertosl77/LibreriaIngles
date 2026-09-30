"""Progreso por skill: score + intentos + confianza + estado + tendencia.

El progreso se recalcula desde los intentos evaluados (fuente de verdad), así
una apelación o una re-evaluación nunca cuentan dos veces.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import utcnow
from app.curriculum.service import find_skill, get_level
from app.learning.models import Attempt, Exercise, StudySkillProgress

MASTERED_SCORE = 85
MASTERED_MIN_ATTEMPTS = 5
REVIEW_SCORE = 60
REVIEW_MIN_ATTEMPTS = 3


def _confidence(count: int) -> str:
    if count >= 12:
        return "high"
    if count >= 5:
        return "medium"
    return "low"


def _status(score: float, count: int) -> str:
    if score >= MASTERED_SCORE and count >= MASTERED_MIN_ATTEMPTS:
        return "MASTERED"
    if score < REVIEW_SCORE and count >= REVIEW_MIN_ATTEMPTS:
        return "NEEDS_REVIEW"
    return "LEARNING"


def _ema(scores: list[float]) -> float:
    """Promedio al principio; con más evidencia pesan más los intentos recientes."""
    value = 0.0
    for index, score in enumerate(scores, start=1):
        alpha = max(0.25, 1 / index)
        value = value + alpha * (score - value)
    return value


def recompute_skill(
    db: Session,
    *,
    study_profile_id: int,
    skill_key: str,
    organization_id: int | None = None,
) -> StudySkillProgress:
    query = (
        select(Attempt.score, Attempt.evaluated_at, Attempt.membership_id)
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .where(
            Attempt.study_profile_id == study_profile_id,
            Exercise.skill_key == skill_key,
            Attempt.score.is_not(None),
        )
        .order_by(Attempt.evaluated_at, Attempt.id)
    )
    if organization_id is not None:
        query = query.where(Attempt.organization_id == organization_id)
    rows = db.execute(query).all()
    scores = [float(row.score) for row in rows]

    progress = db.scalar(
        select(StudySkillProgress).where(
            StudySkillProgress.study_profile_id == study_profile_id,
            StudySkillProgress.skill_key == skill_key,
            StudySkillProgress.organization_id.is_(None)
            if organization_id is None
            else StudySkillProgress.organization_id == organization_id,
        )
    )
    if progress is None:
        progress = StudySkillProgress(
            study_profile_id=study_profile_id,
            skill_key=skill_key,
            organization_id=organization_id,
        )
        db.add(progress)

    count = len(scores)
    score = round(_ema(scores), 1) if scores else 0.0
    trend = None
    if count >= 4:
        previous = _ema(scores[:-3])
        delta = score - previous
        trend = "up" if delta >= 5 else "down" if delta <= -5 else "stable"

    progress.score = score
    progress.attempt_count = count
    progress.confidence = _confidence(count)
    progress.status = _status(score, count)
    progress.trend = trend
    progress.last_practiced_at = rows[-1].evaluated_at if rows else None
    progress.updated_at = utcnow()
    if organization_id is not None and rows:
        progress.membership_id = rows[-1].membership_id
    return progress


def progress_by_skill(db: Session, study_profile_id: int) -> dict[str, StudySkillProgress]:
    rows = db.scalars(
        select(StudySkillProgress).where(
            StudySkillProgress.study_profile_id == study_profile_id,
            StudySkillProgress.organization_id.is_(None),
        )
    ).all()
    return {row.skill_key: row for row in rows}


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def dashboard(db: Session, study_profile_id: int, level: str) -> dict:
    """Árbol nivel → área → tema → skill, con agregados solo sobre lo practicado."""
    curriculum = get_level(level)
    if curriculum is None:
        return {"level": level, "areas": []}
    progress = progress_by_skill(db, study_profile_id)

    areas: dict[str, dict] = {}
    for skill in curriculum.skills:
        area = areas.setdefault(
            skill.area_key,
            {"key": skill.area_key, "name": skill.area_name, "topics": {}},
        )
        topic = area["topics"].setdefault(
            skill.topic_key,
            {"key": skill.topic_key, "name": skill.topic_name, "skills": []},
        )
        row = progress.get(skill.key)
        topic["skills"].append(
            {
                "key": skill.key,
                "name": skill.name,
                "score": row.score if row and row.attempt_count else None,
                "attemptCount": row.attempt_count if row else 0,
                "confidence": row.confidence if row else "low",
                "status": row.status if row and row.attempt_count else "NOT_STARTED",
                "trend": row.trend if row else None,
            }
        )

    result_areas = []
    for area in areas.values():
        topics = []
        for topic in area["topics"].values():
            practiced = [s["score"] for s in topic["skills"] if s["score"] is not None]
            topics.append({**topic, "score": _average(practiced)})
        practiced_area = [
            s["score"] for t in topics for s in t["skills"] if s["score"] is not None
        ]
        result_areas.append(
            {
                "key": area["key"],
                "name": area["name"],
                "score": _average(practiced_area),
                "attemptCount": sum(
                    s["attemptCount"] for t in topics for s in t["skills"]
                ),
                "topics": topics,
            }
        )

    all_scores = [
        s["score"]
        for a in result_areas
        for t in a["topics"]
        for s in t["skills"]
        if s["score"] is not None
    ]
    weakest = sorted(
        (
            {"key": s["key"], "name": f'{t["name"]} · {s["name"]}', "score": s["score"]}
            for a in result_areas
            for t in a["topics"]
            for s in t["skills"]
            if s["score"] is not None
        ),
        key=lambda s: s["score"],
    )[:3]
    return {
        "level": level,
        "overallScore": _average(all_scores),
        "skillsPracticed": len(all_scores),
        "skillsTotal": len(curriculum.skills),
        "weakest": weakest,
        "areas": result_areas,
    }


def skill_name(skill_key: str | None) -> str | None:
    if not skill_key:
        return None
    skill = find_skill(skill_key)
    return f"{skill.topic_name} · {skill.name}" if skill else skill_key
