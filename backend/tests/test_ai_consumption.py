import random

import pytest
from sqlalchemy import select

from app.accounts.models import Account
from app.ai.models import (
    AIConnection,
    AIConnectionOwnerType,
    AIConnectionStatus,
    AIProviderUsageMapping,
    AIUsageEvent,
)
from app.ai.service import NoAIAvailable, run_json_task
from app.ai.usage import AIUsageContext, normalize_usage
from app.db import SessionLocal

from conftest import login


API = "/api/v1"


@pytest.fixture(autouse=True)
def _preserve_random_state():
    """Los escenarios de Consumo no deben alterar la generación aleatoria de tests posteriores."""
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


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
                reasoning_tokens_path="metrics.thinking.tokens",
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
                    "thinking": {"tokens": 5},
                    "response": {"tokens": "9"},
                }
            },
        ) == (17, 5, 9, 31)

        # Cambiar el contrato del proveedor es dato, no código del motor de consumo.
        mapping = db.get(AIProviderUsageMapping, "CUSTOM")
        assert mapping is not None
        mapping.input_tokens_path = "new_usage.in"
        mapping.output_tokens_path = "new_usage.out"
        mapping.reasoning_tokens_path = "new_usage.think"
        mapping.total_tokens_path = "new_usage.total"
        db.commit()

        assert normalize_usage(
            db,
            "CUSTOM",
            {"new_usage": {"in": 4, "think": 2, "out": 6, "total": 12}},
        ) == (4, 2, 6, 12)


