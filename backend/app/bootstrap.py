"""T-220 (E-04) · Datos de referencia del framework.

Planes, beneficios, campaña de bienvenida, cargos y casos de notificación se siembran UNA vez al
arrancar la aplicación (idempotente), no dentro de los GET. Así las lecturas no escriben y varias
réplicas pueden atender el mismo listado sin competir por insertar las mismas filas.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db import SessionLocal

logger = logging.getLogger(__name__)


def seed_reference_data(db: Session) -> None:
    from app.benefits.service import seed_benefits
    from app.campaigns.service import seed_campaigns
    from app.notifications.service import seed_notification_cases
    from app.organizations.job_titles import seed_job_titles
    from app.subscriptions.service import seed_services

    seed_services(db)
    seed_benefits(db)
    seed_campaigns(db)
    seed_job_titles(db)
    seed_notification_cases(db)
    db.commit()


def run_bootstrap() -> None:
    """Se llama al arrancar la app. Un fallo no impide levantar el backend."""
    try:
        with SessionLocal() as db:
            seed_reference_data(db)
    except Exception:
        logger.exception("No se pudieron sembrar los datos de referencia al arrancar.")
