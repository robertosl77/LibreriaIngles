import pytest

from app.db import SessionLocal
from app.verifications.models import VerificationPurpose
from app.verifications.service import ChallengeRateLimited, create_challenge


def test_verification_challenge_limits_same_destination_across_contexts(
    client,
    monkeypatch,
) -> None:
    from app.verifications import service

    monkeypatch.setattr(service.settings, "verification_resend_cooldown_seconds", 0)
    monkeypatch.setattr(service.settings, "verification_max_sends_per_hour", 10)
    monkeypatch.setattr(
        service.settings,
        "verification_max_sends_per_destination_per_hour",
        1,
    )

    with SessionLocal() as db:
        create_challenge(
            db,
            purpose=VerificationPurpose.ORGANIZATION_ONBOARDING_EMAIL,
            context_type="ORGANIZATION_ONBOARDING",
            context_id="onboarding-a",
            destination="victima@example.com",
        )
        db.commit()

        with pytest.raises(ChallengeRateLimited):
            create_challenge(
                db,
                purpose=VerificationPurpose.ORGANIZATION_ONBOARDING_EMAIL,
                context_type="ORGANIZATION_ONBOARDING",
                context_id="onboarding-b",
                destination="VICTIMA@example.com",
            )


def test_new_p02_models_are_registered_in_sqlalchemy_metadata(client) -> None:
    from app.db import Base

    assert "verification_challenges" in Base.metadata.tables
    assert "notification_cases" in Base.metadata.tables
