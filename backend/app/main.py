import truststore
truststore.inject_into_ssl()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registra todas las tablas en el metadata)
from app.api import router
from app.bootstrap import run_bootstrap
from app.core.config import settings
from app.jobs.worker import start_in_process_worker

if settings.is_production and settings.jwt_secret.startswith("dev-insecure"):
    raise RuntimeError("Configurá JWT_SECRET antes de levantar en production.")

@asynccontextmanager
async def lifespan(_: FastAPI):
    # T-220 (E-04): datos de referencia al arrancar; los GET ya no siembran.
    run_bootstrap()
    # T-220 (E-02/E-11): vencimientos, campañas y correcciones pendientes fuera del request.
    worker = start_in_process_worker()
    yield
    if worker is not None:
        worker.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
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
        "name": f"{settings.brand_name} API",
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
