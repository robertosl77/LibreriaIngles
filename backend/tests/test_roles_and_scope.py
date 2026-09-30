from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.accounts.models import Account, AccountStatus, AccountType, AuthMethod, PlatformRole
from app.db import Base
from app.memberships.access import can_admin_access_activity
from app.memberships.models import Membership, MembershipRole, MembershipStatus
from app.organizations.models import Organization


def test_platform_owner_is_not_a_membership_role() -> None:
    assert PlatformRole.PLATFORM_OWNER.value == "PLATFORM_OWNER"
    assert {role.value for role in MembershipRole} == {"ADMIN", "STUDENT"}


def test_admin_scope_excludes_other_org_and_personal_activity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        admin = Account(
            email="admin-a@example.com",
            account_type=AccountType.CORPORATE,
            auth_method=AuthMethod.LOCAL,
            status=AccountStatus.ACTIVE,
        )
        org_a = Organization(slug="a", legal_name="A", display_name="A")
        org_b = Organization(slug="b", legal_name="B", display_name="B")
        session.add_all([admin, org_a, org_b])
        session.flush()

        session.add(
            Membership(
                account_id=admin.id,
                organization_id=org_a.id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
            )
        )
        session.commit()

        assert can_admin_access_activity(
            session,
            admin_account_id=admin.id,
            organization_id=org_a.id,
            activity_organization_id=org_a.id,
        )
        assert not can_admin_access_activity(
            session,
            admin_account_id=admin.id,
            organization_id=org_a.id,
            activity_organization_id=org_b.id,
        )
        assert not can_admin_access_activity(
            session,
            admin_account_id=admin.id,
            organization_id=org_a.id,
            activity_organization_id=None,
        )
