from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registra todas las tablas en el metadata)
from app.api import router
from app.core.config import settings

if settings.is_production and settings.jwt_secret.startswith("dev-insecure"):
    raise RuntimeError("Configurá JWT_SECRET antes de levantar en production.")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": "Librería Inglés API",
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
