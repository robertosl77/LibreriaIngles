"""T-220 · `python -m app.jobs` corre las tareas periódicas como proceso aparte.

`python -m app.jobs --once` corre un ciclo y termina (útil para un cron externo).
"""

import argparse
import logging

import app.models  # noqa: F401  (registra todas las tablas)
from app.core.config import settings
from app.jobs.runner import run_due_jobs
from app.jobs.worker import JobWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Tareas periódicas del backend.")
    parser.add_argument("--once", action="store_true", help="Correr un ciclo y salir.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.once:
        for outcome in run_due_jobs():
            print(outcome)
        return
    JobWorker(settings.jobs_tick_seconds).run_forever()


if __name__ == "__main__":
    main()
