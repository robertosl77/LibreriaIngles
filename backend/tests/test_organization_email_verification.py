from datetime import timedelta

from sqlalchemy import select

from app.accounts.models import Account, AccountStatus, AccountType, AuthMethod
from app.db import SessionLocal
from app.organizations.models import Organization, OrganizationOnboarding, OrganizationOnboardingStatus, utcnow
from app.verifications.models import VerificationChallenge

API = "/api/v1"
VALID_CUIT = "30-12345678-1"


def _payload(email: str = "maria@kakatua.example") -> dict:
    return {
        "country": "AR",
        "taxIdType": "CUIT",
        "taxId": VALID_CUIT,
        "displayName": "Kakatua",
        "website": "https://kakatua.example",
        "referent": {
            "firstName": "Maria",
            "lastName": "Perez",
            "email": email,
            "jobTitle": "Responsable de Capacitación",
            "phone": "+54 11 5555 5555",
            "actingCapacity": "AUTHORIZED_EMPLOYEE",
            "authorityDeclared": True,
        },
    }


def _create(client, email: str = "maria@kakatua.example") -> dict:
    response = client.post(f"{API}/organization-onboarding", json=_payload(email))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["continuationToken"]
    return body


def _headers(created: dict) -> dict[str, str]:
    return {"X-Onboarding-Token": created["continuationToken"]}


def _start(client, created: dict) -> dict:
    response = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/start",
        headers=_headers(created),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_p02_start_uses_hashed_challenge_and_dev_capture(client) -> None:
    created = _create(client)
    started = _start(client, created)

    assert started["developmentCode"].isdigit()
    assert len(started["developmentCode"]) == 6
    assert started["resendAvailableInSeconds"] == 60
    assert started["deliveryProvider"] == "DEV"

    with SessionLocal() as db:
        onboarding = db.scalar(
            select(OrganizationOnboarding).where(
                OrganizationOnboarding.public_id == created["publicId"]
            )
        )
        challenge = db.scalar(
            select(VerificationChallenge).where(
                VerificationChallenge.public_id == started["challengeId"]
            )
        )
        assert onboarding is not None
        assert onboarding.status == OrganizationOnboardingStatus.EMAIL_PENDING
        assert onboarding.continuation_token_hash
        assert onboarding.continuation_token_hash != created["continuationToken"]
        assert challenge is not None
        assert challenge.code_digest
        assert started["developmentCode"] not in challenge.code_digest


def test_p02_requires_continuation_token(client) -> None:
    created = _create(client)
    response = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/start"
    )
    assert response.status_code == 401


def test_p02_correct_code_verifies_email_without_provisioning(client) -> None:
    created = _create(client)
    started = _start(client, created)

    response = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": started["developmentCode"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verified"] is True
    assert response.json()["status"] == "EMAIL_VERIFIED"

    with SessionLocal() as db:
        onboarding = db.scalar(select(OrganizationOnboarding))
        challenge = db.scalar(select(VerificationChallenge))
        assert onboarding.status == OrganizationOnboardingStatus.EMAIL_VERIFIED
        assert onboarding.contact_email_verified_at is not None
        assert challenge.consumed_at is not None
        assert challenge.code_digest is None
        assert db.scalar(select(Organization.id)) is None


def test_p02_three_wrong_attempts_exhaust_challenge(client) -> None:
    created = _create(client)
    started = _start(client, created)
    wrong = "000000" if started["developmentCode"] != "000000" else "000001"

    for _ in range(2):
        response = client.post(
            f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
            headers=_headers(created),
            json={"code": wrong},
        )
        assert response.status_code == 422
        assert "no es válido" in response.json()["detail"]

    third = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": wrong},
    )
    assert third.status_code == 422
    assert "ya no puede utilizarse" in third.json()["detail"]

    correct_after_exhaustion = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": started["developmentCode"]},
    )
    assert correct_after_exhaustion.status_code == 422


def test_p02_resend_invalidates_previous_code(client, monkeypatch) -> None:
    from app.verifications import service

    monkeypatch.setattr(service.settings, "verification_resend_cooldown_seconds", 0)
    created = _create(client)
    first = _start(client, created)
    second_response = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/resend",
        headers=_headers(created),
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["challengeId"] != first["challengeId"]

    old = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": first["developmentCode"]},
    )
    assert old.status_code == 422

    new = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": second["developmentCode"]},
    )
    assert new.status_code == 200


def test_p02_expired_code_is_rejected(client) -> None:
    created = _create(client)
    started = _start(client, created)

    with SessionLocal() as db:
        challenge = db.scalar(
            select(VerificationChallenge).where(
                VerificationChallenge.public_id == started["challengeId"]
            )
        )
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    response = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": started["developmentCode"]},
    )
    assert response.status_code == 422
    assert "venció" in response.json()["detail"]


def test_p02_limits_sends_per_hour(client, monkeypatch) -> None:
    from app.verifications import service

    monkeypatch.setattr(service.settings, "verification_resend_cooldown_seconds", 0)
    monkeypatch.setattr(service.settings, "verification_max_sends_per_hour", 2)
    created = _create(client)
    _start(client, created)

    second = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/resend",
        headers=_headers(created),
    )
    assert second.status_code == 200

    third = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/resend",
        headers=_headers(created),
    )
    assert third.status_code == 429


def test_p02_email_correction_invalidates_old_challenge(client, monkeypatch) -> None:
    from app.verifications import service

    monkeypatch.setattr(service.settings, "verification_resend_cooldown_seconds", 0)
    created = _create(client)
    first = _start(client, created)

    changed = client.patch(
        f"{API}/organization-onboarding/{created['publicId']}/referent-email",
        headers=_headers(created),
        json={"email": "maria2@kakatua.example"},
    )
    assert changed.status_code == 200
    assert changed.json()["email"] == "maria2@kakatua.example"
    assert changed.json()["emailVerified"] is False

    second = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/start",
        headers=_headers(created),
    )
    assert second.status_code == 200

    old = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": first["developmentCode"]},
    )
    assert old.status_code == 422


def test_p02_does_not_modify_preexisting_account(client) -> None:
    email = "maria@kakatua.example"
    with SessionLocal() as db:
        db.add(
            Account(
                email=email,
                display_name="Maria existente",
                account_type=AccountType.PERSONAL,
                auth_method=AuthMethod.LOCAL,
                status=AccountStatus.ACTIVE,
            )
        )
        db.commit()

    created = _create(client, email)
    started = _start(client, created)
    verified = client.post(
        f"{API}/organization-onboarding/{created['publicId']}/email-verification/verify",
        headers=_headers(created),
        json={"code": started["developmentCode"]},
    )
    assert verified.status_code == 200

    with SessionLocal() as db:
        accounts = db.scalars(select(Account).where(Account.email == email)).all()
        assert len(accounts) == 1
        assert accounts[0].display_name == "Maria existente"
        assert accounts[0].status == AccountStatus.ACTIVE
