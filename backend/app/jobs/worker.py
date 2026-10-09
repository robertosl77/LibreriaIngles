"""T-220 · Hilo que corre las tareas periódicas.

En local arranca junto con la API (JOBS_IN_PROCESS=true). En producción conviene un proceso aparte
(`python -m app.jobs`) y JOBS_IN_PROCESS=false en la API; el lease evita corridas dobles igual.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import settings
from app.jobs.runner import run_due_jobs

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(self, tick_seconds: float) -> None:
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="periodic-jobs", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def run_forever(self) -> None:
        self._loop()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_due_jobs()
            except Exception:
                logger.exception("Falló el ciclo de tareas periódicas.")
            self._stop.wait(self.tick_seconds)


def start_in_process_worker() -> JobWorker | None:
    if not settings.jobs_in_process:
        return None
    worker = JobWorker(settings.jobs_tick_seconds)
    worker.start()
    return worker
