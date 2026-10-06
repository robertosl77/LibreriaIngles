import sqlite3

import pytest

from sqlalchemy import select

from app.db import SessionLocal
from app.organizations.models import Organization, OrganizationOnboarding
from app.organizations.verification import is_valid_argentina_cuit, normalize_tax_id

API = "/api/v1"
VALID_CUIT = "30-12345678-1"
REAL_VALID_CUIT = "30-65511620-2"


@pytest.fixture(autouse=True)
def isolate_rns_registry(monkeypatch, tmp_path):
    from app.organizations import verification

    monkeypatch.setattr(
        verification.settings,
        "organization_registry_path",
        str(tmp_path / "missing-rns.db"),
    )


def _payload(**overrides):
    payload = {
        "country": "AR",
        "taxIdType": "CUIT",
        "taxId": VALID_CUIT,
        "displayName": "Kakatua",
        "website": "https://kakatua.example",
        "referent": {
            "firstName": "Maria",
            "lastName": "Perez",
            "email": "maria@kakatua.example",
            "jobTitle": "Responsable de Capacitación",
            "phone": "+54 11 5555 5555",
            "actingCapacity": "AUTHORIZED_EMPLOYEE",
            "authorityDeclared": True,
        },
    }
    payload.update(overrides)
    return payload


def test_cuit_normalization_and_check_digit() -> None:
    assert normalize_tax_id(VALID_CUIT) == "30123456781"
    assert is_valid_argentina_cuit(VALID_CUIT)
    assert not is_valid_argentina_cuit("30-12345678-2")
    assert not is_valid_argentina_cuit("123")


def test_p01_config_is_public_and_does_not_reserve_owner_role(client) -> None:
    response = client.get(f"{API}/organization-onboarding/config")
    assert response.status_code == 200
    body = response.json()
    assert body["countries"][0]["code"] == "AR"
    assert body["countries"][0]["taxIdTypes"][0]["code"] == "CUIT"
    assert {row["code"] for row in body["actingCapacities"]} == {
        "LEGAL_REPRESENTATIVE",
        "PROXY",
        "AUTHORIZED_EMPLOYEE",
        "OTHER",
    }
    assert "OWNER" not in {row["code"] for row in body["actingCapacities"]}
    assert body["emailVerificationImplemented"] is False


def test_lookup_rejects_invalid_cuit_without_persisting(client) -> None:
    response = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": "30-12345678-2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "REVIEW_REQUIRED"
    assert body["source"] == "LOCAL_VALIDATION"

    with SessionLocal() as db:
        assert db.scalar(select(OrganizationOnboarding.id)) is None


def test_lookup_uses_explicit_dev_simulation(client) -> None:
    response = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": VALID_CUIT},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "VERIFIED"
    assert body["source"] == "DEV_MOCK"
    assert body["developmentSimulation"] is True
    assert body["company"]["legalName"].startswith("EMPRESA DE PRUEBA")
    assert "DEV" in body["message"]


def test_create_onboarding_does_not_create_organization_yet(client) -> None:
    response = client.post(f"{API}/organization-onboarding", json=_payload())
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["status"] == "COMPANY_VERIFIED"
    assert body["company"]["taxId"] == "30123456781"
    assert body["company"]["displayName"] == "Kakatua"
    assert body["referent"]["email"] == "maria@kakatua.example"
    assert body["referent"]["jobTitleId"] is not None
    assert body["referent"]["jobTitle"] == "Responsable de Capacitación"
    assert body["referent"]["actingCapacity"] == "AUTHORIZED_EMPLOYEE"
    assert body["referent"]["emailVerified"] is False
    assert body["verification"]["developmentSimulation"] is True
    assert body["nextStep"] == "EMAIL_VERIFICATION_PENDING_P02"
    assert len(body["publicId"]) == 36

    with SessionLocal() as db:
        row = db.scalar(
            select(OrganizationOnboarding).where(
                OrganizationOnboarding.public_id == body["publicId"]
            )
        )
        assert row is not None
        assert row.official_data["developmentSimulation"] is True
        assert row.authority_declared is True
        assert db.scalar(select(Organization.id)) is None


def test_create_requires_authority_declaration(client) -> None:
    payload = _payload()
    payload["referent"]["authorityDeclared"] = False

    response = client.post(f"{API}/organization-onboarding", json=payload)
    assert response.status_code == 422
    assert "autorización suficiente" in response.json()["detail"]


def test_create_rejects_invalid_cuit(client) -> None:
    response = client.post(
        f"{API}/organization-onboarding",
        json=_payload(taxId="30-12345678-2"),
    )
    assert response.status_code == 422
    assert "dígito verificador" in response.json()["detail"]

    with SessionLocal() as db:
        assert db.scalar(select(OrganizationOnboarding.id)) is None


def test_without_dev_mock_valid_cuit_stays_pending(client, monkeypatch) -> None:
    from app.organizations import verification

    monkeypatch.setattr(
        verification.settings,
        "organization_verification_mock_enabled",
        False,
    )
    response = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": VALID_CUIT},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "PENDING"
    assert body["source"] == "AR_OFFICIAL_PENDING"
    assert body["developmentSimulation"] is False


