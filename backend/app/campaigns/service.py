"""Motor de campañas de T-004, etapa 2.

La campaña define CUÁNDO/A QUIÉN; el beneficio reusable define QUÉ servicio/duración se otorga.
T-059 agregará el scheduler para CampaignTrigger.SCHEDULED sin cambiar este contrato.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountStatus, AccountType, PlatformRole
from app.ai.models import AIConnection, AIConnectionOwnerType, AIUsageEvent
from app.benefits.models import Benefit
from app.benefits.service import (
    BenefitApplication,
    apply_service_benefit,
    seed_benefits,
    seed_fidelity_lab_benefits,
)
from app.campaigns.models import (
    Campaign,
    CampaignAction,
    CampaignGrant,
    CampaignSeedMarker,
    CampaignNotification,
    CampaignStatus,
    CampaignTrigger,
)
from app.core.config import settings
from app.learning.models import (
    Attempt,
    ClassSession,
    ClassSessionStatus,
    Exercise,
    PresentationMode,
    ResponseMode,
    SessionKind,
    StudySkillProgress,
)
from app.memberships.models import Membership, MembershipStatus
from app.progress.service import ability_progress
from app.study_profiles.models import (
    AccountStudyProfile,
    AccountStudyProfileStatus,
    StudyProfile,
    StudyProfileStatus,
)
from app.subscriptions.models import Subscription, SubscriptionOrigin, SubscriptionStatus
from app.subscriptions.service import effective_service

WELCOME_CODE = "WELCOME_PLATFORM"
WELCOME_BENEFIT_CODE = "WELCOME_PLATFORM_3D"

# Laboratorio visible solo en local/dev. Todos los casos nacen en DRAFT y son idempotentes.
FIDELITY_LAB_CAMPAIGNS = (
    {
        "code": "LAB_FID_01_6M_AVG5",
        "name": "LAB 01 · Permanencia 6 meses + promedio alto",
        "benefit": "LAB_FID_6M_AVG5",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 180},
            {"field": "AVERAGE_CLASSES_PER_DAY", "operator": "GTE", "value": 5, "windowDays": 30},
        ],
        "message": "Tu permanencia y constancia merecen un reconocimiento.",
    },
    {
        "code": "LAB_FID_02_ANNIVERSARY",
        "name": "LAB 02 · Aniversario de 1 año",
        "benefit": "LAB_FID_1Y",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 365},
        ],
        "message": "Gracias por acompañarnos durante todo un año.",
    },
    {
        "code": "LAB_FID_03_DAILY_7",
        "name": "LAB 03 · Constancia diaria 7 días",
        "benefit": "LAB_FID_DAILY_7",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "MIN_CLASSES_PER_ACTIVE_DAY", "operator": "GTE", "value": 3, "windowDays": 7},
            {"field": "ACTIVE_STUDY_DAYS", "operator": "GTE", "value": 7, "windowDays": 7},
        ],
        "message": "Siete días de constancia: seguí construyendo el hábito.",
    },
    {
        "code": "LAB_FID_04_STREAK_14",
        "name": "LAB 04 · Racha de estudio 14 días",
        "benefit": "LAB_FID_STREAK_14",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "STUDY_STREAK_DAYS", "operator": "GTE", "value": 14},
        ],
        "message": "Tu racha de 14 días merece un premio.",
    },
    {
        "code": "LAB_FID_05_ACTIVE_20",
        "name": "LAB 05 · Alta presencia mensual",
        "benefit": "LAB_FID_ACTIVE_20",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "ACTIVE_STUDY_DAYS", "operator": "GTE", "value": 20, "windowDays": 30},
        ],
        "message": "Tu presencia constante durante el mes se nota.",
    },
    {
        "code": "LAB_FID_06_VOLUME_50",
        "name": "LAB 06 · Volumen mensual de 50 clases",
        "benefit": "LAB_FID_VOLUME_50",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "CLASSES_COMPLETED", "operator": "GTE", "value": 50, "windowDays": 30},
        ],
        "message": "Completaste un gran volumen de práctica este mes.",
    },
    {
        "code": "LAB_FID_07_A1_INTENSE",
        "name": "LAB 07 · Impulso A1 intensivo",
        "benefit": "LAB_FID_A1_INTENSE",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "CURRENT_LEVEL", "operator": "EQ", "value": "A1"},
            {"field": "CLASSES_COMPLETED", "operator": "GTE", "value": 30, "windowDays": 14},
        ],
        "message": "Tu intensidad de práctica en A1 merece un impulso extra.",
    },
    {
        "code": "LAB_FID_08_WINBACK_30",
        "name": "LAB 08 · Volvé después de 30 días",
        "benefit": "LAB_FID_WINBACK_30",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
            {"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "GTE", "value": 30},
        ],
        "message": "Hace tiempo que no practicás. Te damos un impulso para volver.",
    },
    {
        "code": "LAB_FID_09_WINBACK_90",
        "name": "LAB 09 · Recuperación larga 90 días",
        "benefit": "LAB_FID_WINBACK_90",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
            {"field": "DAYS_SINCE_LAST_ACTIVITY", "operator": "GTE", "value": 90},
        ],
        "message": "Queremos ayudarte a retomar después de una pausa larga.",
    },
    {
        "code": "LAB_FID_10_EXPIRED_30",
        "name": "LAB 10 · Regreso tras servicio vencido",
        "benefit": "LAB_FID_EXPIRED_30",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
            {"field": "DAYS_SINCE_SERVICE_EXPIRED", "operator": "GTE", "value": 30},
        ],
        "message": "Tu servicio venció hace tiempo; tenemos una propuesta para volver.",
    },
    {
        "code": "LAB_FID_11_NEVER_STARTED",
        "name": "LAB 11 · Registrado pero nunca empezó",
        "benefit": "LAB_FID_NEVER_STARTED",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "NEVER_STUDIED", "operator": "EQ", "value": True},
        ],
        "message": "Tu primera práctica todavía te está esperando.",
    },
    {
        "code": "LAB_FID_12_LOW_ACTIVITY",
        "name": "LAB 12 · Riesgo por baja actividad",
        "benefit": "LAB_FID_LOW_ACTIVITY",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "CLASSES_COMPLETED", "operator": "LTE", "value": 3, "windowDays": 30},
        ],
        "message": "Vimos poca actividad reciente; te damos un incentivo para retomar.",
    },
    {
        "code": "LAB_FID_13_BYOK_6M",
        "name": "LAB 13 · Fidelidad usando propias keys",
        "benefit": "LAB_FID_BYOK_6M",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "SERVICE_SOURCE", "operator": "EQ", "value": "BYOK"},
            {"field": "DAYS_SINCE_CREATED", "operator": "GTE", "value": 180},
        ],
        "message": "Gracias por seguir aprendiendo con tus propias conexiones de IA.",
    },
    {
        "code": "LAB_FID_14_HYBRID_ACTIVE",
        "name": "LAB 14 · Fidelidad híbrida + actividad",
        "benefit": "LAB_FID_HYBRID_ACTIVE",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "SERVICE_SOURCE", "operator": "EQ", "value": "HYBRID"},
            {"field": "ACTIVE_STUDY_DAYS", "operator": "GTE", "value": 15, "windowDays": 30},
        ],
        "message": "Tu uso sostenido del servicio híbrido merece un reconocimiento.",
    },
    {
        "code": "LAB_FID_15_COMPLAINT",
        "name": "LAB 15 · Compensación manual post-reclamo · editar email",
        "benefit": "LAB_FID_COMPLAINT",
        "rules": [
            {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
            {"field": "ACCOUNT_EMAIL", "operator": "EQ", "value": "reemplazar@ejemplo.invalid"},
        ],
        "message": "Compensación de cortesía luego de resolver tu reclamo.",
    },
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seed_campaigns(db: Session) -> None:
    """Crea seeds idempotentes: bienvenida siempre; laboratorio T-065 solo en local/dev."""
    marker = db.get(CampaignSeedMarker, WELCOME_CODE)
    if marker is None:
        existing = db.scalar(select(Campaign).where(Campaign.code == WELCOME_CODE))
        if existing is not None:
            db.add(CampaignSeedMarker(code=WELCOME_CODE))
            db.flush()
        else:
            seed_benefits(db)
            benefit = db.scalar(select(Benefit).where(Benefit.code == WELCOME_BENEFIT_CODE))
            if benefit is not None:
                db.add(CampaignSeedMarker(code=WELCOME_CODE))
                db.add(
                    Campaign(
                        code=WELCOME_CODE,
                        name="Bienvenida · 3 días de Plataforma",
                        benefit_id=benefit.id,
                        status=CampaignStatus.DRAFT,
                        trigger=CampaignTrigger.FIRST_LOGIN,
                        eligibility={
                            "mode": "ALL",
                            "rules": [
                                {"field": "ACCOUNT_TYPE", "operator": "EQ", "value": "PERSONAL"},
                                {"field": "HAS_GRANTED_SERVICE", "operator": "EQ", "value": False},
                            ],
                        },
                        priority=100,
                        stackable=False,
                        notification=CampaignNotification.IN_APP,
                        message="Bienvenido: tenés 3 días para probar la IA de Librería Inglés.",
                    )
                )
                db.flush()

    if settings.app_env.lower() in {"local", "dev", "development"}:
        _seed_fidelity_lab_campaigns(db)


def _seed_fidelity_lab_campaigns(db: Session) -> None:
    """Siembra 15 campañas DRAFT del laboratorio T-065 solo en bases locales/dev."""
    benefits = seed_fidelity_lab_benefits(db)

    for index, spec in enumerate(FIDELITY_LAB_CAMPAIGNS, start=1):
        code = spec["code"]
        marker = db.get(CampaignSeedMarker, code)
        if marker is not None:
            continue

        existing = db.scalar(select(Campaign).where(Campaign.code == code))
        if existing is not None:
            db.add(CampaignSeedMarker(code=code))
            continue

        benefit = benefits.get(spec["benefit"])
        if benefit is None:
            continue

        db.add(CampaignSeedMarker(code=code))
        db.add(
            Campaign(
                code=code,
                name=spec["name"],
                benefit_id=benefit.id,
                action=CampaignAction.GRANT_BENEFIT,
                action_config={},
                status=CampaignStatus.DRAFT,
                trigger=CampaignTrigger.LOGIN,
                eligibility={"mode": "ALL", "rules": spec["rules"]},
                priority=200 + index,
                stackable=False,
                notification=CampaignNotification.IN_APP,
                message=spec["message"],
            )
        )
    db.flush()


def _scope_matches(db: Session, campaign: Campaign, account: Account) -> bool:
    if campaign.organization_id is None:
        return True
    return (
        db.scalar(
            select(Membership.id).where(
                Membership.account_id == account.id,
                Membership.organization_id == campaign.organization_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        is not None
    )


def _within_window(campaign: Campaign, now: datetime) -> bool:
    starts = _as_utc(campaign.starts_at)
    ends = _as_utc(campaign.ends_at)
    return (starts is None or starts <= now) and (ends is None or now < ends)


def _first_login_matches(campaign: Campaign, account: Account) -> bool:
    first_login = _as_utc(account.first_login_at)
    activated = _as_utc(campaign.activated_at)
    if first_login is None or activated is None or first_login < activated:
        return False

    starts = _as_utc(campaign.starts_at)
    ends = _as_utc(campaign.ends_at)
    if starts is not None and first_login < starts:
        return False
    if ends is not None and first_login >= ends:
        return False
    return True


def _compare_number(actual: int | float, operator: str, expected: int | float) -> bool:
    if operator == "EQ":
        return actual == expected
    if operator == "GTE":
        return actual >= expected
    if operator == "LTE":
        return actual <= expected
    return False


def _days_since(value: datetime | None, now: datetime) -> int | None:
    value = _as_utc(value)
    if value is None:
        return None
    return max(0, int((now - value).total_seconds() // 86400))


def _days_until(value: datetime | None, now: datetime) -> int | None:
    value = _as_utc(value)
    if value is None or value <= now:
        return None
    return max(1, ceil((value - now).total_seconds() / 86400))


def _last_activity_at(db: Session, account: Account) -> datetime | None:
    return db.scalar(
        select(func.max(ClassSession.evaluated_at)).where(
            ClassSession.account_id == account.id,
            ClassSession.kind == SessionKind.CLASS,
            ClassSession.status == ClassSessionStatus.COMPLETED,
            ClassSession.evaluated_at.is_not(None),
        )
    )


def _completed_activity_times(
    db: Session,
    account: Account,
    *,
    since: datetime | None = None,
) -> list[datetime]:
    query = select(ClassSession.evaluated_at).where(
        ClassSession.account_id == account.id,
        ClassSession.kind == SessionKind.CLASS,
        ClassSession.status == ClassSessionStatus.COMPLETED,
        ClassSession.evaluated_at.is_not(None),
    )
    if since is not None:
        query = query.where(ClassSession.evaluated_at >= since)
    values = db.scalars(query.order_by(ClassSession.evaluated_at.asc())).all()
    return [value for value in (_as_utc(item) for item in values) if value is not None]


def _streak_history(db: Session, account: Account, *, now: datetime) -> tuple[int, int | None]:
    days = sorted({value.date() for value in _completed_activity_times(db, account)})
    if not days:
        return 0, None

    runs: list[tuple[object, object, int]] = []
    start = previous = days[0]
    length = 1
    for day in days[1:]:
        if day == previous + timedelta(days=1):
            length += 1
        else:
            runs.append((start, previous, length))
            start = day
            length = 1
        previous = day
    runs.append((start, previous, length))

    # Una racha que terminó hoy o ayer todavía se considera vigente: aún no hubo un
    # día calendario completo sin actividad que pruebe que se cortó.
    ended = [run for run in runs if run[1] < now.date() - timedelta(days=1)]
    if not ended:
        return 0, None

    _, ended_at, ended_length = ended[-1]
    broken_on = ended_at + timedelta(days=1)
    return ended_length, max(0, (now.date() - broken_on).days)


def _exam_metric(
    db: Session,
    account: Account,
    *,
    field: str,
    window_days: int | None,
    now: datetime,
) -> int | None:
    if window_days is None:
        return None
    since = now - timedelta(days=window_days)
    rows = db.scalars(
        select(ClassSession).where(
            ClassSession.account_id == account.id,
            ClassSession.kind == SessionKind.EXAM,
            ClassSession.status == ClassSessionStatus.COMPLETED,
            ClassSession.evaluated_at.is_not(None),
            ClassSession.evaluated_at >= since,
        )
    ).all()
    if field == "EXAMS_COMPLETED":
        return len(rows)
    if field == "EXAMS_PASSED":
        return sum(1 for row in rows if (row.exam_result or {}).get("passed") is True)
    if field == "EXAMS_FAILED":
        return sum(1 for row in rows if (row.exam_result or {}).get("passed") is False)
    return None


def _class_lifecycle_metric(
    db: Session,
    account: Account,
    *,
    field: str,
    window_days: int | None,
    now: datetime,
) -> int | None:
    if window_days is None:
        return None
    since = now - timedelta(days=window_days)

    if field == "CLASSES_GENERATED":
        return int(
            db.scalar(
                select(func.count(ClassSession.id)).where(
                    ClassSession.account_id == account.id,
                    ClassSession.kind == SessionKind.CLASS,
                    ClassSession.generated_at.is_not(None),
                    ClassSession.generated_at >= since,
                )
            )
            or 0
        )

    if field == "CLASSES_GENERATION_FAILED":
        # Hoy ClassSession no conserva failed_at; el fallo ocurre en el mismo flujo
        # inmediato de generación, por lo que created_at es la marca persistente disponible.
        return int(
            db.scalar(
                select(func.count(ClassSession.id)).where(
                    ClassSession.account_id == account.id,
                    ClassSession.kind == SessionKind.CLASS,
                    ClassSession.status == ClassSessionStatus.GENERATION_FAILED,
                    ClassSession.created_at >= since,
                )
            )
            or 0
        )

    if field == "CLASSES_NOT_COMPLETED":
        return int(
            db.scalar(
                select(func.count(ClassSession.id)).where(
                    ClassSession.account_id == account.id,
                    ClassSession.kind == SessionKind.CLASS,
                    ClassSession.generated_at.is_not(None),
                    ClassSession.generated_at >= since,
                    ClassSession.status != ClassSessionStatus.COMPLETED,
                )
            )
            or 0
        )

    if field == "CLASSES_STARTED":
        rows = db.scalars(
            select(ClassSession).where(
                ClassSession.account_id == account.id,
                ClassSession.kind == SessionKind.CLASS,
                ClassSession.created_at >= since,
            )
        ).all()
        started_statuses = {
            ClassSessionStatus.IN_PROGRESS,
            ClassSessionStatus.AWAITING_EVALUATION,
            ClassSessionStatus.COMPLETED,
        }
        return sum(
            1
            for row in rows
            if row.status in started_statuses
            or row.current_attempt > 1
            or row.submitted_at is not None
            or row.evaluated_at is not None
        )

    return None


def _activity_day_counts(
    db: Session,
    account: Account,
    *,
    now: datetime,
    window_days: int,
) -> Counter:
    since = now - timedelta(days=window_days)
    return Counter(value.date() for value in _completed_activity_times(db, account, since=since))


def _study_streak_days(db: Session, account: Account, *, now: datetime) -> int:
    days = sorted({value.date() for value in _completed_activity_times(db, account)}, reverse=True)
    if not days:
        return 0
    today = now.date()
    if days[0] < today - timedelta(days=1):
        return 0

    streak = 1
    current = days[0]
    for candidate in days[1:]:
        if candidate == current - timedelta(days=1):
            streak += 1
            current = candidate
        elif candidate < current - timedelta(days=1):
            break
    return streak


def _activity_metric(
    db: Session,
    account: Account,
    *,
    field: str,
    window_days: int | None,
    now: datetime,
) -> int | float | None:
    if field == "STUDY_STREAK_DAYS":
        return _study_streak_days(db, account, now=now)
    if field in {"LAST_ENDED_STREAK_DAYS", "DAYS_SINCE_STREAK_BROKEN"}:
        ended_length, days_since_broken = _streak_history(db, account, now=now)
        return ended_length if field == "LAST_ENDED_STREAK_DAYS" else days_since_broken
    if field in {"EXAMS_COMPLETED", "EXAMS_PASSED", "EXAMS_FAILED"}:
        return _exam_metric(
            db,
            account,
            field=field,
            window_days=window_days,
            now=now,
        )
    if field in {
        "CLASSES_GENERATED",
        "CLASSES_STARTED",
        "CLASSES_GENERATION_FAILED",
        "CLASSES_NOT_COMPLETED",
    }:
        return _class_lifecycle_metric(
            db,
            account,
            field=field,
            window_days=window_days,
            now=now,
        )
    if window_days is None:
        return None

    counts = _activity_day_counts(db, account, now=now, window_days=window_days)
    if field == "CLASSES_COMPLETED":
        return sum(counts.values())
    if field == "ACTIVE_STUDY_DAYS":
        return len(counts)
    if field == "MIN_CLASSES_PER_ACTIVE_DAY":
        return min(counts.values()) if counts else 0
    if field == "AVERAGE_CLASSES_PER_ACTIVE_DAY":
        return round(sum(counts.values()) / len(counts), 2) if counts else 0.0
    if field == "AVERAGE_CLASSES_PER_DAY":
        return round(sum(counts.values()) / window_days, 2) if window_days else None
    return None


def _last_expired_service_at(db: Session, account: Account) -> datetime | None:
    # Fuerza el vencimiento perezoso antes de consultar el histórico.
    effective_service(db, account)
    rows = db.scalars(
        select(Subscription)
        .where(
            Subscription.account_id == account.id,
            Subscription.status == SubscriptionStatus.EXPIRED,
        )
        .order_by(Subscription.ended_at.desc(), Subscription.expires_at.desc(), Subscription.id.desc())
    ).all()
    if not rows:
        return None
    latest = rows[0]
    return latest.ended_at or latest.expires_at


def _current_level(db: Session, account: Account) -> str | None:
    row = db.execute(
        select(AccountStudyProfile, StudyProfile)
        .join(StudyProfile, StudyProfile.id == AccountStudyProfile.study_profile_id)
        .where(
            AccountStudyProfile.account_id == account.id,
            AccountStudyProfile.status == AccountStudyProfileStatus.ACTIVE,
            StudyProfile.status == StudyProfileStatus.ACTIVE,
        )
        .order_by(AccountStudyProfile.linked_at.desc())
    ).first()
    if row is None:
        return None
    _, profile = row
    return profile.operational_level or profile.selected_level or profile.estimated_level


def _active_study_profile(db: Session, account: Account) -> tuple[AccountStudyProfile, StudyProfile] | None:
    row = db.execute(
        select(AccountStudyProfile, StudyProfile)
        .join(StudyProfile, StudyProfile.id == AccountStudyProfile.study_profile_id)
        .where(
            AccountStudyProfile.account_id == account.id,
            AccountStudyProfile.status == AccountStudyProfileStatus.ACTIVE,
            StudyProfile.status == StudyProfileStatus.ACTIVE,
        )
        .order_by(AccountStudyProfile.linked_at.desc())
    ).first()
    return (row[0], row[1]) if row is not None else None


def _progress_metric(
    db: Session,
    account: Account,
    *,
    field: str,
    subject: str,
) -> str | float | None:
    active = _active_study_profile(db, account)
    if active is None:
        return None
    link, profile = active

    if field.startswith("SKILL_"):
        progress = db.scalar(
            select(StudySkillProgress).where(
                StudySkillProgress.study_profile_id == link.study_profile_id,
                StudySkillProgress.skill_key == subject,
                StudySkillProgress.organization_id.is_(None),
            )
        )
        if field == "SKILL_STATUS":
            return progress.status if progress is not None and progress.attempt_count else "NOT_STARTED"
        if field == "SKILL_SCORE":
            return progress.score if progress is not None and progress.attempt_count else None
        if field == "SKILL_TREND":
            return progress.trend.upper() if progress is not None and progress.trend else None
        return None

    level = profile.operational_level or profile.selected_level or profile.estimated_level
    if not level:
        return None
    # Campaigns consume el agregado oficial del dominio de progreso; no recalculan
    # evidencias, estados ni tendencias por su cuenta.
    item = next(
        (row for row in ability_progress(db, link.study_profile_id, level) if row["key"] == subject),
        None,
    )
    if item is None:
        return None
    if field == "ABILITY_STATUS":
        return item.get("status")
    if field == "ABILITY_SCORE":
        return item.get("score")
    if field == "ABILITY_TREND":
        trend = item.get("trend")
        return str(trend).upper() if trend else None
    return None


def _appeals_count(
    db: Session,
    account: Account,
    *,
    window_days: int | None,
    now: datetime,
) -> int | None:
    if window_days is None:
        return None
    since = now - timedelta(days=window_days)
    return int(
        db.scalar(
            select(func.count(Attempt.id)).where(
                Attempt.account_id == account.id,
                Attempt.appealed_at.is_not(None),
                Attempt.appealed_at >= since,
            )
        )
        or 0
    )


def _modality_response_count(db: Session, account: Account, *, field: str) -> int:
    query = (
        select(func.count(Attempt.id))
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .where(Attempt.account_id == account.id)
    )
    if field == "SPEAKING_RESPONSES":
        query = query.where(Attempt.response_mode == ResponseMode.SPEAK)
    else:
        query = query.where(Exercise.presentation_mode == PresentationMode.LISTEN)
    return int(db.scalar(query) or 0)


AI_HEALTH_CHECK_OPERATION = "health_check"
AI_CREDENTIAL_OR_QUOTA_ERRORS = {"INVALID_CREDENTIALS", "QUOTA_EXCEEDED"}


def _ai_failures_count(
    db: Session,
    account: Account,
    *,
    window_days: int | None,
    filters: dict,
    now: datetime,
) -> int | None:
    if window_days is None:
        return None
    since = now - timedelta(days=window_days)
    query = select(func.count(AIUsageEvent.id)).where(
        AIUsageEvent.account_id == account.id,
        AIUsageEvent.success.is_(False),
        AIUsageEvent.created_at >= since,
    )

    owner_type = str(filters.get("ownerType") or "").strip().upper()
    if owner_type:
        query = query.where(AIUsageEvent.owner_type == AIConnectionOwnerType(owner_type))

    error_code = str(filters.get("errorCode") or "").strip().upper()
    if error_code == "CREDENTIAL_OR_QUOTA":
        query = query.where(AIUsageEvent.error_code.in_(AI_CREDENTIAL_OR_QUOTA_ERRORS))
    elif error_code:
        query = query.where(AIUsageEvent.error_code == error_code)

    operation = str(filters.get("operation") or "").strip().lower()
    if operation:
        query = query.where(AIUsageEvent.operation == operation)

    return int(db.scalar(query) or 0)


def _days_since_byok_configured_without_success(
    db: Session,
    account: Account,
    *,
    now: datetime,
) -> int | None:
    connections = list(
        db.scalars(
            select(AIConnection).where(
                AIConnection.owner_type == AIConnectionOwnerType.ACCOUNT,
                AIConnection.owner_id == account.id,
                AIConnection.active.is_(True),
            )
        ).all()
    )
    if not connections:
        return None

    connection_ids = [connection.id for connection in connections]
    successful_real_use = db.scalar(
        select(func.count(AIUsageEvent.id)).where(
            AIUsageEvent.connection_id.in_(connection_ids),
            AIUsageEvent.account_id == account.id,
            AIUsageEvent.success.is_(True),
            AIUsageEvent.operation != AI_HEALTH_CHECK_OPERATION,
        )
    ) or 0
    if int(successful_real_use) > 0:
        return None

    oldest = min(
        (_as_utc(connection.created_at) for connection in connections if connection.created_at),
        default=None,
    )
    return _days_since(oldest, now)


def rule_evaluation(
    db: Session,
    account: Account,
    rule: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Evalúa una condición y devuelve evidencia explicable para preview/auditoría."""
    now = now or utcnow()
    field = str(rule.get("field", "")).upper()
    operator = str(rule.get("operator", "EQ")).upper()
    expected = rule.get("value")
    actual = None

    if field == "ACCOUNT_TYPE":
        actual = account.account_type.value
        matched = operator == "EQ" and actual == str(expected).upper()
    elif field in {"HAS_GRANTED_SERVICE", "SERVICE_SOURCE"}:
        service = effective_service(db, account)
        if field == "HAS_GRANTED_SERVICE":
            actual = service.granted
            matched = operator == "EQ" and actual == bool(expected)
        else:
            actual = service.source.value
            matched = operator == "EQ" and actual == str(expected).upper()
    elif field == "ACCOUNT_EMAIL":
        actual = account.email.lower()
        matched = operator == "EQ" and actual == str(expected).strip().lower()
    elif field == "EMAIL_DOMAIN":
        actual = account.email.rsplit("@", 1)[-1].lower() if "@" in account.email else ""
        matched = operator == "EQ" and actual == str(expected).strip().lower()
    elif field == "DOCUMENT_COUNTRY":
        actual = account.document_country.upper() if account.document_country else None
        matched = operator == "EQ" and actual == str(expected).strip().upper()
    elif field == "DAYS_SINCE_CREATED":
        actual = _days_since(account.created_at, now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "CREATED_AT":
        actual_dt = _as_utc(account.created_at)
        actual = actual_dt.isoformat() if actual_dt else None
        try:
            expected_dt = _as_utc(datetime.fromisoformat(str(expected).replace("Z", "+00:00")))
            if operator == "GTE":
                matched = actual_dt is not None and actual_dt >= expected_dt
            elif operator == "LTE":
                matched = actual_dt is not None and actual_dt <= expected_dt
            else:
                matched = actual_dt is not None and actual_dt == expected_dt
        except (TypeError, ValueError):
            matched = False
    elif field == "DAYS_SINCE_LAST_ACTIVITY":
        last_activity = _last_activity_at(db, account)
        actual = _days_since(last_activity, now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "NEVER_STUDIED":
        actual = _last_activity_at(db, account) is None
        matched = operator == "EQ" and actual == bool(expected)
    elif field == "DAYS_SINCE_SERVICE_EXPIRED":
        actual = _days_since(_last_expired_service_at(db, account), now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "DAYS_UNTIL_SERVICE_EXPIRES":
        service = effective_service(db, account)
        actual = _days_until(service.expires_at, now) if service.granted else None
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "SUBSCRIPTION_ORIGIN":
        service = effective_service(db, account)
        actual = service.origin.value if service.granted and service.origin is not None else None
        matched = operator == "EQ" and actual == str(expected).strip().upper()
    elif field == "CURRENT_LEVEL":
        actual = _current_level(db, account)
        matched = operator == "EQ" and actual == str(expected).upper()
    elif field in {
        "SKILL_STATUS",
        "SKILL_SCORE",
        "SKILL_TREND",
        "ABILITY_STATUS",
        "ABILITY_SCORE",
        "ABILITY_TREND",
    }:
        subject = str(rule.get("subject") or "").strip()
        actual = _progress_metric(db, account, field=field, subject=subject)
        if field.endswith("_SCORE"):
            try:
                matched = actual is not None and _compare_number(float(actual), operator, float(expected))
            except (TypeError, ValueError):
                matched = False
        else:
            matched = operator == "EQ" and actual is not None and str(actual).upper() == str(expected).upper()
    elif field == "APPEALS_COUNT":
        window_days = rule.get("windowDays")
        try:
            window_days = int(window_days) if window_days is not None else None
        except (TypeError, ValueError):
            window_days = None
        actual = _appeals_count(db, account, window_days=window_days, now=now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field in {"SPEAKING_RESPONSES", "LISTENING_RESPONSES"}:
        actual = _modality_response_count(db, account, field=field)
        try:
            matched = _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "AI_FAILURES_COUNT":
        window_days = rule.get("windowDays")
        try:
            window_days = int(window_days) if window_days is not None else None
        except (TypeError, ValueError):
            window_days = None
        actual = _ai_failures_count(
            db,
            account,
            window_days=window_days,
            filters=rule.get("filters") or {},
            now=now,
        )
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field == "DAYS_SINCE_BYOK_CONFIGURED_WITHOUT_SUCCESS":
        actual = _days_since_byok_configured_without_success(db, account, now=now)
        try:
            matched = actual is not None and _compare_number(actual, operator, int(expected))
        except (TypeError, ValueError):
            matched = False
    elif field in {
        "CLASSES_COMPLETED",
        "CLASSES_GENERATED",
        "CLASSES_STARTED",
        "CLASSES_GENERATION_FAILED",
        "CLASSES_NOT_COMPLETED",
        "EXAMS_COMPLETED",
        "EXAMS_PASSED",
        "EXAMS_FAILED",
        "ACTIVE_STUDY_DAYS",
        "MIN_CLASSES_PER_ACTIVE_DAY",
        "AVERAGE_CLASSES_PER_ACTIVE_DAY",
        "AVERAGE_CLASSES_PER_DAY",
        "STUDY_STREAK_DAYS",
        "LAST_ENDED_STREAK_DAYS",
        "DAYS_SINCE_STREAK_BROKEN",
    }:
        window_days = rule.get("windowDays")
        try:
            window_days = int(window_days) if window_days is not None else None
        except (TypeError, ValueError):
            window_days = None
        actual = _activity_metric(
            db,
            account,
            field=field,
            window_days=window_days,
            now=now,
        )
        try:
            matched = actual is not None and _compare_number(actual, operator, float(expected))
        except (TypeError, ValueError):
            matched = False
    else:
        matched = False

    result = {
        "field": field,
        "operator": operator,
        "expected": expected,
        "actual": actual,
        "matched": bool(matched),
    }
    if rule.get("subject"):
        result["subject"] = rule.get("subject")
    if rule.get("filters"):
        result["filters"] = rule.get("filters")
    if rule.get("windowDays") is not None:
        result["windowDays"] = rule.get("windowDays")
    return result


def _rule_matches(db: Session, account: Account, rule: dict, now: datetime) -> bool:
    return bool(rule_evaluation(db, account, rule, now=now)["matched"])


def preview_audience(
    db: Session,
    *,
    rules: list[dict],
    trigger: CampaignTrigger,
    campaign_id: int | None = None,
    sample_limit: int = 10,
) -> dict:
    """Simula audiencia sin aplicar beneficio ni crear grants.

    Para FIRST_LOGIN de una campaña nueva, solo son candidatos prospectivos quienes todavía
    no hicieron su primer login. Para una campaña ya activada se respeta activated_at.
    """
    now = utcnow()
    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    accounts = db.scalars(
        select(Account)
        .where(
            Account.status == AccountStatus.ACTIVE,
            Account.account_type == AccountType.PERSONAL,
            Account.platform_role.is_(None),
        )
        .order_by(Account.id)
    ).all()

    rows: list[dict] = []
    for account in accounts:
        evaluations = [rule_evaluation(db, account, rule, now=now) for rule in rules]
        conditions_match = all(item["matched"] for item in evaluations)

        already_received = False
        if campaign_id is not None:
            already_received = db.scalar(
                select(CampaignGrant.id).where(
                    CampaignGrant.campaign_id == campaign_id,
                    CampaignGrant.account_id == account.id,
                )
            ) is not None

        if trigger == CampaignTrigger.FIRST_LOGIN:
            if campaign is not None and campaign.activated_at is not None:
                trigger_match = _first_login_matches(campaign, account)
            else:
                trigger_match = account.first_login_at is None
        else:
            # LOGIN y SCHEDULED dependen del evento/scheduler; el preview responde quién
            # cumple las condiciones ahora.
            trigger_match = True

        eligible_now = conditions_match and trigger_match and not already_received
        rows.append(
            {
                "accountId": account.id,
                "email": account.email,
                "displayName": account.display_name,
                "eligible": eligible_now,
                "alreadyReceived": already_received,
                "triggerMatch": trigger_match,
                "rules": evaluations,
            }
        )

    eligible_rows = [row for row in rows if row["eligible"]]
    excluded_rows = [row for row in rows if not row["eligible"]]
    sample = (eligible_rows[:sample_limit] + excluded_rows[: max(0, sample_limit - len(eligible_rows[:sample_limit]))])[:sample_limit]
    warnings: list[str] = []
    if trigger == CampaignTrigger.SCHEDULED:
        warnings.append("La audiencia se puede simular, pero SCHEDULED requiere el scheduler de T-059 para ejecutarse.")
    if trigger == CampaignTrigger.FIRST_LOGIN and campaign is None:
        warnings.append("Para una campaña nueva de primer login, el preview cuenta solo cuentas que aún no ingresaron por primera vez.")

    return {
        "candidateCount": len(rows),
        "eligibleCount": len(eligible_rows),
        "excludedCount": len(excluded_rows),
        "sample": sample,
        "warnings": warnings,
    }


def _available_for_account(
    db: Session, campaign: Campaign, account: Account, *, now: datetime
) -> bool:
    if (
        campaign.deleted_at is not None
        or campaign.status != CampaignStatus.ACTIVE
        or not _within_window(campaign, now)
    ):
        return False
    if not _scope_matches(db, campaign, account):
        return False
    return db.scalar(
        select(CampaignGrant.id).where(
            CampaignGrant.campaign_id == campaign.id,
            CampaignGrant.account_id == account.id,
        )
    ) is None


def eligible(db: Session, campaign: Campaign, account: Account, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if not _available_for_account(db, campaign, account, now=now):
        return False
    if campaign.trigger == CampaignTrigger.FIRST_LOGIN and not _first_login_matches(campaign, account):
        return False
    eligibility = campaign.eligibility or {"mode": "ALL", "rules": []}
    if str(eligibility.get("mode", "ALL")).upper() != "ALL":
        return False
    return all(_rule_matches(db, account, rule, now) for rule in eligibility.get("rules", []))


def _notification_message(campaign: Campaign, benefit: str) -> str:
    return (campaign.message or "").strip() or f'Recibiste la campaña "{campaign.name}": {benefit}.'


def _apply_benefit(db: Session, campaign: Campaign, account: Account) -> BenefitApplication | None:
    benefit = db.get(Benefit, campaign.benefit_id)
    if benefit is None:
        return None
    creator = db.get(Account, campaign.created_by_account_id) if campaign.created_by_account_id else None
    return apply_service_benefit(
        db,
        benefit,
        account,
        granted_by=creator,
        origin=SubscriptionOrigin.CAMPAIGN,
        note=f"Campaña #{campaign.id}: {campaign.name}",
    )


def apply_campaign(
    db: Session,
    campaign: Campaign,
    account: Account,
    *,
    conditions_prechecked: bool = False,
) -> CampaignGrant | None:
    """Reserva cupo, aplica el beneficio y registra nunca_recibió(campaña)."""
    locked = db.scalar(select(Campaign).where(Campaign.id == campaign.id).with_for_update())
    now = utcnow()
    if locked is None or not _available_for_account(db, locked, account, now=now):
        return None
    if not conditions_prechecked and not eligible(db, locked, account, now=now):
        return None
    if locked.max_recipients is not None:
        used = db.scalar(
            select(func.count(CampaignGrant.id)).where(CampaignGrant.campaign_id == locked.id)
        ) or 0
        if int(used) >= locked.max_recipients:
            return None

    if locked.action != CampaignAction.GRANT_BENEFIT:
        # T-065 modela acciones futuras, pero solo GRANT_BENEFIT está habilitada hoy.
        return None

    application = _apply_benefit(db, locked, account)
    if application is None or not application.applied or application.subscription is None:
        return None

    notification = locked.notification
    grant = CampaignGrant(
        campaign_id=locked.id,
        account_id=account.id,
        subscription_id=application.subscription.id,
        benefit_summary=application.summary,
        notification_message=(
            _notification_message(locked, application.summary)
            if notification in {CampaignNotification.IN_APP, CampaignNotification.IN_APP_EMAIL}
            else None
        ),
        email_status=(
            "PENDING"
            if notification in {CampaignNotification.EMAIL, CampaignNotification.IN_APP_EMAIL}
            else None
        ),
    )
    db.add(grant)
    db.flush()
    return grant


def _evaluate_campaigns(
    db: Session,
    account: Account,
    *,
    triggers: list[CampaignTrigger],
) -> list[CampaignGrant]:
    if account.platform_role == PlatformRole.PLATFORM_OWNER:
        return []
    seed_campaigns(db)
    now = utcnow()
    campaigns = db.scalars(
        select(Campaign)
        .where(
            Campaign.status == CampaignStatus.ACTIVE,
            Campaign.deleted_at.is_(None),
            Campaign.trigger.in_(triggers),
        )
        .order_by(Campaign.priority.asc(), Campaign.id.asc())
    ).all()

    candidates = [campaign for campaign in campaigns if eligible(db, campaign, account, now=now)]

    applied: list[CampaignGrant] = []
    applied_campaigns: list[Campaign] = []
    for campaign in candidates:
        if applied_campaigns and (
            not campaign.stackable or any(not previous.stackable for previous in applied_campaigns)
        ):
            continue
        grant = apply_campaign(db, campaign, account, conditions_prechecked=True)
        if grant is None:
            continue
        applied.append(grant)
        applied_campaigns.append(campaign)
        if not campaign.stackable:
            break
    return applied


def evaluate_login_campaigns(
    db: Session,
    account: Account,
    *,
    first_login: bool | None = None,
) -> list[CampaignGrant]:
    return _evaluate_campaigns(
        db,
        account,
        triggers=[CampaignTrigger.FIRST_LOGIN, CampaignTrigger.LOGIN],
    )


def reconcile_first_login_campaigns(db: Session, account: Account) -> list[CampaignGrant]:
    return _evaluate_campaigns(db, account, triggers=[CampaignTrigger.FIRST_LOGIN])


def pending_in_app_notices(db: Session, account: Account) -> list[dict]:
    rows = db.execute(
        select(CampaignGrant, Campaign)
        .join(Campaign, Campaign.id == CampaignGrant.campaign_id)
        .where(
            CampaignGrant.account_id == account.id,
            CampaignGrant.notification_message.is_not(None),
            CampaignGrant.in_app_read_at.is_(None),
        )
        .order_by(CampaignGrant.applied_at.desc(), CampaignGrant.id.desc())
    ).all()
    return [
        {
            "grantId": grant.id,
            "campaignId": campaign.id,
            "campaign": campaign.name,
            "message": grant.notification_message,
            "benefit": grant.benefit_summary,
            "appliedAt": grant.applied_at,
        }
        for grant, campaign in rows
    ]


def mark_notice_read(db: Session, account: Account, grant_id: int) -> bool:
    grant = db.scalar(
        select(CampaignGrant).where(
            CampaignGrant.id == grant_id,
            CampaignGrant.account_id == account.id,
            CampaignGrant.notification_message.is_not(None),
        )
    )
    if grant is None:
        return False
    if grant.in_app_read_at is None:
        grant.in_app_read_at = utcnow()
        db.flush()
    return True
