"""Examen de aprobación de nivel y certificado (T-024).

- Se propone cuando el progreso del nivel es suficiente (cobertura + promedio).
- Es una sesión aparte (kind=EXAM): no cuenta para el progreso de las clases,
  no tiene lecciones ni "rehacer".
- Aprueba con promedio global mínimo Y mínimo en cada área, para que una
  debilidad importante no quede compensada por otras áreas.
- Al aprobar se emite un certificado propio de Librería Inglés con código de
  verificación. Se guardan los datos; el documento se regenera idéntico.
"""

import math
import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import utcnow
from app.ai.service import AIResult
from app.classes.generation import GenerationFailed, generate_content, slot_for
from app.core.deps import StudyContext
from app.curriculum.service import CEFR_LEVELS, available_levels, get_level
from app.exams.models import LevelCertificate
from app.learning.models import (
    Attempt,
    ClassSession,
    ClassSessionStatus,
    Exercise,
    SessionKind,
)
from app.progress.service import progress_by_skill

# Estructura del examen: ejercicios por área (se omiten áreas sin skills en el nivel).
EXAM_BLUEPRINT = {"grammar": 5, "vocabulary": 3, "listening": 2, "reading": 2, "writing": 2}
PASS_SCORE = 70  # promedio global mínimo
AREA_MIN_SCORE = 60  # mínimo en cada área
ELIGIBLE_COVERAGE = 0.7  # porción de skills del nivel practicadas
ELIGIBLE_SCORE = 70  # promedio de las skills practicadas
RETRY_COOLDOWN = timedelta(hours=24)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I


class ExamError(Exception):
    pass


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def current_level(study: StudyContext) -> str | None:
    return study.profile.operational_level or study.profile.selected_level


def _exams(db: Session, profile_id: int, level: str) -> list[ClassSession]:
    return list(
        db.scalars(
            select(ClassSession)
            .where(
                ClassSession.study_profile_id == profile_id,
                ClassSession.kind == SessionKind.EXAM,
                ClassSession.target_level == level,
            )
            .order_by(ClassSession.created_at.desc(), ClassSession.id.desc())
        )
    )


def certificate_of(db: Session, profile_id: int, level: str) -> LevelCertificate | None:
    return db.scalar(
        select(LevelCertificate).where(
            LevelCertificate.study_profile_id == profile_id,
            LevelCertificate.level == level,
        )
    )


def _next_level(level: str) -> dict | None:
    index = CEFR_LEVELS.index(level) if level in CEFR_LEVELS else -1
    if index < 0 or index + 1 >= len(CEFR_LEVELS):
        return None
    following = CEFR_LEVELS[index + 1]
    return {"level": following, "available": following in available_levels()}


