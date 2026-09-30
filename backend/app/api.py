from fastapi import APIRouter

from app.system.api import router as system_router

router = APIRouter()
router.include_router(system_router)
