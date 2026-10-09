"""T-220 · Catálogo de tareas periódicas.

El framework no conoce qué hace cada tarea: cada módulo (framework o core) registra las suyas con
`@periodic_job`. El runner las corre fuera del request, sin depender de que alguien entre a la app.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

JobFunction = Callable[[Session], int]


@dataclass(frozen=True)
class PeriodicJob:
    name: str
    every_seconds: int
    run: JobFunction
    description: str


_JOBS: dict[str, PeriodicJob] = {}


def periodic_job(name: str, *, every_seconds: int, description: str) -> Callable[[JobFunction], JobFunction]:
    """Registra una tarea. La función recibe una sesión y devuelve cuántos ítems procesó."""

    def decorator(func: JobFunction) -> JobFunction:
        if name in _JOBS and _JOBS[name].run is not func:
            raise RuntimeError(f"La tarea {name} ya está registrada.")
        _JOBS[name] = PeriodicJob(name=name, every_seconds=every_seconds, run=func, description=description)
        return func

    return decorator


def registered_jobs() -> list[PeriodicJob]:
    from app.jobs import catalog  # noqa: F401  (composición: importa los módulos que registran)

    return sorted(_JOBS.values(), key=lambda job: job.name)


def get_job(name: str) -> PeriodicJob:
    for job in registered_jobs():
        if job.name == name:
            return job
    raise KeyError(name)