def test_lookup_accepts_real_world_valid_cuit_from_manual_test(client) -> None:
    """Regresión del caso detectado durante la primera prueba manual de P01."""
    assert is_valid_argentina_cuit(REAL_VALID_CUIT)

    response = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": REAL_VALID_CUIT},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "VERIFIED"
    assert body["source"] == "DEV_MOCK"
    assert body["taxId"] == "30655116202"
    assert body["developmentSimulation"] is True


def test_dev_purge_removes_incomplete_onboarding_by_cuit(client) -> None:
    created = client.post(f"{API}/organization-onboarding", json=_payload())
    assert created.status_code == 201, created.text

    lookup = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": VALID_CUIT},
    )
    assert lookup.status_code == 200
    assert lookup.json()["platform"]["onboardingInProgress"] is True

    deleted = client.delete(
        f"{API}/organization-onboarding/dev-purge",
        params={"country": "AR", "taxIdType": "CUIT", "taxId": VALID_CUIT},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deletedOnboardings"] == 1

    with SessionLocal() as db:
        assert db.scalar(select(OrganizationOnboarding.id)) is None


def test_dev_purge_never_deletes_provisioned_organization(client) -> None:
    normalized = normalize_tax_id(VALID_CUIT)
    with SessionLocal() as db:
        db.add(
            Organization(
                slug="kakatua-test",
                legal_name="Kakatua Test S.A.",
                display_name="Kakatua Test",
                tax_id=normalized,
                country="AR",
                active=True,
            )
        )
        db.commit()

    response = client.delete(
        f"{API}/organization-onboarding/dev-purge",
        params={"country": "AR", "taxIdType": "CUIT", "taxId": VALID_CUIT},
    )
    assert response.status_code == 409
    assert "no elimina organizaciones reales" in response.json()["detail"]

    with SessionLocal() as db:
        assert db.scalar(select(Organization.id)) is not None


def test_lookup_prefers_official_rns_cache_over_dev_mock(client, monkeypatch, tmp_path) -> None:
    from app.organizations import verification

    registry = tmp_path / "rns_registry.db"
    with sqlite3.connect(registry) as db:
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute(
            """
            CREATE TABLE companies (
                cuit TEXT PRIMARY KEY,
                legal_name TEXT NOT NULL,
                legal_entity_type TEXT,
                contract_date TEXT,
                updated_at TEXT,
                registry_number TEXT,
                fiscal_address TEXT,
                legal_address TEXT,
                fiscal_province TEXT,
                legal_province TEXT,
                activity_code TEXT,
                activity_description TEXT,
                activity_state TEXT,
                activity_order INTEGER,
                activity_rank INTEGER NOT NULL
            )
            """
        )
        db.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("source", "RNS_OPEN_DATA"),
                ("source_updated_at", "2026-09-18"),
            ],
        )
        db.execute(
            """
            INSERT INTO companies(
                cuit, legal_name, legal_entity_type, fiscal_address, legal_address,
                fiscal_province, legal_province, activity_code, activity_description,
                activity_state, activity_order, activity_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalize_tax_id(REAL_VALID_CUIT),
                "KAKATUA S.A.",
                "SOCIEDAD ANONIMA",
                "Av. Siempre Viva 123 · CABA",
                "Av. Siempre Viva 123 · CABA",
                "CIUDAD AUTONOMA BUENOS AIRES",
                "CIUDAD AUTONOMA BUENOS AIRES",
                "854990",
                "SERVICIOS DE ENSEÑANZA",
                "AC",
                1,
                1,
            ),
        )
        db.commit()

    monkeypatch.setattr(
        verification.settings,
        "organization_registry_path",
        str(registry),
    )

    response = client.post(
        f"{API}/organization-onboarding/company/lookup",
        json={"country": "AR", "taxIdType": "CUIT", "taxId": REAL_VALID_CUIT},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "VERIFIED"
    assert body["source"] == "RNS_OPEN_DATA"
    assert body["developmentSimulation"] is False
    assert body["company"]["legalName"] == "KAKATUA S.A."
    assert body["company"]["primaryActivity"] == "SERVICIOS DE ENSEÑANZA"


def test_job_title_catalog_detects_similar_entries(client) -> None:
    seeded = client.get(
        f"{API}/organization-onboarding/job-titles",
        params={"q": "recursos humanos"},
    )
    assert seeded.status_code == 200
    assert any("Recursos Humanos" in row["name"] for row in seeded.json())

    similar = client.post(
        f"{API}/organization-onboarding/job-titles/resolve",
        json={"name": "Responsable Recursos Humanos", "confirmSimilar": False},
    )
    assert similar.status_code == 200
    body = similar.json()
    assert body["status"] == "SIMILAR"
    assert body["item"] is None
    assert body["similar"]

    created = client.post(
        f"{API}/organization-onboarding/job-titles/resolve",
        json={"name": "Responsable Recursos Humanos", "confirmSimilar": True},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "CREATED"
    assert created.json()["item"]["id"]


def test_job_title_catalog_reuses_exact_normalized_title(client) -> None:
    first = client.post(
        f"{API}/organization-onboarding/job-titles/resolve",
        json={"name": "CAPO", "confirmSimilar": False},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "CREATED"

    second = client.post(
        f"{API}/organization-onboarding/job-titles/resolve",
        json={"name": "  capo  ", "confirmSimilar": False},
    )
    assert second.status_code == 200
    assert second.json()["status"] == "EXISTING"
    assert second.json()["item"]["id"] == first.json()["item"]["id"]
