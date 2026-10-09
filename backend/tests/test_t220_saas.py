"""T-220 · Adaptación SaaS del código existente (#313)."""

import importlib

import pytest

from sqlalchemy import func, select

from app.db import SessionLocal
from tests.conftest import login

API = "/api/v1"


def owner(client) -> dict:
    return login(client, "owner@example.com")


# ---------------------------------------------------------------- E-07 rutas DEV


def _paths(router) -> set[str]:
    from fastapi import FastAPI

    probe = FastAPI()
    probe.include_router(router)
    return set(probe.openapi()["paths"])


def test_dev_routes_are_mounted_outside_production() -> None:
    import app.api as api_module

    paths = _paths(api_module.router)
    assert "/auth/dev-login" in paths
    assert "/organization-onboarding/dev-purge" in paths
    assert "/platform/accounts/{account_id}/dev-purge" in paths


def test_dev_routes_do_not_exist_in_production(monkeypatch) -> None:
    import app.api as api_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    try:
        reloaded = importlib.reload(api_module)
        paths = _paths(reloaded.router)
        assert "/auth/dev-login" not in paths
        assert "/organization-onboarding/dev-purge" not in paths
        assert "/platform/accounts/{account_id}/dev-purge" not in paths
        # Las rutas normales siguen.
        assert "/auth/google" in paths
    finally:
        monkeypatch.setattr(settings, "app_env", "test")
        importlib.reload(api_module)


# ---------------------------------------------------------------- E-04 siembras al arrancar


def test_reference_data_is_seeded_at_startup(client) -> None:
    from app.campaigns.models import Campaign
    from app.notifications.models import NotificationCase
    from app.organizations.models import JobTitle
    from app.subscriptions.models import Plan

    with SessionLocal() as db:
        assert db.scalar(select(func.count(Plan.id))) > 0
        assert db.scalar(select(func.count(Campaign.id))) > 0
        assert db.scalar(select(func.count(JobTitle.id))) > 0
        assert db.scalar(select(func.count(NotificationCase.id))) > 0


def test_listing_services_does_not_write(client) -> None:
    from app.subscriptions.models import Plan

    headers = owner(client)
    with SessionLocal() as db:
        plan = db.scalars(select(Plan).order_by(Plan.id)).first()
        db.delete(plan)
        db.commit()
        before = db.scalar(select(func.count(Plan.id)))

    assert client.get(f"{API}/platform/services", headers=headers).status_code == 200

    with SessionLocal() as db:
        # Antes el GET volvía a sembrar el plan borrado.
        assert db.scalar(select(func.count(Plan.id))) == before


def test_reading_a_notification_case_does_not_insert_it(client) -> None:
    from app.notifications.models import NotificationCase
    from app.notifications.service import ORGANIZATION_EMAIL_VERIFICATION, get_notification_case

    with SessionLocal() as db:
        db.query(NotificationCase).delete()
        db.commit()
        case = get_notification_case(db, ORGANIZATION_EMAIL_VERIFICATION)
        assert case.code == ORGANIZATION_EMAIL_VERIFICATION
        db.commit()
        assert db.scalar(select(func.count(NotificationCase.id))) == 0


# ---------------------------------------------------------------- E-13 marca


def test_branding_endpoint_is_public_and_configurable(client, monkeypatch) -> None:
    from app.core.config import settings

    assert client.get(f"{API}/system/branding").json() == {"name": settings.brand_name}
    monkeypatch.setattr(settings, "brand_name", "Pañales SA")
    assert client.get(f"{API}/system/branding").json() == {"name": "Pañales SA"}


# ---------------------------------------------------------------- E-01 contexto de empresa


def _student_with_level(client, email: str = "ana@example.com") -> dict:
    headers = login(client, email)
    assert client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers).status_code == 200
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    return headers


