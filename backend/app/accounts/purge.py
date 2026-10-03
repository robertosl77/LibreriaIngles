"""Borrado físico de una cuenta de prueba.

Herramienta estrictamente de desarrollo. Elimina la cuenta y su información personal/educativa
para poder repetir altas y campañas desde cero. No elimina datos globales de plataforma.
"""

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.ai.models import (
    AICredentialAuditEvent,
    AIConnection,
    AIConnectionOwnerType,
    AIUsageEvent,
)
from app.benefits.models import Benefit
from app.campaigns.models import Campaign, CampaignGrant
from app.exams.models import LevelCertificate
from app.learning.models import (
    AIEvaluationCache,
    Attempt,
    ClassSession,
    DraftAnswer,
    Exercise,
    StudySkillProgress,
)
from app.invitations.models import Invitation, InvitationRedemption
from app.invitations.service import refresh_status
from app.memberships.models import Membership
from app.study_profiles.models import AccountLinkVerification, AccountStudyProfile, StudyProfile
from app.subscriptions.models import Subscription


def _ids(db: Session, statement) -> list[int]:
    return [int(value) for value in db.scalars(statement).all()]


def purge_account_completely(db: Session, account: Account) -> None:
    """Elimina en una transacción todos los datos propios de la cuenta."""
    account_id = account.id
    email = account.email

    profile_ids = _ids(
        db,
        select(AccountStudyProfile.study_profile_id).where(
            AccountStudyProfile.account_id == account_id
        ),
    )
    exclusive_profile_ids: list[int] = []
    for profile_id in profile_ids:
        other_links = db.scalar(
            select(func.count(AccountStudyProfile.account_id)).where(
                AccountStudyProfile.study_profile_id == profile_id,
                AccountStudyProfile.account_id != account_id,
            )
        ) or 0
        if int(other_links) == 0:
            exclusive_profile_ids.append(profile_id)

    membership_ids = _ids(
        db, select(Membership.id).where(Membership.account_id == account_id)
    )
    own_connection_ids = _ids(
        db,
        select(AIConnection.id).where(
            AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT,
            AIConnection.owner_id == account_id,
        ),
    )

    session_filters = [ClassSession.account_id == account_id]
    if exclusive_profile_ids:
        session_filters.append(ClassSession.study_profile_id.in_(exclusive_profile_ids))
    if membership_ids:
        session_filters.append(ClassSession.membership_id.in_(membership_ids))
    session_ids = _ids(db, select(ClassSession.id).where(or_(*session_filters)))

    exercise_filters = []
    if session_ids:
        exercise_filters.append(Exercise.class_session_id.in_(session_ids))
    if exclusive_profile_ids:
        exercise_filters.append(Exercise.study_profile_id.in_(exclusive_profile_ids))
    if membership_ids:
        exercise_filters.append(Exercise.membership_id.in_(membership_ids))
    exercise_ids = (
        _ids(db, select(Exercise.id).where(or_(*exercise_filters)))
        if exercise_filters
        else []
    )

    if exercise_ids:
        db.execute(delete(AIEvaluationCache).where(AIEvaluationCache.exercise_id.in_(exercise_ids)))
        db.execute(delete(DraftAnswer).where(DraftAnswer.exercise_id.in_(exercise_ids)))
        db.execute(delete(Attempt).where(Attempt.exercise_id.in_(exercise_ids)))

    draft_filters = [DraftAnswer.account_id == account_id]
    attempt_filters = [Attempt.account_id == account_id]
    if session_ids:
        draft_filters.append(DraftAnswer.class_session_id.in_(session_ids))
    if exclusive_profile_ids:
        attempt_filters.append(Attempt.study_profile_id.in_(exclusive_profile_ids))
    if membership_ids:
        attempt_filters.append(Attempt.membership_id.in_(membership_ids))
    db.execute(delete(DraftAnswer).where(or_(*draft_filters)))
    db.execute(delete(Attempt).where(or_(*attempt_filters)))

    certificate_filters = [LevelCertificate.account_id == account_id]
    if exclusive_profile_ids:
        certificate_filters.append(LevelCertificate.study_profile_id.in_(exclusive_profile_ids))
    if session_ids:
        certificate_filters.append(LevelCertificate.exam_session_id.in_(session_ids))
    db.execute(delete(LevelCertificate).where(or_(*certificate_filters)))

    progress_filters = []
    if exclusive_profile_ids:
        progress_filters.append(StudySkillProgress.study_profile_id.in_(exclusive_profile_ids))
    if membership_ids:
        progress_filters.append(StudySkillProgress.membership_id.in_(membership_ids))
    if progress_filters:
        db.execute(delete(StudySkillProgress).where(or_(*progress_filters)))

    if exercise_ids:
        db.execute(delete(Exercise).where(Exercise.id.in_(exercise_ids)))
    if session_ids:
        db.execute(delete(ClassSession).where(ClassSession.id.in_(session_ids)))

    usage_filters = [AIUsageEvent.account_id == account_id]
    audit_filters = [AICredentialAuditEvent.account_id == account_id]
    if own_connection_ids:
        usage_filters.append(AIUsageEvent.connection_id.in_(own_connection_ids))
        audit_filters.append(AICredentialAuditEvent.connection_id.in_(own_connection_ids))
        db.execute(
            update(ClassSession)
            .where(ClassSession.generated_by_connection_id.in_(own_connection_ids))
            .values(generated_by_connection_id=None)
        )
    db.execute(delete(AIUsageEvent).where(or_(*usage_filters)))
    db.execute(delete(AICredentialAuditEvent).where(or_(*audit_filters)))
    if own_connection_ids:
        db.execute(delete(AIConnection).where(AIConnection.id.in_(own_connection_ids)))

    db.execute(delete(CampaignGrant).where(CampaignGrant.account_id == account_id))

    redeemed_invitation_ids = _ids(
        db,
        select(InvitationRedemption.invitation_id).where(
            InvitationRedemption.account_id == account_id
        ),
    )
    db.execute(
        delete(InvitationRedemption).where(InvitationRedemption.account_id == account_id)
    )
    for invitation_id in redeemed_invitation_ids:
        invitation = db.get(Invitation, invitation_id)
        if invitation is not None:
            refresh_status(db, invitation)

    db.execute(delete(Subscription).where(Subscription.account_id == account_id))
    db.execute(
        update(Subscription)
        .where(Subscription.granted_by_account_id == account_id)
        .values(granted_by_account_id=None)
    )
    db.execute(
        update(Campaign)
        .where(Campaign.created_by_account_id == account_id)
        .values(created_by_account_id=None)
    )
    db.execute(
        update(Benefit)
        .where(Benefit.created_by_account_id == account_id)
        .values(created_by_account_id=None)
    )
    db.execute(
        update(Invitation)
        .where(Invitation.created_by_account_id == account_id)
        .values(created_by_account_id=None)
    )

    db.execute(
        update(Membership)
        .where(Membership.revoked_by_account_id == account_id)
        .values(revoked_by_account_id=None)
    )
    if membership_ids:
        db.execute(delete(Membership).where(Membership.id.in_(membership_ids)))
    link_filters = [AccountLinkVerification.account_id == account_id]
    if exclusive_profile_ids:
        link_filters.append(AccountLinkVerification.study_profile_id.in_(exclusive_profile_ids))
    db.execute(delete(AccountLinkVerification).where(or_(*link_filters)))
    db.execute(delete(AccountStudyProfile).where(AccountStudyProfile.account_id == account_id))
    if exclusive_profile_ids:
        db.execute(delete(StudyProfile).where(StudyProfile.id.in_(exclusive_profile_ids)))

    db.execute(delete(Account).where(Account.id == account_id))
