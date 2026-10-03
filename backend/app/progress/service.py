"""Progreso por skill: score + intentos + confianza + estado + tendencia.

El progreso se recalcula desde los intentos evaluados (fuente de verdad), así
una apelación o una re-evaluación nunca cuentan dos veces.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import utcnow
from app.curriculum.service import find_skill, get_level
from app.learning.models import (
    Assistance,
    Attempt,
    ClassSession,
    Exercise,
    SessionKind,
    StudySkillProgress,
)

MASTERED_SCORE = 85
MASTERED_MIN_ATTEMPTS = 5
REVIEW_SCORE = 60
REVIEW_MIN_ATTEMPTS = 3
# Un intento respondido con ayuda (lección/pista) cuenta como media evidencia (T-020).
ASSISTED_WEIGHT = 0.5
RECENT_WINDOW = 5


def _confidence(count: float) -> str:
    if count >= 12:
        return "high"
    if count >= 5:
        return "medium"
    return "low"


def _status(score: float, count: float, assisted_recent: int = 0) -> str:
    # Pedir ayuda es señal de debilidad aunque la respuesta sea correcta (T-034):
    # con ayuda reciente no se considera dominado.
    if score >= MASTERED_SCORE and count >= MASTERED_MIN_ATTEMPTS and not assisted_recent:
        return "MASTERED"
    if score < REVIEW_SCORE and count >= REVIEW_MIN_ATTEMPTS:
        return "NEEDS_REVIEW"
    return "LEARNING"


def _ema(scores: list[float], weights: list[float] | None = None) -> float:
    """Promedio al principio; con más evidencia pesan más los intentos recientes.

    `weights` (0..1) reduce cuánto mueve el score un intento: con ayuda, la mitad.
    """
    weights = weights or [1.0] * len(scores)
    value = 0.0
    evidence = 0.0
    for score, weight in zip(scores, weights):
        evidence += weight
        alpha = max(0.25, 1 / evidence) * weight if evidence else 0.0
        value = value + min(1.0, alpha) * (score - value)
    return value


SECONDARY_CURRICULAR_WEIGHT = 0.5


def secondary_skill_results(result: dict | None) -> list[dict]:
    return [
        item for item in (result or {}).get("secondarySkillResults") or []
        if isinstance(item, dict)
        and item.get("skillKey")
        and isinstance(item.get("score"), (int, float))
        and not isinstance(item.get("score"), bool)
    ]


def secondary_skill_keys(result: dict | None) -> set[str]:
    return {item["skillKey"] for item in secondary_skill_results(result)}


def recompute_skill(
    db: Session,
    *,
    study_profile_id: int,
    skill_key: str,
    organization_id: int | None = None,
) -> StudySkillProgress:
    """Recalcula una skill con evidencia principal y evidencia curricular secundaria (T-048)."""
    query = (
        select(Attempt, Exercise)
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .join(ClassSession, ClassSession.id == Exercise.class_session_id)
        .where(
            Attempt.study_profile_id == study_profile_id,
            Attempt.score.is_not(None),
            # El examen de nivel es independiente del progreso de las clases (T-024).
            ClassSession.kind == SessionKind.CLASS,
        )
        .order_by(Attempt.evaluated_at, Attempt.id)
    )
    if organization_id is not None:
        query = query.where(Attempt.organization_id == organization_id)
    rows = db.execute(query).all()

    evidence_rows: list[dict] = []
    for attempt, exercise in rows:
        assisted = (attempt.assistance or Assistance.NONE) != Assistance.NONE
        if exercise.skill_key == skill_key:
            evidence_rows.append(
                {
                    "score": float(attempt.score),
                    "weight": ASSISTED_WEIGHT if assisted else 1.0,
                    "assisted": assisted,
                    "evaluated_at": attempt.evaluated_at,
                    "membership_id": attempt.membership_id,
                }
            )
        for item in secondary_skill_results(attempt.evaluation_result):
            if item["skillKey"] != skill_key or exercise.skill_key == skill_key:
                continue
            evidence_rows.append(
                {
                    "score": float(item["score"]),
                    "weight": SECONDARY_CURRICULAR_WEIGHT * (ASSISTED_WEIGHT if assisted else 1.0),
                    "assisted": assisted,
                    "evaluated_at": attempt.evaluated_at,
                    "membership_id": attempt.membership_id,
                }
            )

    scores = [row["score"] for row in evidence_rows]
    weights = [row["weight"] for row in evidence_rows]

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
    evidence = sum(weights)
    score = round(_ema(scores, weights), 1) if scores else 0.0
    trend = None
    if count >= 4:
        previous = _ema(scores[:-3], weights[:-3])
        delta = score - previous
        trend = "up" if delta >= 5 else "down" if delta <= -5 else "stable"

    assisted_recent = sum(1 for row in evidence_rows[-RECENT_WINDOW:] if row["assisted"])
    progress.score = score
    progress.attempt_count = count
    progress.confidence = _confidence(evidence)
    progress.assisted_recent = assisted_recent
    progress.status = _status(score, evidence, assisted_recent)
    progress.trend = trend
    progress.last_practiced_at = evidence_rows[-1]["evaluated_at"] if evidence_rows else None
    progress.updated_at = utcnow()
    if organization_id is not None and evidence_rows:
        progress.membership_id = evidence_rows[-1]["membership_id"]
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
                "assistedRecent": row.assisted_recent if row else 0,
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
    writing = next((area for area in result_areas if area["key"] == "writing"), None)
    orthography_topic = (
        next((topic for topic in writing["topics"] if topic["key"] == "orthography"), None)
        if writing else None
    )
    orthography_skills = orthography_topic["skills"] if orthography_topic else []
    orthography_practiced = [s for s in orthography_skills if s["score"] is not None]
    orthography_score = _average([s["score"] for s in orthography_practiced])
    orthography_attempts = sum(s["attemptCount"] for s in orthography_skills)
    orthography_help = sum(s["assistedRecent"] for s in orthography_skills)
    orthography_status = (
        "NOT_STARTED"
        if orthography_score is None
        else _status(orthography_score, orthography_attempts, orthography_help)
    )

    return {
        "level": level,
        "overallScore": _average(all_scores),
        "skillsPracticed": len(all_scores),
        "skillsTotal": len(curriculum.skills),
        "weakest": weakest,
        "areas": result_areas,
        "orthography": {
            "name": "Ortografía",
            "score": orthography_score,
            "skillsPracticed": len(orthography_practiced),
            "skillsTotal": len(orthography_skills),
            "attemptCount": orthography_attempts,
            "assistedRecent": orthography_help,
            "status": orthography_status,
        },
        "abilities": ability_progress(db, study_profile_id, level),
    }


def ability_progress(db: Session, study_profile_id: int, level: str) -> list[dict]:
    """Progreso por habilidad del idioma (T-034) a partir de las evidencias de cada intento.

    Mismo cálculo que una skill: EMA ponderada (la ayuda y las señales secundarias pesan menos),
    tendencia sobre los últimos intentos y cuántas evidencias fueron con ayuda.
    """
    from app.progress.evidence import ABILITIES, attempt_evidence

    rows = db.execute(
        select(Attempt, Exercise)
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .join(ClassSession, ClassSession.id == Exercise.class_session_id)
        .where(
            Attempt.study_profile_id == study_profile_id,
            Attempt.score.is_not(None),
            Exercise.level == level,
            ClassSession.kind == SessionKind.CLASS,
        )
        .order_by(Attempt.evaluated_at, Attempt.id)
    ).all()

    series: dict[str, list] = {key: [] for key, _ in ABILITIES}
    # De qué temas vino la evidencia de cada habilidad (para Listening/Speaking/Pronunciation).
    sources: dict[str, dict[str, dict]] = {key: {} for key, _ in ABILITIES}
    practice: list[float] = []
    for attempt, exercise in rows:
        for item in attempt_evidence(attempt, exercise):
            series[item.ability].append(item)
            src = sources[item.ability].setdefault(
                exercise.skill_key or "", {"scores": [], "assisted": 0}
            )
            src["scores"].append(item.score)
            src["assisted"] += int(item.assisted)
        practice += (attempt.signals or {}).get("practiceScores") or []

    result = []
    for key, name in ABILITIES:
        items = series[key]
        scores = [e.score for e in items]
        weights = [e.weight for e in items]
        count = len(scores)
        score = round(_ema(scores, weights), 1) if scores else None
        assisted_recent = sum(1 for e in items[-RECENT_WINDOW:] if e.assisted)
        trend = None
        if count >= 4:
            delta = score - _ema(scores[:-3], weights[:-3])
            trend = "up" if delta >= 5 else "down" if delta <= -5 else "stable"
        item = {
            "key": key,
            "name": name,
            "score": score,
            "evidenceCount": count,
            "assistedCount": sum(1 for e in items if e.assisted),
            # Señal de debilidad para el balanceo (etapa 3): ayuda en las últimas evidencias.
            "assistedRecent": assisted_recent,
            "trend": trend,
            "status": _status(score, sum(weights), assisted_recent) if scores else "NOT_STARTED",
        }
        item["sources"] = sorted(
            (
                {
                    "skillKey": skill_key,
                    "name": skill_name(skill_key) or skill_key,
                    "count": len(src["scores"]),
                    "score": _average(src["scores"]),
                    "assistedCount": src["assisted"],
                }
                for skill_key, src in sources[key].items()
            ),
            key=lambda s: (-s["count"], s["name"]),
        )
        if key == "PRONUNCIATION":
            # La práctica no pesa en el puntaje: se muestra su evolución aparte.
            item["practiceTrials"] = len(practice)
            item["practiceFirst"] = practice[0] if practice else None
            item["practiceLast"] = practice[-1] if practice else None
        result.append(item)
    return result


def skill_name(skill_key: str | None) -> str | None:
    if not skill_key:
        return None
    skill = find_skill(skill_key)
    return f"{skill.topic_name} · {skill.name}" if skill else skill_key
