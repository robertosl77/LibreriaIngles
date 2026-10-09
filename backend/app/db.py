from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def ensure_database_directory(database_url: str | None = None) -> None:
    url = make_url(database_url or settings.resolved_database_url)

    if url.get_backend_name() != "sqlite":
        return

    if not url.database or url.database == ":memory:":
        return

    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _engine_options() -> dict[str, object]:
    url = make_url(settings.resolved_database_url)
    options: dict[str, object] = {"pool_pre_ping": True}

    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}

        if url.database == ":memory:":
            options["poolclass"] = StaticPool

    return options


engine = create_engine(settings.resolved_database_url, **_engine_options())


if make_url(settings.resolved_database_url).get_backend_name() == "sqlite":
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_concurrency(dbapi_connection, _record) -> None:
        """T-211: WAL deja leer mientras otro escribe; busy_timeout hace esperar (no fallar) al
        segundo escritor. Así una corrección larga no deja en blanco otras pestañas."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=15000")
            if make_url(settings.resolved_database_url).database not in (None, "", ":memory:"):
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
