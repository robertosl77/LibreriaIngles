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
        "product": settings.brand_name,
        "apiVersion": "v1",
        "architecture": {
            "backend": "FastAPI",
            "persistence": "SQLAlchemy",
            "database": "SQLite (local) / PostgreSQL (planned)",
            "domains": True,
        },
    }


@router.get("/system/branding", tags=["system"])
def branding() -> dict[str, str]:
    """T-220 (E-13): marca visible del producto. Pública: la usa la pantalla de inicio sin sesión."""
    return {"name": settings.brand_name}
