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

    # Autenticación
    jwt_secret: str = "dev-insecure-change-me-in-production-32b"
    jwt_expire_minutes: int = 60 * 24 * 7
    google_client_id: str = ""
    # Login sin Google para desarrollo local. Nunca se habilita en production.
    dev_login_enabled: bool = False
    # Emails (separados por coma) que reciben el rol PLATFORM_OWNER al ingresar.
    platform_owner_emails: str = ""

    # Cifrado de API keys (clave Fernet). Obligatoria en production.
    encryption_key: str = ""

    # Proveedor de IA simulado para desarrollo y tests. Nunca en production.
    mock_ai_enabled: bool = False
    ai_timeout_seconds: float = 60.0

    # T-168 · Eficiencia de IA en clases. Cada mejora se puede apagar para comparar antes/después.
    # T-169: presupuesto de razonamiento por tarea (Gemini 2.5 Flash/Flash-Lite).
    ai_reasoning_control: bool = True
    ai_reasoning_budget_open: int = 512  # corrección de escritura libre y conversación
    # T-173: esquema JSON obligatorio en la respuesta (Gemini).
    ai_response_schema: bool = True
    # T-171: corregir en una sola llamada las respuestas de una clase que necesitan IA.
    ai_batch_evaluation: bool = True
    # T-172: fill_blank y rewrite escritos se resuelven por regla antes de ir a la IA.
    ai_rule_first_closed: bool = True
    # T-178: el ejemplo semilla viaja a la IA en versión compacta.
    ai_compact_examples: bool = True
    # T-181: máximo de respuestas por llamada de corrección en lote (examen).
    ai_batch_max_items: int = 6

    # P01 B2B: padrón oficial RNS sincronizado localmente + fallback DEV.
    organization_registry_path: str = "data/rns_registry.db"
    organization_verification_mock_enabled: bool = True

    # P02: challenge reutilizable de verificación.
    verification_code_ttl_minutes: int = 25
    verification_max_attempts: int = 3
    verification_resend_cooldown_seconds: int = 60
    # Límite por onboarding/contexto y, por separado, por buzón destinatario.
    verification_max_sends_per_hour: int = 5
    verification_max_sends_per_destination_per_hour: int = 5

    # Delivery de email. `dev` captura el código únicamente fuera de production.
    # `smtp` permite un primer provider real sin acoplar el onboarding al proveedor.
    email_delivery_provider: str = "dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 20.0
    smtp_from_email: str = ""
    smtp_from_name: str = "Sr. Marcos"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def dev_login_allowed(self) -> bool:
        return self.dev_login_enabled and not self.is_production

    @property
    def mock_ai_allowed(self) -> bool:
        return self.mock_ai_enabled and not self.is_production

    @property
    def organization_verification_mock_allowed(self) -> bool:
        return self.organization_verification_mock_enabled and not self.is_production

    @property
    def resolved_organization_registry_path(self) -> Path:
        path = Path(self.organization_registry_path)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path

    @property
    def dev_account_purge_allowed(self) -> bool:
        """Borrado físico de cuentas de prueba: solo local/dev/test, nunca QA o producción."""
        return self.app_env.lower() in {"local", "dev", "development", "test"}

    @property
    def platform_owner_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.platform_owner_emails.split(",")
            if email.strip()
        }

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
