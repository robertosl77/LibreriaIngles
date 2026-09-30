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

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
