import os

import pytest

# Los tests nunca deben apuntar a la base SQLite ni depender de la configuración
# local del desarrollador. Todo lo que cambia el comportamiento de P01/P02 se fija
# antes de importar la aplicación para que un backend/.env personal no vuelva
# no determinista la suite.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEV_LOGIN_ENABLED"] = "true"
os.environ["MOCK_AI_ENABLED"] = "true"
os.environ["JWT_SECRET"] = "test-secret-with-at-least-32-bytes!!"
os.environ["PLATFORM_OWNER_EMAILS"] = "owner@example.com"

# P01: los tests de onboarding usan explícitamente el provider simulado salvo
# aquellos casos que lo deshabilitan con monkeypatch para probar PENDING.
os.environ["ORGANIZATION_VERIFICATION_MOCK_ENABLED"] = "true"

# P02: valores canónicos del challenge y provider seguro de test.
os.environ["VERIFICATION_CODE_TTL_MINUTES"] = "25"
os.environ["VERIFICATION_MAX_ATTEMPTS"] = "3"
os.environ["VERIFICATION_RESEND_COOLDOWN_SECONDS"] = "60"
os.environ["VERIFICATION_MAX_SENDS_PER_HOUR"] = "5"
os.environ["VERIFICATION_MAX_SENDS_PER_DESTINATION_PER_HOUR"] = "5"
os.environ["EMAIL_DELIVERY_PROVIDER"] = "dev"


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db import Base, engine
    from app.main import app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)


def login(client, email: str = "roberto@example.com") -> dict:
    response = client.post("/api/v1/auth/dev-login", json={"email": email, "name": "Roberto"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}
