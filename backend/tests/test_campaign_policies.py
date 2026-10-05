"""T-141: políticas globales reutilizables de Campaigns."""

from conftest import login

API = "/api/v1"
OWNER = "owner@example.com"


def _owner_and_service(client):
    owner = login(client, OWNER)
    response = client.get(f"{API}/platform/services", headers=owner)
    assert response.status_code == 200, response.text
    services = {row["code"]: row for row in response.json()}
    return owner, services["INDIVIDUAL_PLATFORM"]["id"]


def _benefit(client, owner, service_id: int, name: str, days: int = 3) -> dict:
    response = client.post(
        f"{API}/platform/benefits",
        headers=owner,
        json={"name": name, "serviceId": service_id, "durationDays": days, "active": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _campaign(
    client,
    owner,
    *,
    name: str,
    benefit_id: int,
    trigger: str,
    priority: int,
    stackable: bool = False,
) -> dict:
    response = client.post(
        f"{API}/platform/campaigns",
        headers=owner,
        json={
            "name": name,
            "benefitId": benefit_id,
            "trigger": trigger,
            "rules": [{"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"}],
            "priority": priority,
            "stackable": stackable,
            "notification": "NONE",
        },
    )
    assert response.status_code == 201, response.text
    campaign = response.json()
    activated = client.post(
        f"{API}/platform/campaigns/{campaign['id']}/activate", headers=owner
    )
    assert activated.status_code == 200, activated.text
    return activated.json()


def _policy(
    client,
    owner,
    *,
    name: str,
    field: str = "CAMPAIGN_GRANTS_COUNT",
    days: int = 30,
    value: int = 1,
    campaign_ids: list[int] | None = None,
    enabled: bool = True,
) -> dict:
    applies_to = (
        {"mode": "CAMPAIGNS", "campaignIds": campaign_ids}
        if campaign_ids
        else {"mode": "ALL", "campaignIds": []}
    )
    response = client.post(
        f"{API}/platform/campaigns/policies",
        headers=owner,
        json={
            "name": name,
            "kind": "SUPPRESSION",
            "enabled": enabled,
            "appliesTo": applies_to,
            "rules": [
                {
                    "field": field,
                    "operator": "GTE",
                    "value": value,
                    "windowDays": days,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _campaign_by_id(client, owner, campaign_id: int) -> dict:
    rows = client.get(f"{API}/platform/campaigns", headers=owner).json()
    return next(row for row in rows if row["id"] == campaign_id)


def test_policy_portal_is_owner_only_and_exclusion_is_reserved(client) -> None:
    user = login(client, "policy-user@example.com")
    assert client.get(f"{API}/platform/campaigns/policies", headers=user).status_code == 403

    owner, _ = _owner_and_service(client)
    capabilities = client.get(
        f"{API}/platform/campaigns/policies/capabilities", headers=owner
    )
    assert capabilities.status_code == 200, capabilities.text
    kinds = {item["key"]: item for item in capabilities.json()["kinds"]}
    assert kinds["SUPPRESSION"]["available"] is True
    assert kinds["EXCLUSION"]["available"] is False

    invalid = client.post(
        f"{API}/platform/campaigns/policies",
        headers=owner,
        json={
            "name": "Exclusión prematura",
            "kind": "EXCLUSION",
            "enabled": True,
            "appliesTo": {"mode": "ALL", "campaignIds": []},
            "rules": [
                {
                    "field": "CAMPAIGN_GRANTS_COUNT",
                    "operator": "GTE",
                    "value": 1,
                    "windowDays": 30,
                }
            ],
        },
    )
    assert invalid.status_code == 422


def test_global_suppression_blocks_campaign_after_recent_grant_and_audits(client) -> None:
    owner, service_id = _owner_and_service(client)
    first_benefit = _benefit(client, owner, service_id, "Alta actividad", 3)
    first = _campaign(
        client,
        owner,
        name="Alta actividad",
        benefit_id=first_benefit["id"],
        trigger="FIRST_LOGIN",
        priority=1,
    )

    login(client, "suppression@example.com")
    assert _campaign_by_id(client, owner, first["id"])["recipients"] == 1

    _policy(client, owner, name="Enfriamiento 30 días", days=30)

    anniversary_benefit = _benefit(client, owner, service_id, "Aniversario", 5)
    anniversary = _campaign(
        client,
        owner,
        name="Aniversario",
        benefit_id=anniversary_benefit["id"],
        trigger="LOGIN",
        priority=2,
    )

    login(client, "suppression@example.com")
    assert _campaign_by_id(client, owner, anniversary["id"])["recipients"] == 0

    blocks = client.get(f"{API}/platform/campaigns/policies/blocks", headers=owner)
    assert blocks.status_code == 200, blocks.text
    row = blocks.json()[0]
    assert row["campaignId"] == anniversary["id"]
    assert row["policy"] == "Enfriamiento 30 días"
    assert row["account"] == "suppression@example.com"
    assert "últimos 30 días" in row["reason"]


def test_disabled_suppression_does_not_block(client) -> None:
    owner, service_id = _owner_and_service(client)
    benefit = _benefit(client, owner, service_id, "Histórico", 2)
    _campaign(
        client,
        owner,
        name="Histórico",
        benefit_id=benefit["id"],
        trigger="FIRST_LOGIN",
        priority=1,
    )
    login(client, "disabled-policy@example.com")

    policy = _policy(client, owner, name="Pausa global", enabled=False)
    candidate_benefit = _benefit(client, owner, service_id, "Nueva campaña", 2)
    candidate = _campaign(
        client,
        owner,
        name="Nueva campaña",
        benefit_id=candidate_benefit["id"],
        trigger="LOGIN",
        priority=2,
    )

    login(client, "disabled-policy@example.com")
    assert _campaign_by_id(client, owner, candidate["id"])["recipients"] == 1
    assert policy["enabled"] is False


def test_same_benefit_policy_blocks_only_same_benefit(client) -> None:
    owner, service_id = _owner_and_service(client)
    shared = _benefit(client, owner, service_id, "Beneficio compartido", 3)
    _campaign(
        client,
        owner,
        name="Campaña histórica",
        benefit_id=shared["id"],
        trigger="FIRST_LOGIN",
        priority=1,
    )
    login(client, "same-benefit@example.com")

    _policy(
        client,
        owner,
        name="No repetir Benefit 90 días",
        field="SAME_BENEFIT_GRANTS_COUNT",
        days=90,
    )

    same = _campaign(
        client,
        owner,
        name="Mismo Benefit",
        benefit_id=shared["id"],
        trigger="LOGIN",
        priority=2,
    )
    other_benefit = _benefit(client, owner, service_id, "Benefit distinto", 4)
    other = _campaign(
        client,
        owner,
        name="Otro Benefit",
        benefit_id=other_benefit["id"],
        trigger="LOGIN",
        priority=3,
    )

    login(client, "same-benefit@example.com")
    assert _campaign_by_id(client, owner, same["id"])["recipients"] == 0
    assert _campaign_by_id(client, owner, other["id"])["recipients"] == 1


def test_suppressed_high_priority_campaign_does_not_block_lower_nonstackable(client) -> None:
    """Story time crítico: A se suprime antes de ocupar lugar en convivencia."""
    owner, service_id = _owner_and_service(client)

    historical_benefit = _benefit(client, owner, service_id, "Histórico", 1)
    _campaign(
        client,
        owner,
        name="Histórico reciente",
        benefit_id=historical_benefit["id"],
        trigger="FIRST_LOGIN",
        priority=1,
    )
    login(client, "pipeline@example.com")

    benefit_a = _benefit(client, owner, service_id, "Benefit A", 2)
    campaign_a = _campaign(
        client,
        owner,
        name="A prioritaria",
        benefit_id=benefit_a["id"],
        trigger="LOGIN",
        priority=10,
        stackable=False,
    )
    benefit_b = _benefit(client, owner, service_id, "Benefit B", 2)
    campaign_b = _campaign(
        client,
        owner,
        name="B secundaria",
        benefit_id=benefit_b["id"],
        trigger="LOGIN",
        priority=20,
        stackable=False,
    )

    _policy(
        client,
        owner,
        name="Suprimir solo A si hubo campaña reciente",
        campaign_ids=[campaign_a["id"]],
        days=30,
    )

    login(client, "pipeline@example.com")

    assert _campaign_by_id(client, owner, campaign_a["id"])["recipients"] == 0
    assert _campaign_by_id(client, owner, campaign_b["id"])["recipients"] == 1


def test_policy_can_be_disabled_reenabled_and_soft_deleted(client) -> None:
    owner, _ = _owner_and_service(client)
    policy = _policy(client, owner, name="Editable")

    disabled = client.post(
        f"{API}/platform/campaigns/policies/{policy['id']}/disable", headers=owner
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = client.post(
        f"{API}/platform/campaigns/policies/{policy['id']}/enable", headers=owner
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    deleted = client.delete(
        f"{API}/platform/campaigns/policies/{policy['id']}", headers=owner
    )
    assert deleted.status_code == 204
    listed = client.get(f"{API}/platform/campaigns/policies", headers=owner)
    assert all(row["id"] != policy["id"] for row in listed.json())
