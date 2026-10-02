"""T-004 etapa 3: beneficios + invitaciones nominadas/abiertas por link."""

from datetime import datetime, timezone

from conftest import login
from sqlalchemy import select

API = "/api/v1"
OWNER = "owner@example.com"


def _setup(client):
    owner = login(client, OWNER)
    services = {
        row["code"]: row
        for row in client.get(f"{API}/platform/services", headers=owner).json()
    }
    return owner, services


def _benefit(client, owner, service_id: int, name="Regalo 30", days=30):
    response = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={"name": name, "serviceId": service_id, "durationDays": days, "active": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _invite(client, owner, benefit_id: int, **overrides):
    payload = {
        "name": "Invitación de prueba",
        "benefitId": benefit_id,
        "recipientMode": "OPEN",
        "maxRedemptions": 1,
        **overrides,
    }
    response = client.post(f"{API}/platform/invitations", headers=owner, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _login_with_invite(client, email: str, token: str):
    response = client.post(
        f"{API}/auth/dev-login",
        json={
            "email": email,
            "name": "Invitado",
            "invitationToken": token,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def test_benefit_and_invitation_portals_are_owner_only(client) -> None:
    user = login(client, "user@example.com")
    assert client.get(f"{API}/platform/benefits", headers=user).status_code == 403
    assert client.get(f"{API}/platform/invitations", headers=user).status_code == 403


def test_campaign_and_invitation_share_one_benefit_definition(client) -> None:
    owner, services = _setup(client)
    benefit = _benefit(client, owner, services["INDIVIDUAL_PLATFORM"]["id"], days=30)

    campaign = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": "Promo",
            "benefitId": benefit["id"],
            "trigger": "FIRST_LOGIN",
            "rules": [],
            "priority": 10,
            "stackable": False,
            "notification": "NONE",
        },
    )
    assert campaign.status_code == 201, campaign.text
    invitation = _invite(client, owner, benefit["id"])

    updated = client.put(
        f"{API}/platform/benefits/{benefit['id']}",
        headers=owner,
        json={
            "name": "Regalo 45",
            "serviceId": services["INDIVIDUAL_PLATFORM"]["id"],
            "durationDays": 45,
            "active": True,
        },
    )
    assert updated.status_code == 200, updated.text

    campaigns = client.get(f"{API}/platform/campaigns", headers=owner).json()
    same_campaign = next(row for row in campaigns if row["id"] == campaign.json()["id"])
    invitations = client.get(f"{API}/platform/invitations", headers=owner).json()
    same_invitation = next(row for row in invitations if row["id"] == invitation["id"])
    assert same_campaign["grantDays"] == 45
    assert same_campaign["benefitName"] == "Regalo 45"
    assert same_invitation["durationDays"] == 45
    assert same_invitation["benefitName"] == "Regalo 45"


def test_named_invitation_matches_email_and_runs_before_welcome(client) -> None:
    from app.accounts.models import Account
    from app.campaigns.models import CampaignGrant
    from app.db import SessionLocal

    owner, services = _setup(client)
    welcome = next(
        row for row in client.get(f"{API}/platform/campaigns", headers=owner).json()
        if row["code"] == "WELCOME_PLATFORM"
    )
    assert client.post(
        f"{API}/platform/campaigns/{welcome['id']}/activate", headers=owner
    ).status_code == 200

    benefit = _benefit(client, owner, services["INDIVIDUAL_PLATFORM"]["id"], days=30)
    invitation = _invite(
        client,
        owner,
        benefit["id"],
        name="Para amiga",
        recipientMode="NAMED",
        email="friend@example.com",
        firstName="Friend",
        lastName="Example",
        maxRedemptions=999,
    )
    assert invitation["maxRedemptions"] == 1
    assert invitation["emailStatus"] == "PENDING"

    wrong = _login_with_invite(client, "other@example.com", invitation["token"])
    wrong_me = client.get(f"{API}/me", headers=wrong).json()
    assert wrong_me["service"]["origin"] == "CAMPAIGN"
    rejected = client.post(
        f"{API}/invitations/{invitation['token']}/redeem", headers=wrong
    )
    assert rejected.status_code == 409
    assert "otra cuenta" in rejected.json()["detail"]

    friend = _login_with_invite(client, "friend@example.com", invitation["token"])
    friend_me = client.get(f"{API}/me", headers=friend).json()
    assert friend_me["service"]["origin"] == "INVITATION"
    assert friend_me["service"]["source"] == "PLATFORM"

    repeated = client.post(
        f"{API}/invitations/{invitation['token']}/redeem", headers=friend
    )
    assert repeated.status_code == 200
    assert repeated.json()["alreadyRedeemed"] is True

    with SessionLocal() as db:
        friend_account = db.scalar(select(Account).where(Account.email == "friend@example.com"))
        assert friend_account is not None
        assert db.scalar(
            select(CampaignGrant.id).where(
                CampaignGrant.campaign_id == welcome["id"],
                CampaignGrant.account_id == friend_account.id,
            )
        ) is None


def test_open_link_one_use_is_transferable_and_exhausts_after_first_account(client) -> None:
    owner, services = _setup(client)
    benefit = _benefit(client, owner, services["INDIVIDUAL_PLATFORM"]["id"], days=7)
    invitation = _invite(client, owner, benefit["id"], maxRedemptions=1)

    first = _login_with_invite(client, "first-open@example.com", invitation["token"])
    assert client.get(f"{API}/me", headers=first).json()["service"]["origin"] == "INVITATION"

    second = _login_with_invite(client, "second-open@example.com", invitation["token"])
    assert client.get(f"{API}/me", headers=second).json()["service"]["origin"] is None

    preview = client.get(f"{API}/invitations/{invitation['token']}")
    assert preview.status_code == 200
    assert preview.json()["status"] == "EXHAUSTED"
    assert preview.json()["remaining"] == 0


def test_open_link_cupo_counts_distinct_accounts_not_retries(client) -> None:
    owner, services = _setup(client)
    benefit = _benefit(client, owner, services["INDIVIDUAL_PLATFORM"]["id"], days=5)
    invitation = _invite(client, owner, benefit["id"], maxRedemptions=2)

    first = _login_with_invite(client, "one@example.com", invitation["token"])
    again = client.post(f"{API}/invitations/{invitation['token']}/redeem", headers=first)
    assert again.status_code == 200
    assert again.json()["alreadyRedeemed"] is True

    _login_with_invite(client, "two@example.com", invitation["token"])
    third = _login_with_invite(client, "three@example.com", invitation["token"])
    assert client.get(f"{API}/me", headers=third).json()["service"]["origin"] is None

    row = next(
        row for row in client.get(f"{API}/platform/invitations", headers=owner).json()
        if row["id"] == invitation["id"]
    )
    assert row["redemptions"] == 2
    assert row["status"] == "EXHAUSTED"


def test_existing_same_service_adds_days_but_different_service_does_not_replace(client) -> None:
    owner, services = _setup(client)
    user = login(client, "existing@example.com")
    account = next(
        row for row in client.get(f"{API}/platform/accounts", headers=owner).json()
        if row["email"] == "existing@example.com"
    )
    base_benefit = _benefit(
        client,
        owner,
        services["INDIVIDUAL_PLATFORM"]["id"],
        name="Base 10",
        days=10,
    )
    granted = client.post(
        f"{API}/platform/accounts/{account['id']}/benefit",
        headers=owner,
        json={"benefitId": base_benefit["id"]},
    )
    assert granted.status_code == 200
    before = datetime.fromisoformat(granted.json()["service"]["expiresAt"].replace("Z", "+00:00"))

    same = _benefit(client, owner, services["INDIVIDUAL_PLATFORM"]["id"], name="Suma 5", days=5)
    same_invite = _invite(client, owner, same["id"])
    redeemed = client.post(f"{API}/invitations/{same_invite['token']}/redeem", headers=user)
    assert redeemed.status_code == 200, redeemed.text
    after_raw = client.get(f"{API}/me", headers=user).json()["service"]["expiresAt"]
    after = datetime.fromisoformat(after_raw.replace("Z", "+00:00"))
    assert 4.9 <= (after - before).total_seconds() / 86400 <= 5.1

    hybrid = _benefit(client, owner, services["INDIVIDUAL_HYBRID"]["id"], name="Híbrido", days=5)
    hybrid_invite = _invite(client, owner, hybrid["id"])
    conflict = client.post(f"{API}/invitations/{hybrid_invite['token']}/redeem", headers=user)
    assert conflict.status_code == 409
    assert "otro servicio" in conflict.json()["detail"]

    row = next(
        row for row in client.get(f"{API}/platform/invitations", headers=owner).json()
        if row["id"] == hybrid_invite["id"]
    )
    assert row["redemptions"] == 0
    assert row["remaining"] == 1
    assert client.get(f"{API}/me", headers=user).json()["service"]["source"] == "PLATFORM"


def test_invitation_engine_exception_never_blocks_login(client, monkeypatch) -> None:
    import app.invitations.service as invitation_service

    def explode(*args, **kwargs):
        raise RuntimeError("invitation-engine-boom")

    monkeypatch.setattr(invitation_service, "redeem_invitation", explode)
    response = client.post(
        f"{API}/auth/dev-login",
        json={
            "email": "invite-failure@example.com",
            "name": "Invitado",
            "invitationToken": "x" * 32,
        },
    )
    assert response.status_code == 200, response.text
