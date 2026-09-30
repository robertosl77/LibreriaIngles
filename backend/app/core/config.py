from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


BACKEND_DIR = Path(__file__).resolve().parents[2]


def escape_configparser_value(value: str) -> str:
    """Escape percent signs before passing values through ConfigParser."""
    return value.replace("%", "%%")


class Settings(BaseSettings):
    app_name: str = "Libreria Ingles API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/libreria_ingles.db"
    cors_origins: str = "http://localhost:4200"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        url = make_url(self.database_url)

        if url.get_backend_name() != "sqlite":
            return self.database_url

        if not url.database or url.database == ":memory:":
            return self.database_url

        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = (BACKEND_DIR / database_path).resolve()

        return url.set(database=database_path.as_posix()).render_as_string(
            hide_password=False
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
