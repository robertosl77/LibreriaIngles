from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.classes.api import SWITCH_NOTICE, _detail
from app.core.deps import CurrentStudy, DbSession
from app.exams import service
from app.exams.models import LevelCertificate

router = APIRouter(tags=["exams"])


@router.get("/exams/status")
def exam_status(study: CurrentStudy, db: DbSession) -> dict:
    """Estado del examen del nivel actual: requisitos, intento en curso, aprobación."""
    return service.exam_status(db, study)


@router.post("/exams", status_code=status.HTTP_201_CREATED)
def create_exam(study: CurrentStudy, db: DbSession) -> dict:
    try:
        session, result = service.create_exam(db, study)
    except service.ExamError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    notice = SWITCH_NOTICE if result and result.switched else None
    return _detail(db, session, notice)


@router.get("/certificates")
def my_certificates(study: CurrentStudy, db: DbSession) -> list[dict]:
    rows = db.scalars(
        select(LevelCertificate)
        .where(LevelCertificate.study_profile_id == study.profile.id)
        .order_by(LevelCertificate.issued_at)
    ).all()
    return [service.certificate_payload(row) for row in rows]


@router.get("/certificates/{code}")
def verify_certificate(code: str, db: DbSession) -> dict:
    """Público: cualquiera con el código puede ver y verificar el certificado."""
    certificate = db.scalar(
        select(LevelCertificate).where(LevelCertificate.code == code.strip().upper())
    )
    if certificate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificado inexistente.")
    return service.certificate_payload(certificate)
