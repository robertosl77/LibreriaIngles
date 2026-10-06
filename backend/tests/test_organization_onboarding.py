from sqlalchemy import select

from app.db import SessionLocal
from app.organizations.models import Organization, OrganizationOnboarding
from app.organizations.verification import is_valid_argentina_cuit, normalize_tax_id

API = "/api/v1"
VALID_CUIT = "30-12345678-1"


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
