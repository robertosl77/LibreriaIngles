from sqlalchemy import select

from app.accounts.models import Account
from app.ai.models import (
    AIConnection,
    AIConnectionOwnerType,
    AIConnectionStatus,
    AIProviderUsageMapping,
    AIUsageEvent,
)
from app.ai.service import run_json_task
from app.ai.usage import AIUsageContext, normalize_usage
from app.db import SessionLocal

from conftest import login


API = "/api/v1"


def _account(db, email: str) -> Account:
    account = db.scalar(select(Account).where(Account.email == email))
    assert account is not None
    return account


def test_usage_normalization_is_driven_by_database_mapping(client) -> None:
    with SessionLocal() as db:
        db.add(
            AIProviderUsageMapping(
                provider="CUSTOM",
                input_tokens_path="metrics.request.tokens",
                output_tokens_path="metrics.response.tokens",
                total_tokens_path=None,
                active=True,
            )
        )
        db.commit()

        assert normalize_usage(
            db,
            "CUSTOM",
            {
                "metrics": {
                    "request": {"tokens": 17},
                    "response": {"tokens": "9"},
                }
            },
        ) == (17, 9, 26)

        # Cambiar el contrato del proveedor es dato, no código del motor de consumo.
        mapping = db.get(AIProviderUsageMapping, "CUSTOM")
        assert mapping is not None
        mapping.input_tokens_path = "new_usage.in"
        mapping.output_tokens_path = "new_usage.out"
        mapping.total_tokens_path = "new_usage.total"
        db.commit()

        assert normalize_usage(
            db,
            "CUSTOM",
            {"new_usage": {"in": 4, "out": 6, "total": 10}},
        ) == (4, 6, 10)


def test_mock_usage_is_persisted_with_subject_and_visible_in_my_consumption(client) -> None:
    headers = login(client, "student@example.com")

    with SessionLocal() as db:
        account = _account(db, "student@example.com")
        db.add(
            AIProviderUsageMapping(
                provider="MOCK",
                input_tokens_path="usage.input_tokens",
                output_tokens_path="usage.output_tokens",
                total_tokens_path="usage.total_tokens",
                active=True,
            )
        )
        db.add(
            AIConnection(
                owner_type=AIConnectionOwnerType.ACCOUNT,
                owner_id=account.id,
                provider="MOCK",
                name="Mock personal",
                model="mock",
                priority=1,
                active=True,
                status=AIConnectionStatus.AVAILABLE,
            )
        )
        db.commit()

        result = run_json_task(
            db,
            account,
            system="test",
            user="test",
            task={"kind": "campaign_assist", "description": "bienvenida", "benefits": []},
            usage_context=AIUsageContext(
                subject_type="TEST_OBJECT",
                subject_id=77,
                subject_label="Objeto de prueba",
                subject_route="/app/clase/77",
            ),
        )
        assert result.connection.provider == "MOCK"

        event = db.scalar(
            select(AIUsageEvent)
            .where(AIUsageEvent.account_id == account.id)
            .order_by(AIUsageEvent.id.desc())
        )
        assert event is not None
        assert (event.input_tokens, event.output_tokens, event.total_tokens) == (120, 40, 160)
        assert event.subject_type == "TEST_OBJECT"
        assert event.subject_id == 77
        assert event.subject_route == "/app/clase/77"
        assert event.service_source == "BYOK"

    response = client.get(f"{API}/ai/usage", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "ME"
    assert body["summary"]["requests"] == 1
    assert body["summary"]["measuredRequests"] == 1
    assert body["summary"]["totalTokens"] == 160
    assert body["rows"][0]["provider"] == "MOCK"
    assert body["rows"][0]["model"] == "mock"
    assert body["rows"][0]["actualSource"] == "BYOK"
    assert body["rows"][0]["subject"]["id"] == 77
    assert body["rows"][0]["subject"]["route"] == "/app/clase/77"


def test_personal_consumption_masks_platform_engine_details(client) -> None:
    headers = login(client, "student@example.com")

    with SessionLocal() as db:
        account = _account(db, "student@example.com")
        db.add(
            AIUsageEvent(
                connection_id=None,
                connection_name="OpenAI interna",
                owner_type=AIConnectionOwnerType.PLATFORM,
                provider="OPENAI",
                model="gpt-secret",
                account_id=account.id,
                service_source="HYBRID",
                operation="evaluate_answer",
                input_tokens=25,
                output_tokens=5,
                total_tokens=30,
                success=True,
            )
        )
        db.commit()

    response = client.get(f"{API}/ai/usage", headers=headers)
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["provider"] == "PLATFORM"
    assert row["model"] is None
    assert row["connectionName"] == "IA de Librería Inglés"
    assert row["serviceSource"] == "HYBRID"
    assert row["actualSource"] == "PLATFORM"


def test_platform_owner_can_use_global_consumption_scope(client) -> None:
    student_headers = login(client, "student@example.com")
    assert student_headers

    with SessionLocal() as db:
        student = _account(db, "student@example.com")
        db.add(
            AIUsageEvent(
                connection_id=None,
                connection_name="Gemini propia",
                owner_type=AIConnectionOwnerType.ACCOUNT,
                provider="GEMINI",
                model="gemini-2.5-flash",
                account_id=student.id,
                service_source="BYOK",
                operation="generate_class",
                input_tokens=100,
                output_tokens=30,
                total_tokens=130,
                success=True,
            )
        )
        db.commit()

    owner_headers = login(client, "owner@example.com")
    scopes = client.get(f"{API}/ai/usage/scopes", headers=owner_headers)
    assert scopes.status_code == 200
    assert {item["kind"] for item in scopes.json()} >= {"ME", "PLATFORM"}

    response = client.get(f"{API}/ai/usage", headers=owner_headers, params={"scope": "PLATFORM"})
    assert response.status_code == 200, response.text
    rows = response.json()["rows"]
    student_row = next(row for row in rows if row["accountEmail"] == "student@example.com")
    assert student_row["provider"] == "GEMINI"
    assert student_row["model"] == "gemini-2.5-flash"
    assert student_row["totalTokens"] == 130
