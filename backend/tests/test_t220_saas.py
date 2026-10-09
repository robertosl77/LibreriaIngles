"""T-220 · Adaptación SaaS del código existente (#313)."""

import importlib

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
