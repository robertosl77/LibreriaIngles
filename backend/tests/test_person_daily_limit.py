"""T-217 (#306): tope diario por persona sumando todas las conexiones de plataforma."""

import pytest

from conftest import login


@pytest.fixture
def db(client):
    from app.db import SessionLocal

    with SessionLocal() as session:
        yield session


def _account(db, email, role=None):
    from app.accounts.models import Account, AccountType, AuthMethod

    account = Account(email=email, account_type=AccountType.PERSONAL, auth_method=AuthMethod.LOCAL,
                      platform_role=role)
    db.add(account)
    db.flush()
    return account


def _platform(db, name):
    from app.ai.models import AIConnection, AIConnectionOwnerType

    connection = AIConnection(provider="MOCK", name=name, model="mock", priority=1, active=True,
                              owner_type=AIConnectionOwnerType.PLATFORM)
    db.add(connection)
    db.flush()
    return connection


def _use(db, connection, account, count, success=True, operation="generate_class"):
    from app.ai.models import AIUsageEvent

    for _ in range(count):
        db.add(AIUsageEvent(connection_id=connection.id, connection_name=connection.name,
                            owner_type=connection.owner_type, provider="MOCK", model="mock",
                            operation=operation, account_id=account.id, success=success, total_tokens=10))
    db.flush()


def _cap(db, value):
    from app.ai.models import AIPlatformLimit
    from app.ai.service import PERSON_DAILY_REQUESTS

    db.merge(AIPlatformLimit(key=PERSON_DAILY_REQUESTS, value=value))
    db.flush()


def test_cap_sums_all_platform_connections_and_failover_does_not_reset(db):
    from app.ai.service import limit_reason

    a, b = _platform(db, "A"), _platform(db, "B")
    student = _account(db, "alumno@example.com")
    _cap(db, 3)
    _use(db, a, student, 2)
    assert limit_reason(db, b, student) is None
    _use(db, b, student, 1)
    # Con 3 pedidos entre A y B, ninguna conexión de plataforma le sirve hoy.
    assert "límite diario" in limit_reason(db, a, student)
    assert "límite diario" in limit_reason(db, b, student)


def test_failures_health_checks_and_other_people_do_not_count(db):
    from app.ai.service import limit_reason

    a = _platform(db, "A")
    student, other = _account(db, "uno@example.com"), _account(db, "otro@example.com")
    _cap(db, 2)
    _use(db, a, student, 5, success=False)
    _use(db, a, student, 5, operation="health_check")
    _use(db, a, other, 5)
    _use(db, a, student, 1)
    assert limit_reason(db, a, student) is None


def test_owner_is_exempt_and_no_cap_means_unlimited(db):
    from app.accounts.models import PlatformRole
    from app.ai.service import limit_reason

    a = _platform(db, "A")
    owner = _account(db, "dueno@example.com", PlatformRole.PLATFORM_OWNER)
    student = _account(db, "alumno2@example.com")
    _use(db, a, owner, 10)
    _use(db, a, student, 10)
    assert limit_reason(db, a, student) is None  # sin tope configurado
    _cap(db, 2)
    assert limit_reason(db, a, owner) is None
    assert limit_reason(db, a, student) is not None


def test_only_owner_configures_the_cap(client):
    student = login(client)
    assert client.get("/api/v1/platform/ai-limits", headers=student).status_code == 403
    owner = login(client, "owner@example.com")
    assert client.get("/api/v1/platform/ai-limits", headers=owner).json() == {"personDailyRequests": None}
    assert client.put("/api/v1/platform/ai-limits", json={"personDailyRequests": 0}, headers=owner).status_code == 422
    saved = client.put("/api/v1/platform/ai-limits", json={"personDailyRequests": 40}, headers=owner).json()
    assert saved == {"personDailyRequests": 40}
    cleared = client.put("/api/v1/platform/ai-limits", json={"personDailyRequests": None}, headers=owner).json()
    assert cleared == {"personDailyRequests": None}


def test_repeated_reason_is_shown_once():
    from app.ai.service import NoAIAvailable

    err = NoAIAvailable(["IA de la plataforma: tope", "IA de la plataforma: tope", "X: otra"])
    assert err.errors == ["IA de la plataforma: tope", "X: otra"]
