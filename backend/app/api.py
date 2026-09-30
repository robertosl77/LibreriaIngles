from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/meta", tags=["system"])
def meta() -> dict[str, object]:
    return {
        "product": "Librería Inglés",
        "apiVersion": "v1",
        "architecture": {
            "backend": "FastAPI",
            "persistence": "SQLAlchemy",
            "database": "SQLite (local) / PostgreSQL (planned)",
        },
    }
