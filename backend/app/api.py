from fastapi import APIRouter

from app.ai.api import router as ai_router
from app.auth.api import router as auth_router
from app.classes.api import router as classes_router
from app.campaigns.api import router as campaign_notices_router
from app.exams.api import router as exams_router
from app.platform.api import router as platform_router
from app.platform.campaigns_api import router as platform_campaigns_router
from app.platform.services_api import router as platform_services_router
from app.progress.api import router as progress_router
from app.system.api import router as system_router

router = APIRouter()
router.include_router(system_router)
router.include_router(auth_router)
router.include_router(ai_router)
router.include_router(classes_router)
router.include_router(campaign_notices_router)
router.include_router(exams_router)
router.include_router(progress_router)
router.include_router(platform_router)
router.include_router(platform_campaigns_router)
router.include_router(platform_services_router)
