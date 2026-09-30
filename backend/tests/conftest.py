import os

import pytest

# Los tests nunca deben apuntar a la base SQLite de desarrollo.
# Se establece antes de importar la aplicación.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEV_LOGIN_ENABLED"] = "true"
os.environ["MOCK_AI_ENABLED"] = "true"
os.environ["JWT_SECRET"] = "test-secret-with-at-least-32-bytes!!"
os.environ["PLATFORM_OWNER_EMAILS"] = "owner@example.com"


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
