from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memberships.models import Membership, MembershipRole, MembershipStatus


def can_admin_access_activity(
    session: Session,
    *,
    admin_account_id: int,
    organization_id: int,
    activity_organization_id: int | None,
) -> bool:
    """Return whether an organization ADMIN may see a piece of study activity."""
    if activity_organization_id is None:
        return False

    if activity_organization_id != organization_id:
        return False

    membership_id = session.scalar(
        select(Membership.id).where(
            Membership.account_id == admin_account_id,
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.ADMIN,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    return membership_id is not None
