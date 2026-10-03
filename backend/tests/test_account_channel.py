"""Canal por el que cada cuenta recibió su beneficio vigente (portal → Cuentas)."""

from conftest import login
from test_campaigns import API, _create_campaign, _owner_and_services


def _account(client, owner, email: str) -> dict:
    rows = client.get(f"{API}/platform/accounts", params={"q": email}, headers=owner).json()
    return next(row for row in rows if row["email"] == email)


def test_channel_shows_campaign_invitation_and_manual(client) -> None:
    owner, services = _owner_and_services(client)
    campaign = _create_campaign(
        client, owner, services["INDIVIDUAL_PLATFORM"]["id"], name="Primeros 10", days=1, priority=1
    )
    login(client, "camp@example.com")
    assert _account(client, owner, "camp@example.com")["channel"] == {
        "type": "CAMPAIGN",
        "name": campaign["name"],
    }

    client.post(f"{API}/platform/campaigns/{campaign['id']}/pause", headers=owner)
    benefit = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={"name": "Amigo", "serviceId": services["INDIVIDUAL_PLATFORM"]["id"], "durationDays": 1},
    ).json()
    invitation = client.post(
        f"{API}/platform/invitations",
        headers=owner,
        json={"name": "Link amigos", "benefitId": benefit["id"], "recipientMode": "OPEN", "maxRedemptions": 5},
    ).json()
    client.post(
        f"{API}/auth/dev-login",
        json={"email": "link@example.com", "invitationToken": invitation["token"]},
    )
    assert _account(client, owner, "link@example.com")["channel"] == {
        "type": "INVITATION",
        "name": "Link amigos",
    }

    login(client, "manual@example.com")
    target = _account(client, owner, "manual@example.com")
    assert target["channel"] is None
    granted = client.post(
        f"{API}/platform/accounts/{target['id']}/benefit",
        headers=owner,
        json={"benefitId": benefit["id"]},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["channel"] == {"type": "MANUAL", "name": "owner@example.com"}
