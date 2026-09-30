from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, Settings


def test_relative_sqlite_path_is_resolved_from_backend() -> None:
    settings = Settings(database_url="sqlite:///./data/test.db")

    url = make_url(settings.resolved_database_url)

    assert Path(url.database).resolve() == (BACKEND_DIR / "data" / "test.db").resolve()


def test_in_memory_sqlite_url_is_not_rewritten() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    assert settings.resolved_database_url == "sqlite+pysqlite:///:memory:"
