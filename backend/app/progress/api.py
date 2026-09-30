from fastapi import APIRouter

from app.core.deps import CurrentStudy, DbSession
from app.progress.service import dashboard

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("")
def get_progress(study: CurrentStudy, db: DbSession) -> dict:
    level = study.profile.operational_level or study.profile.selected_level or "A1"
    return dashboard(db, study.profile.id, level)
