from configparser import ConfigParser
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, Settings, escape_configparser_value


def test_relative_sqlite_path_is_resolved_from_backend() -> None:
    settings = Settings(database_url="sqlite:///./data/test.db")

    url = make_url(settings.resolved_database_url)

    assert Path(url.database).resolve() == (BACKEND_DIR / "data" / "test.db").resolve()


def test_in_memory_sqlite_url_is_not_rewritten() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    assert settings.resolved_database_url == "sqlite+pysqlite:///:memory:"


def test_alembic_configparser_accepts_percent_encoded_windows_drive() -> None:
    # SQLAlchemy puede convertir E:/... en E%3A/... al renderizar la URL.
    windows_sqlite_url = (
        "sqlite:///E%3A/Bibliotecas/Documents/GitHub/"
        "LibreriaIngles/backend/data/libreria_ingles.db"
    )

    parser = ConfigParser()
    parser.add_section("alembic")
    parser.set(
        "alembic",
        "sqlalchemy.url",
        escape_configparser_value(windows_sqlite_url),
    )

    assert parser.get("alembic", "sqlalchemy.url") == windows_sqlite_url