def exam_status(db: Session, study: StudyContext) -> dict:
    level = current_level(study)
    curriculum = get_level(level) if level else None
    if curriculum is None:
        return {"level": level, "available": False}

    progress = progress_by_skill(db, study.profile.id)
    practiced = [
        progress[s.key].score
        for s in curriculum.skills
        if s.key in progress and progress[s.key].attempt_count > 0
    ]
    total = len(curriculum.skills)
    coverage = len(practiced) / total if total else 0
    average = round(sum(practiced) / len(practiced), 1) if practiced else None
    needed = math.ceil(ELIGIBLE_COVERAGE * total)
    checks = [
        {
            "key": "coverage",
            "label": f"Practicar al menos el {int(ELIGIBLE_COVERAGE * 100)} % de los temas del nivel",
            "ok": coverage >= ELIGIBLE_COVERAGE,
            "detail": f"{len(practiced)} de {total} temas (necesitás {needed})",
        },
        {
            "key": "score",
            "label": f"Promedio de {ELIGIBLE_SCORE} % o más en lo practicado",
            "ok": average is not None and average >= ELIGIBLE_SCORE,
            "detail": f"{average} %" if average is not None else "Sin práctica todavía",
        },
    ]
    eligible = all(c["ok"] for c in checks)

    exams = _exams(db, study.profile.id, level)
    open_exam = next((e for e in exams if e.status != ClassSessionStatus.COMPLETED), None)
    completed = [e for e in exams if e.status == ClassSessionStatus.COMPLETED]
    last = completed[0] if completed else None
    certificate = certificate_of(db, study.profile.id, level)

    cooldown_until = None
    if last and certificate is None and last.exam_result and not last.exam_result.get("passed"):
        until = _aware(last.evaluated_at) + RETRY_COOLDOWN if last.evaluated_at else None
        if until and until > utcnow():
            cooldown_until = until

    return {
        "level": level,
        "available": True,
        "eligible": eligible,
        "checks": checks,
        "passed": certificate is not None,
        "certificateCode": certificate.code if certificate else None,
        "openExamId": open_exam.id if open_exam else None,
        "lastExam": (
            {"id": last.id, "score": last.score, "result": last.exam_result, "evaluatedAt": last.evaluated_at}
            if last
            else None
        ),
        "attempts": len(completed),
        "cooldownUntil": cooldown_until,
        "canStart": eligible and certificate is None and open_exam is None and cooldown_until is None,
        "nextLevel": _next_level(level),
        "rules": {
            "passScore": PASS_SCORE,
            "areaMinScore": AREA_MIN_SCORE,
            "exercises": sum(EXAM_BLUEPRINT.get(a, 0) for a in {s.area_key for s in curriculum.skills}),
            "retryHours": int(RETRY_COOLDOWN.total_seconds() // 3600),
        },
    }


def exam_slots(level: str, rng=None) -> list[dict]:
    """Ejercicios repartidos por área, con skills al azar (independiente del progreso)."""
    rng = rng or random.Random()
    curriculum = get_level(level)
    slots: list[dict] = []
    for area, count in EXAM_BLUEPRINT.items():
        skills = [s for s in curriculum.skills if s.area_key == area]
        if not skills:
            continue
        pool = list(skills)
        rng.shuffle(pool)
        for index in range(count):
            slots.append(slot_for(pool[index % len(pool)], rng))
    return slots


def create_exam(db: Session, study: StudyContext) -> tuple[ClassSession, AIResult | None]:
    status = exam_status(db, study)
    if not status.get("available"):
        raise ExamError("Elegí un nivel disponible antes de rendir el examen.")
    if status["passed"]:
        raise ExamError(f"Ya aprobaste el nivel {status['level']}.")
    if status["openExamId"]:
        raise ExamError("Ya tenés un examen en curso.")
    if status["cooldownUntil"]:
        raise ExamError("Podés volver a rendir el examen 24 horas después del último intento.")
    if not status["eligible"]:
        raise ExamError("Todavía no cumplís los requisitos para rendir el examen.")

    level = status["level"]
    session = ClassSession(
        study_profile_id=study.profile.id,
        account_id=study.account.id,
        organization_id=study.organization_id,
        membership_id=study.membership_id,
        kind=SessionKind.EXAM,
        status=ClassSessionStatus.GENERATING,
        target_level=level,
        title=f"Examen de nivel {level}",
        generation_request={"level": level, "purpose": "exam", "slots": exam_slots(level)},
    )
    db.add(session)
    db.commit()  # persistir la solicitud antes de llamar a la IA
    try:
        result = generate_content(db, study, session)
    except GenerationFailed as exc:  # pragma: no cover - generate_content no la lanza hoy
        raise ExamError(str(exc)) from exc
    return session, result


def _new_code(db: Session, level: str) -> str:
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"LI-{level}-{raw[:4]}-{raw[4:]}"
        if db.scalar(select(LevelCertificate.id).where(LevelCertificate.code == code)) is None:
            return code


def holder_name(account: Account | None) -> str:
    if account is None:
        return "Alumno"
    return (account.display_name or "").strip() or account.email.split("@")[0]


def finalize_exam(db: Session, session: ClassSession) -> dict:
    """Calcula el resultado por área y, si aprueba, emite el certificado (idempotente)."""
    attempts = db.execute(
        select(Attempt, Exercise)
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .where(
            Exercise.class_session_id == session.id,
            Attempt.attempt_number == session.current_attempt,
        )
    ).all()
    curriculum = get_level(session.target_level)
    names = {s.area_key: s.area_name for s in curriculum.skills} if curriculum else {}

    by_area: dict[str, list[float]] = {}
    for attempt, exercise in attempts:
        by_area.setdefault(exercise.area or "other", []).append(attempt.score or 0)
    areas = []
    for key in [k for k in EXAM_BLUEPRINT if k in by_area] + [k for k in by_area if k not in EXAM_BLUEPRINT]:
        scores = by_area[key]
        score = round(sum(scores) / len(scores), 1)
        areas.append(
            {
                "key": key,
                "name": names.get(key, key),
                "score": score,
                "items": len(scores),
                "passed": score >= AREA_MIN_SCORE,
            }
        )
    total = [attempt.score or 0 for attempt, _ in attempts]
    score = round(sum(total) / len(total), 1) if total else 0.0
    passed = bool(areas) and score >= PASS_SCORE and all(a["passed"] for a in areas)
    session.exam_result = {
        "passed": passed,
        "score": score,
        "passScore": PASS_SCORE,
        "areaMinScore": AREA_MIN_SCORE,
        "areas": areas,
    }

    if passed and certificate_of(db, session.study_profile_id, session.target_level) is None:
        account = db.get(Account, session.account_id) if session.account_id else None
        db.add(
            LevelCertificate(
                code=_new_code(db, session.target_level),
                study_profile_id=session.study_profile_id,
                account_id=session.account_id,
                exam_session_id=session.id,
                holder_name=holder_name(account),
                level=session.target_level,
                score=score,
                area_scores={a["name"]: a["score"] for a in areas},
            )
        )
    db.commit()
    return session.exam_result


def certificate_payload(certificate: LevelCertificate) -> dict:
    curriculum = get_level(certificate.level)
    return {
        "code": certificate.code,
        "holderName": certificate.holder_name,
        "level": certificate.level,
        "levelName": curriculum.name if curriculum else None,
        "score": certificate.score,
        "areaScores": certificate.area_scores,
        "issuedAt": certificate.issued_at,
        "issuer": "Librería Inglés",
        "notice": (
            "Certificado emitido por Librería Inglés según su propio examen de nivel, "
            "con referencia a los niveles del MCER (CEFR). No es una certificación oficial "
            "CEFR ni de Cambridge u otro organismo."
        ),
    }