def _organization(name: str = "Acme") -> int:
    from app.organizations.models import Organization

    with SessionLocal() as db:
        org = Organization(slug=name.lower(), legal_name=f"{name} SA", display_name=name)
        db.add(org)
        db.commit()
        return org.id


def _membership(email: str, organization_id: int, *, status=None) -> int:
    from app.accounts.models import Account
    from app.memberships.models import Membership, MembershipStatus

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == email))
        membership = Membership(
            account_id=account.id,
            organization_id=organization_id,
            status=status or MembershipStatus.ACTIVE,
        )
        db.add(membership)
        db.commit()
        return membership.id


def test_without_header_the_request_is_personal(client) -> None:
    headers = _student_with_level(client)
    me = client.get(f"{API}/me", headers=headers).json()
    assert me["activeOrganizationId"] is None
    assert me["organizations"] == []


def test_header_with_active_membership_sets_the_organization(client) -> None:
    from app.learning.models import ClassSession

    headers = _student_with_level(client)
    org_id = _organization()
    membership_id = _membership("ana@example.com", org_id)
    org_headers = {**headers, "X-Organization-Id": str(org_id)}

    me = client.get(f"{API}/me", headers=org_headers).json()
    assert me["activeOrganizationId"] == org_id
    assert me["organizations"] == [{"id": org_id, "name": "Acme", "role": "STUDENT"}]

    klass = client.post(f"{API}/classes", headers=org_headers)
    assert klass.status_code == 201, klass.text
    with SessionLocal() as db:
        session = db.get(ClassSession, klass.json()["id"])
        # Antes quedaba siempre None aunque el alumno estudiara para su empresa.
        assert session.organization_id == org_id
        assert session.membership_id == membership_id


def test_header_of_a_foreign_organization_is_rejected(client) -> None:
    headers = _student_with_level(client)
    _student_with_level(client, "beto@example.com")
    org_id = _organization()
    _membership("beto@example.com", org_id)

    response = client.get(f"{API}/me", headers={**headers, "X-Organization-Id": str(org_id)})
    assert response.status_code == 403


def test_revoked_membership_cannot_act_for_the_organization(client) -> None:
    from app.memberships.models import MembershipStatus

    headers = _student_with_level(client)
    org_id = _organization()
    _membership("ana@example.com", org_id, status=MembershipStatus.REVOKED)

    response = client.post(f"{API}/classes", headers={**headers, "X-Organization-Id": str(org_id)})
    assert response.status_code == 403
    assert client.get(f"{API}/me", headers=headers).json()["organizations"] == []


# ---------------------------------------------------------------- E-02 / E-11 tareas periódicas


def _run(name: str, **kwargs):
    from app.jobs.registry import get_job
    from app.jobs.runner import run_job

    return run_job(get_job(name), **kwargs)


def test_jobs_are_registered_from_framework_and_core() -> None:
    from app.jobs.registry import registered_jobs

    names = {job.name for job in registered_jobs()}
    assert {
        "subscriptions.expire",
        "campaigns.reconcile_first_login",
        "classes.process_pending_evaluations",
    } <= names


def test_me_is_a_pure_read(client) -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    headers = login(client)
    commits: list[int] = []

    def count(_session) -> None:
        commits.append(1)

    event.listen(Session, "before_commit", count)
    try:
        assert client.get(f"{API}/me", headers=headers).status_code == 200
    finally:
        event.remove(Session, "before_commit", count)
    # Antes /me reconciliaba campañas, vencía suscripciones y hacía commit.
    assert commits == []