def test_mock_usage_is_persisted_with_subject_and_visible_in_my_consumption(client) -> None:
    headers = login(client, "student@example.com")

    with SessionLocal() as db:
        account = _account(db, "student@example.com")
        db.add(
            AIProviderUsageMapping(
                provider="MOCK",
                input_tokens_path="usage.input_tokens",
                output_tokens_path="usage.output_tokens",
                reasoning_tokens_path=None,
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
        assert (
            event.input_tokens,
            event.reasoning_tokens,
            event.output_tokens,
            event.total_tokens,
        ) == (120, None, 40, 160)
        assert event.subject_type == "TEST_OBJECT"
        assert event.subject_id == 77
        assert event.subject_route == "/app/clase/77"
        assert event.service_source == "BYOK"
        assert event.diagnostic_snapshot is not None
        assert event.diagnostic_snapshot["requestKind"] == "TEXT_JSON"
        assert event.diagnostic_snapshot["systemChars"] == len("test")
        assert event.diagnostic_snapshot["userChars"] == len("test")
        assert len(event.diagnostic_snapshot["systemFingerprint"]) == 16
        assert event.diagnostic_snapshot["responseJsonChars"] > 0

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



def test_consumption_diagnostic_detects_outlier_against_comparable_calls(client) -> None:
    headers = login(client, "student@example.com")

    with SessionLocal() as db:
        account = _account(db, "student@example.com")
        totals = [100, 110, 120, 400]
        input_tokens = [80, 90, 95, 320]
        user_chars = [500, 520, 530, 2200]
        conversation_chars = [100, 110, 120, 900]
        events = []
        for total, input_count, user_count, conversation_count in zip(
            totals, input_tokens, user_chars, conversation_chars
        ):
            event = AIUsageEvent(
                connection_id=None,
                connection_name="Mock personal",
                owner_type=AIConnectionOwnerType.ACCOUNT,
                provider="MOCK",
                model="mock",
                account_id=account.id,
                service_source="BYOK",
                operation="evaluate_answer",
                subject_type="EXERCISE",
                subject_label="Corrección de prueba",
                input_tokens=input_count,
                reasoning_tokens=5,
                output_tokens=total - input_count - 5,
                total_tokens=total,
                diagnostic_snapshot={
                    "version": 1,
                    "requestKind": "TEXT_JSON",
                    "systemChars": 1000,
                    "userChars": user_count,
                    "details": {
                        "exerciseType": "conversation",
                        "presentationMode": "LISTEN",
                        "responseMode": "SPEAK",
                        "conversationTurns": 2,
                        "conversationChars": conversation_count,
                    },
                },
                success=True,
            )
            db.add(event)
            events.append(event)
        db.commit()
        outlier_id = events[-1].id

    response = client.get(f"{API}/ai/usage/{outlier_id}/diagnostic", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    diagnostic = body["diagnostic"]
    assert diagnostic["tokens"]["total"] == 400
    assert diagnostic["snapshot"]["userChars"] == 2200
    assert diagnostic["comparison"]["sampleSize"] == 4
    assert diagnostic["comparison"]["enoughSample"] is True
    assert diagnostic["comparison"]["medianTotalTokens"] == 115.0
    assert diagnostic["comparison"]["totalVsMedian"] > 3
    signal_keys = {item["key"] for item in diagnostic["comparison"]["signals"]}
    assert {"inputTokens", "userChars", "conversationChars"} <= signal_keys
    assert "no atribuyen causalidad" in diagnostic["note"]


def test_personal_diagnostic_keeps_platform_provider_and_model_private(client) -> None:
    headers = login(client, "student@example.com")

    with SessionLocal() as db:
        account = _account(db, "student@example.com")
        event = AIUsageEvent(
            connection_id=None,
            connection_name="Interna",
            owner_type=AIConnectionOwnerType.PLATFORM,
            provider="OPENAI",
            model="gpt-interno",
            account_id=account.id,
            service_source="PLATFORM",
            operation="evaluate_answer",
            subject_type="EXERCISE",
            input_tokens=20,
            output_tokens=5,
            total_tokens=25,
            diagnostic_snapshot={
                "version": 1,
                "requestKind": "TEXT_JSON",
                "systemChars": 100,
                "userChars": 50,
            },
            success=True,
        )
        db.add(event)
        db.commit()
        event_id = event.id

    response = client.get(f"{API}/ai/usage/{event_id}/diagnostic", headers=headers)
    assert response.status_code == 200, response.text
    cohort = response.json()["diagnostic"]["comparison"]["cohort"]
    assert cohort["provider"] == "PLATFORM"
    assert cohort["model"] is None


def test_failover_attempts_share_execution_and_report_recovery(client) -> None:
    headers = login(client, "failover@example.com")

    with SessionLocal() as db:
        account = _account(db, "failover@example.com")
        db.add_all(
            [
                AIConnection(
                    owner_type=AIConnectionOwnerType.ACCOUNT,
                    owner_id=account.id,
                    provider="MOCK",
                    name="Primaria",
                    model="mock-fail-down",
                    priority=1,
                    active=True,
                    status=AIConnectionStatus.AVAILABLE,
                ),
                AIConnection(
                    owner_type=AIConnectionOwnerType.ACCOUNT,
                    owner_id=account.id,
                    provider="MOCK",
                    name="Backup",
                    model="mock",
                    priority=2,
                    active=True,
                    status=AIConnectionStatus.AVAILABLE,
                ),
            ]
        )
        db.commit()

        result = run_json_task(
            db,
            account,
            system="test",
            user="test",
            task={"kind": "campaign_assist", "description": "bienvenida", "benefits": []},
        )
        assert result.connection.name == "Backup"

        events = list(
            db.scalars(
                select(AIUsageEvent)
                .where(
                    AIUsageEvent.account_id == account.id,
                    AIUsageEvent.operation == "campaign_assist",
                )
                .order_by(AIUsageEvent.attempt_index)
            ).all()
        )
        assert len(events) == 2
        assert events[0].execution_id
        assert events[0].execution_id == events[1].execution_id
        assert [event.attempt_index for event in events] == [1, 2]
        assert [event.success for event in events] == [False, True]
        assert events[0].error_code == "PROVIDER_DOWN"

    response = client.get(f"{API}/ai/usage", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["executions"] == 1
    assert body["summary"]["requests"] == 2
    correlated = [row for row in body["rows"] if row["execution"]]
    assert len(correlated) == 2
    assert {row["execution"]["id"] for row in correlated} == {
        correlated[0]["execution"]["id"]
    }
    assert {row["execution"]["status"] for row in correlated} == {
        "RECOVERED_BY_FAILOVER"
    }
    assert {row["execution"]["attempts"] for row in correlated} == {2}

def test_exhausted_execution_is_reported_as_interrupted(client) -> None:
    headers = login(client, "interrupted@example.com")

    with SessionLocal() as db:
        account = _account(db, "interrupted@example.com")
        db.add_all(
            [
                AIConnection(
                    owner_type=AIConnectionOwnerType.ACCOUNT,
                    owner_id=account.id,
                    provider="MOCK",
                    name="Fallida 1",
                    model="mock-fail-down",
                    priority=1,
                    active=True,
                    status=AIConnectionStatus.AVAILABLE,
                ),
                AIConnection(
                    owner_type=AIConnectionOwnerType.ACCOUNT,
                    owner_id=account.id,
                    provider="MOCK",
                    name="Fallida 2",
                    model="mock-fail-auth",
                    priority=2,
                    active=True,
                    status=AIConnectionStatus.AVAILABLE,
                ),
            ]
        )
        db.commit()

        try:
            run_json_task(
                db,
                account,
                system="test",
                user="test",
                task={"kind": "campaign_assist", "description": "bienvenida", "benefits": []},
            )
            assert False, "La ejecución debía agotar todas las conexiones."
        except NoAIAvailable:
            pass

        events = list(
            db.scalars(
                select(AIUsageEvent)
                .where(AIUsageEvent.account_id == account.id)
                .order_by(AIUsageEvent.attempt_index)
            ).all()
        )
        assert len(events) == 2
        assert events[0].execution_id == events[1].execution_id
        assert all(not event.success for event in events)

    response = client.get(f"{API}/ai/usage", headers=headers)
    assert response.status_code == 200
    rows = [row for row in response.json()["rows"] if row["execution"]]
    assert rows
    assert {row["execution"]["status"] for row in rows} == {"INTERRUPTED"}

def test_consumption_reference_includes_class_and_exercise(client) -> None:
    from app.classes.evaluation import evaluate_with_ai
    from app.learning.models import (
        Assistance,
        DraftAnswer,
        EvaluationMode,
        Exercise,
        PresentationMode,
        ResponseMode,
    )

    headers = login(client, "reference@example.com")
    assert client.put(
        f"{API}/me/level", json={"level": "A1"}, headers=headers
    ).status_code == 200
    assert client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Mock reference", "model": "mock", "priority": 1},
        headers=headers,
    ).status_code == 201

    created = client.post(f"{API}/classes", headers=headers)
    assert created.status_code == 201, created.text
    klass = created.json()

    with SessionLocal() as db:
        account = _account(db, "reference@example.com")
        exercise = db.scalar(
            select(Exercise)
            .where(Exercise.class_session_id == klass["id"])
            .order_by(Exercise.id)
        )
        assert exercise is not None
        exercise.evaluation_mode = EvaluationMode.AI
        exercise.presentation_mode = PresentationMode.LISTEN
        exercise.response_mode = ResponseMode.SPEAK
        db.add(
            DraftAnswer(
                class_session_id=klass["id"],
                exercise_id=exercise.id,
                account_id=account.id,
                answer_text="A deliberately open answer",
                audio_duration_ms=4200,
                signals={
                    "listenPlays": 3,
                    "listenSlowPlays": 1,
                    "speakRetakes": 2,
                    "practiceScores": [62, 81],
                },
                assistance=Assistance.LESSON,
            )
        )
        db.commit()

        evaluate_with_ai(db, account, exercise, "A deliberately open answer")

        event = db.scalar(
            select(AIUsageEvent)
            .where(
                AIUsageEvent.account_id == account.id,
                AIUsageEvent.operation == "evaluate_answer",
            )
            .order_by(AIUsageEvent.id.desc())
        )
        assert event is not None
        from app.classes.reference import exercise_display_number

        number = exercise_display_number(db, exercise)
        event_id = event.id
        assert event.subject_label == f"Clase #{klass['id']} · Ejercicio {number}"
        assert event.subject_route == f"/app/clase/{klass['id']}"

    report = client.get(f"{API}/ai/usage", headers=headers)
    assert report.status_code == 200
    correction = next(
        row for row in report.json()["rows"] if row["operation"] == "evaluate_answer"
    )
    assert correction["subject"]["label"] == f"Clase #{klass['id']} · Ejercicio {number}"
    assert correction["subject"]["exerciseNumber"] == number
    assert correction["subject"]["previewable"] is True

    preview = client.get(f"{API}/ai/usage/{event_id}/reference", headers=headers)
    assert preview.status_code == 200, preview.text
    detail = preview.json()
    assert detail["kind"] == "EXERCISE"
    assert detail["class"]["id"] == klass["id"]
    assert detail["exercise"]["number"] == number
    assert detail["exercise"]["id"] == exercise.id
    context = detail["exercise"]["executionContext"]
    assert context["operation"] == "evaluate_answer"
    assert context["presentationMode"] == "LISTEN"
    assert context["responseMode"] == "SPEAK"
    assert context["evaluationMode"] == "AI"
    assert context["audioDurationMs"] == 4200
    assert context["listenPlays"] == 3
    assert context["listenSlowPlays"] == 1
    assert context["speakRetakes"] == 2
    assert context["pronunciationPracticeScores"] == [62, 81]
    assert context["assistance"] == "LESSON"
    assert context["contextStats"]["answerChars"] == len("A deliberately open answer")
    assert detail["fullClassRoute"] == f"/app/clase/{klass['id']}"

    generation = next(
        row for row in report.json()["rows"] if row["operation"] == "generate_class"
    )
    class_preview = client.get(
        f"{API}/ai/usage/{generation['id']}/reference", headers=headers
    )
    assert class_preview.status_code == 200, class_preview.text
    class_detail = class_preview.json()
    assert class_detail["kind"] == "CLASS"
    assert class_detail["class"]["id"] == klass["id"]
    assert class_detail["exercises"]
    assert class_detail["generationSummary"]["logicalExercises"] >= 1
    assert class_detail["generationSummary"]["storedExerciseRows"] == len(
        class_detail["exercises"]
    )
    assert class_detail["generationSummary"]["presentationModes"]
    assert class_detail["generationSummary"]["responseModes"]

    # PLATFORM_OWNER puede auditar la clase completa desde el mismo evento,
    # pero no recibe una ruta editable hacia la clase de otra cuenta.
    owner_headers = login(client, "owner@example.com")
    owner_full = client.get(
        f"{API}/ai/usage/{event_id}/reference",
        headers=owner_headers,
        params={"view": "CLASS"},
    )
    assert owner_full.status_code == 200, owner_full.text
    owner_detail = owner_full.json()
    assert owner_detail["kind"] == "CLASS"
    assert owner_detail["class"]["id"] == klass["id"]
    assert owner_detail["exercises"]
    assert owner_detail["fullClassRoute"] is None
