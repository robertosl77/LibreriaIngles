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
# T-220: los tests corren las tareas periódicas a mano (sin hilo de fondo).
os.environ["JOBS_IN_PROCESS"] = "false"


@pytest.fixture(autouse=True)
def isolate_organization_registry(monkeypatch, tmp_path):
    """Evita que la suite use por accidente el padrón RNS local del desarrollador."""
    from app.organizations import verification

    monkeypatch.setattr(
        verification.settings,
        "organization_registry_path",
        str(tmp_path / "missing-rns.db"),
    )


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


def correct_answer(exercise) -> str:
    """Respuesta correcta de cualquier tipo de ejercicio, armada desde su answer key (T-183)."""
    import json

    key = exercise.answer_key or {}
    kind = exercise.exercise_type
    if kind == "match_pairs":
        return json.dumps(key["pairs"])
    if kind == "listen_form":
        return json.dumps({label: answers[0] for label, answers in key["fields"].items()})
    if kind == "gap_text":
        return json.dumps([gap[0] for gap in key["gaps"]])
    if kind == "short_writing":
        return "My name is Ana. I live in Rosario and I work in an office."
    if kind == "conversation":
        return "Hi! I'm Ana. I'm fine, thanks."
    return key["acceptedAnswers"][0]
