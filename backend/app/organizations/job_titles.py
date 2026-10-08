from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organizations.models import JobTitle


SEED_JOB_TITLES = (
    "Responsable de Capacitación",
    "Responsable de Recursos Humanos",
    "Gerente de Recursos Humanos",
    "Gerente General",
    "Director/a",
    "Director/a de Recursos Humanos",
    "Jefe/a de Recursos Humanos",
    "Jefe/a de Capacitación",
    "Analista de Recursos Humanos",
    "Representante legal",
    "Apoderado/a",
    "CEO",
)

ABBREVIATIONS = {
    "rrhh": "recursos humanos",
    "rr hh": "recursos humanos",
    "rec humanos": "recursos humanos",
}


def normalize_job_title(value: str) -> str:
    text = " ".join(value.strip().split())
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())
    return ABBREVIATIONS.get(text, text)


def display_job_title(value: str) -> str:
    return " ".join(value.strip().split())


def _score(query: str, candidate: str) -> float:
    q = normalize_job_title(query)
    c = normalize_job_title(candidate)
    if not q or not c:
        return 0.0
    sequence = SequenceMatcher(None, q, c).ratio()
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    union = q_tokens | c_tokens
    jaccard = len(q_tokens & c_tokens) / len(union) if union else 0.0
    contains = 1.0 if q in c or c in q else 0.0
    return max(sequence, jaccard, 0.92 * contains)


def seed_job_titles(db: Session) -> None:
    existing = {
        row.normalized_name
        for row in db.scalars(select(JobTitle)).all()
    }
    changed = False
    for name in SEED_JOB_TITLES:
        normalized = normalize_job_title(name)
        if normalized in existing:
            continue
        db.add(
            JobTitle(
                name=name,
                normalized_name=normalized,
                active=True,
            )
        )
        existing.add(normalized)
        changed = True
    if changed:
        db.flush()


def search_job_titles(
    db: Session,
    query: str = "",
    *,
    limit: int = 8,
) -> list[tuple[JobTitle, float]]:
    seed_job_titles(db)
    rows = db.scalars(
        select(JobTitle)
        .where(JobTitle.active.is_(True))
        .order_by(JobTitle.name.asc())
    ).all()

    cleaned = display_job_title(query)
    if not cleaned:
        return [(row, 1.0) for row in rows[:limit]]

    ranked = [
        (row, _score(cleaned, row.name))
        for row in rows
    ]
    ranked = [item for item in ranked if item[1] >= 0.35]
    ranked.sort(key=lambda item: (-item[1], item[0].name.casefold()))
    return ranked[:limit]


def find_exact_job_title(db: Session, value: str) -> JobTitle | None:
    normalized = normalize_job_title(value)
    if not normalized:
        return None
    return db.scalar(
        select(JobTitle).where(
            JobTitle.normalized_name == normalized,
            JobTitle.active.is_(True),
        )
    )


def get_job_title(db: Session, job_title_id: int) -> JobTitle | None:
    row = db.get(JobTitle, job_title_id)
    if row is None or not row.active:
        return None
    return row


def resolve_job_title(
    db: Session,
    value: str,
    *,
    confirm_similar: bool = False,
) -> dict:
    seed_job_titles(db)
    display = display_job_title(value)
    normalized = normalize_job_title(display)
    if len(display) < 2 or not normalized:
        raise ValueError("Ingresá un cargo o función válido.")

    exact = find_exact_job_title(db, display)
    if exact is not None:
        return {
            "status": "EXISTING",
            "item": exact,
            "similar": [],
        }

    similar = [
        (row, score)
        for row, score in search_job_titles(db, display, limit=5)
        if score >= 0.78
    ]
    if similar and not confirm_similar:
        return {
            "status": "SIMILAR",
            "item": None,
            "similar": similar,
        }

    row = JobTitle(
        name=display,
        normalized_name=normalized,
        active=True,
    )
    db.add(row)
    db.flush()
    return {
        "status": "CREATED",
        "item": row,
        "similar": similar,
    }