def test_expired_subscription_reads_as_expired_and_the_job_persists_it(client) -> None:
    from datetime import datetime, timedelta, timezone

    from app.accounts.models import Account
    from app.subscriptions.models import Plan, Subscription, SubscriptionStatus
    from app.subscriptions.service import grant_service

    headers = login(client)
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == "roberto@example.com"))
        plan = db.scalar(select(Plan).where(Plan.code == "INDIVIDUAL_PLATFORM"))
        subscription = grant_service(db, account, plan, granted_by=None, days=3)
        subscription.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
        subscription_id = subscription.id

    # La lectura ya lo muestra vencido aunque la tarea no haya corrido...
    service = client.get(f"{API}/me", headers=headers).json()["service"]
    assert service["source"] == "BYOK"
    assert service["expired"]["name"] == plan.name
    with SessionLocal() as db:
        # ...y no escribió nada.
        assert db.get(Subscription, subscription_id).status == SubscriptionStatus.ACTIVE

    outcome = _run("subscriptions.expire", force=True)
    assert outcome.ok and outcome.processed == 1
    with SessionLocal() as db:
        row = db.get(Subscription, subscription_id)
        assert row.status == SubscriptionStatus.EXPIRED
        assert row.ended_at is not None


def test_job_lease_prevents_a_second_run_in_the_same_window(client) -> None:
    from app.jobs.models import JobLease

    first = _run("subscriptions.expire")
    second = _run("subscriptions.expire")
    assert first.ran is True
    assert second.ran is False
    with SessionLocal() as db:
        lease = db.get(JobLease, "subscriptions.expire")
        assert lease.last_ok is True
        assert lease.locked_until is not None


def test_a_failing_job_is_recorded_and_does_not_stop_the_others(client, monkeypatch) -> None:
    from app.jobs import registry
    from app.jobs.models import JobLease
    from app.jobs.runner import run_due_jobs

    def boom(db):
        raise RuntimeError("boom")

    job = registry.get_job("subscriptions.expire")
    monkeypatch.setitem(registry._JOBS, job.name, registry.PeriodicJob(job.name, job.every_seconds, boom, ""))

    outcomes = {o.name: o for o in run_due_jobs()}
    assert outcomes["subscriptions.expire"].ok is False
    assert outcomes["campaigns.reconcile_first_login"].ok is True
    with SessionLocal() as db:
        assert "boom" in db.get(JobLease, "subscriptions.expire").last_error


def test_pending_evaluation_is_completed_by_the_job_without_the_browser(client, monkeypatch) -> None:
    from app.core.config import settings
    from app.learning.models import ClassSession, ClassSessionStatus

    # Mismo escenario que test_all_providers_down_keeps_answers_and_recovers, pero sin que el
    # navegador llame a /process-pending: lo resuelve la tarea periódica.
    monkeypatch.setattr(settings, "ai_rule_first_closed", False)
    headers = _student_with_level(client)
    klass = client.post(f"{API}/classes", headers=headers).json()
    answers = {
        str(e["id"]): "Every morning I get up early and I drink coffee with my family."
        for e in klass["exercises"]
    }
    connections = client.get(f"{API}/ai/connections", headers=headers).json()
    client.patch(
        f"{API}/ai/connections/{connections[0]['id']}",
        json={"model": "mock-fail-quota"},
        headers=headers,
    )
    submitted = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    ).json()
    if submitted["status"] != "AWAITING_EVALUATION":
        pytest.skip("todo se resolvió sin IA: no hay pendiente que probar")

    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Backup", "model": "mock", "priority": 2},
        headers=headers,
    )
    outcome = _run("classes.process_pending_evaluations", force=True)
    assert outcome.ok and outcome.processed == 1
    with SessionLocal() as db:
        assert db.get(ClassSession, klass["id"]).status == ClassSessionStatus.COMPLETED


def test_in_process_worker_runs_jobs_and_stops(client) -> None:
    import time

    from app.jobs.models import JobLease
    from app.jobs.worker import JobWorker

    worker = JobWorker(tick_seconds=0.05)
    worker.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            with SessionLocal() as db:
                if db.scalar(select(func.count(JobLease.name)).where(JobLease.last_ok.is_(True))) >= 3:
                    break
            time.sleep(0.05)
    finally:
        worker.stop()
    with SessionLocal() as db:
        assert db.scalar(select(func.count(JobLease.name)).where(JobLease.last_ok.is_(True))) >= 3
