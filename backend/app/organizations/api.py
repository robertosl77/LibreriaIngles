from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DbSession
from app.organizations.contact_validation import (
    check_website,
    normalize_phone,
    normalize_website,
)
from app.organizations.job_titles import (
    get_job_title,
    resolve_job_title,
    search_job_titles,
)
from app.organizations.models import (
    JobTitle,
    Organization,
    OrganizationActingCapacity,
    OrganizationOnboarding,
    OrganizationOnboardingStatus,
    utcnow,
)
from app.organizations.verification import (
    OrganizationVerificationResult,
    VerificationState,
    normalize_tax_id,
    verify_organization,
)

router = APIRouter(prefix="/organization-onboarding", tags=["organization-onboarding"])


class CompanyLookupIn(BaseModel):
    country: str = Field(default="AR", min_length=2, max_length=2)
    taxIdType: str = Field(default="CUIT", min_length=2, max_length=32)
    taxId: str = Field(min_length=1, max_length=64)


class ReferentIn(BaseModel):
    firstName: str = Field(min_length=1, max_length=100)
    lastName: str = Field(min_length=1, max_length=100)
    email: EmailStr
    jobTitleId: int | None = Field(default=None, ge=1)
    jobTitle: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=6, max_length=64)
    actingCapacity: OrganizationActingCapacity
    authorityDeclared: bool


class JobTitleResolveIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    confirmSimilar: bool = False


class WebsiteCheckIn(BaseModel):
    website: str = Field(min_length=3, max_length=500)


class PhoneNormalizeIn(BaseModel):
    country: str = Field(default="AR", min_length=2, max_length=2)
    phone: str = Field(min_length=3, max_length=64)


def _job_title_payload(row: JobTitle, score: float | None = None) -> dict:
    payload = {"id": row.id, "name": row.name}
    if score is not None:
        payload["score"] = round(score, 3)
    return payload


@router.get("/job-titles")
def list_job_titles(db: DbSession, q: str = "", limit: int = 8) -> list[dict]:
    limit = max(1, min(limit, 20))
    rows = search_job_titles(db, q, limit=limit)
    db.commit()
    return [_job_title_payload(row, score) for row, score in rows]


@router.post("/job-titles/resolve")
def resolve_job_title_endpoint(payload: JobTitleResolveIn, db: DbSession) -> dict:
    try:
        result = resolve_job_title(
            db,
            payload.name,
            confirm_similar=payload.confirmSimilar,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    item = result["item"]
    similar = result["similar"]
    db.commit()
    return {
        "status": result["status"],
        "item": _job_title_payload(item) if item is not None else None,
        "similar": [_job_title_payload(row, score) for row, score in similar],
    }


@router.post("/website/check")
def website_check(payload: WebsiteCheckIn) -> dict:
    result = check_website(payload.website)
    return {
        "state": result.state,
        "normalizedUrl": result.normalized_url,
        "message": result.message,
        "statusCode": result.status_code,
    }


@router.post("/phone/normalize")
def phone_normalize(payload: PhoneNormalizeIn) -> dict:
    try:
        result = normalize_phone(payload.phone, payload.country)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "e164": result.e164,
        "display": result.display,
        "phoneType": result.phone_type,
    }


class OnboardingCreateIn(CompanyLookupIn):
    displayName: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=500)
    referent: ReferentIn


def _verification_payload(result: OrganizationVerificationResult) -> dict:
    return {
        "state": result.state.value,
        "country": result.country,
        "taxIdType": result.tax_id_type,
        "taxId": result.tax_id,
        "source": result.source,
        "message": result.message,
        "checkedAt": result.checked_at,
        "developmentSimulation": result.development_simulation,
        "company": {
            "legalName": result.legal_name,
            "legalEntityType": result.legal_entity_type,
            "registryJurisdiction": result.registry_jurisdiction,
            "registryNumber": result.registry_number,
            "fiscalAddress": result.fiscal_address,
            "legalAddress": result.legal_address,
            "primaryActivity": result.primary_activity,
        },
    }


def _status_for(result: OrganizationVerificationResult) -> OrganizationOnboardingStatus:
    if result.state == VerificationState.VERIFIED:
        return OrganizationOnboardingStatus.COMPANY_VERIFIED
    if result.state == VerificationState.PENDING:
        return OrganizationOnboardingStatus.VERIFICATION_PENDING
    return OrganizationOnboardingStatus.REVIEW_REQUIRED


@router.get("/config")
def onboarding_config() -> dict:
    """P01 empieza con Argentina, pero expone el catálogo desde backend."""
    return {
        "countries": [
            {
                "code": "AR",
                "name": "Argentina",
                "dialCode": "+54",
                "taxIdTypes": [{"code": "CUIT", "name": "CUIT"}],
            }
        ],
        "actingCapacities": [
            {"code": item.value, "name": {
                OrganizationActingCapacity.LEGAL_REPRESENTATIVE: "Representante legal",
                OrganizationActingCapacity.PROXY: "Apoderado/a",
                OrganizationActingCapacity.AUTHORIZED_EMPLOYEE: "Empleado/a autorizado/a",
                OrganizationActingCapacity.OTHER: "Otro",
            }[item]}
            for item in OrganizationActingCapacity
        ],
        "emailVerificationImplemented": False,
        "devPurgeAllowed": settings.dev_account_purge_allowed,
    }


@router.post("/company/lookup")
def lookup_company(payload: CompanyLookupIn, db: DbSession) -> dict:
    result = verify_organization(
        country=payload.country,
        tax_id_type=payload.taxIdType,
        tax_id=payload.taxId,
    )
    response = _verification_payload(result)

    existing_org = db.scalar(
        select(Organization).where(
            Organization.country == result.country,
            Organization.tax_id == result.tax_id,
        )
    )
    active_onboarding = db.scalar(
        select(OrganizationOnboarding)
        .where(
            OrganizationOnboarding.country == result.country,
            OrganizationOnboarding.tax_id_type == result.tax_id_type,
            OrganizationOnboarding.tax_id == result.tax_id,
            OrganizationOnboarding.status.notin_([
                OrganizationOnboardingStatus.ABANDONED,
                OrganizationOnboardingStatus.PROVISIONED,
            ]),
        )
        .order_by(OrganizationOnboarding.created_at.desc())
        .limit(1)
    )

    response["platform"] = {
        "alreadyRegistered": existing_org is not None,
        "onboardingInProgress": active_onboarding is not None,
        "onboardingPublicId": (
            active_onboarding.public_id if active_onboarding is not None else None
        ),
    }
    return response


@router.post("", status_code=status.HTTP_201_CREATED)
def create_onboarding(payload: OnboardingCreateIn, db: DbSession) -> dict:
    if not payload.referent.authorityDeclared:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Debés declarar que contás con autorización suficiente para iniciar el alta.",
        )

    result = verify_organization(
        country=payload.country,
        tax_id_type=payload.taxIdType,
        tax_id=payload.taxId,
    )
    if (
        result.state == VerificationState.REVIEW_REQUIRED
        and result.source == "LOCAL_VALIDATION"
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result.message)

    existing_org = db.scalar(
        select(Organization).where(
            Organization.country == result.country,
            Organization.tax_id == result.tax_id,
        )
    )
    if existing_org is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esa organización ya existe en Librería Inglés.",
        )

    existing_onboarding = db.scalar(
        select(OrganizationOnboarding)
        .where(
            OrganizationOnboarding.country == result.country,
            OrganizationOnboarding.tax_id_type == result.tax_id_type,
            OrganizationOnboarding.tax_id == result.tax_id,
            OrganizationOnboarding.status.notin_([
                OrganizationOnboardingStatus.ABANDONED,
                OrganizationOnboardingStatus.PROVISIONED,
            ]),
        )
        .order_by(OrganizationOnboarding.created_at.desc())
        .limit(1)
    )
    if existing_onboarding is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe una solicitud de alta en curso para esta organización.",
        )

    job_title = (
        get_job_title(db, payload.referent.jobTitleId)
        if payload.referent.jobTitleId is not None
        else None
    )
    if payload.referent.jobTitleId is not None and job_title is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "El cargo o función seleccionado ya no está disponible.",
        )

    if job_title is None:
        resolved_title = resolve_job_title(
            db,
            payload.referent.jobTitle,
            confirm_similar=False,
        )
        if resolved_title["status"] == "SIMILAR":
            candidates = ", ".join(
                row.name for row, _ in resolved_title["similar"][:3]
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"El cargo se parece a opciones existentes: {candidates}. Seleccioná una o confirmá el alta.",
            )
        job_title = resolved_title["item"]

    website: str | None = None
    if payload.website and payload.website.strip():
        try:
            website = normalize_website(payload.website)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    try:
        phone = normalize_phone(payload.referent.phone, result.country)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    display_name = (payload.displayName or "").strip() or result.legal_name
    onboarding = OrganizationOnboarding(
        status=_status_for(result),
        country=result.country,
        tax_id_type=result.tax_id_type,
        tax_id=result.tax_id,
        legal_name=result.legal_name,
        display_name=display_name,
        legal_entity_type=result.legal_entity_type,
        registry_jurisdiction=result.registry_jurisdiction,
        registry_number=result.registry_number,
        fiscal_address=result.fiscal_address,
        legal_address=result.legal_address,
        primary_activity=result.primary_activity,
        website=website,
        contact_first_name=payload.referent.firstName.strip(),
        contact_last_name=payload.referent.lastName.strip(),
        contact_email=str(payload.referent.email).strip().lower(),
        contact_job_title_id=job_title.id,
        contact_job_title=job_title.name,
        contact_phone=phone.e164,
        acting_capacity=payload.referent.actingCapacity,
        authority_declared=True,
        verification_source=result.source,
        verification_message=result.message,
        verification_checked_at=result.checked_at,
        official_data=result.official_data,
        last_activity_at=utcnow(),
    )
    db.add(onboarding)
    db.commit()
    db.refresh(onboarding)

    if onboarding.status == OrganizationOnboardingStatus.COMPANY_VERIFIED:
        next_step = "EMAIL_VERIFICATION_PENDING_P02"
    elif onboarding.status == OrganizationOnboardingStatus.VERIFICATION_PENDING:
        next_step = "COMPANY_VERIFICATION_PENDING"
    else:
        next_step = "MANUAL_REVIEW_REQUIRED"

    return {
        "publicId": onboarding.public_id,
        "status": onboarding.status.value,
        "company": {
            "country": onboarding.country,
            "taxIdType": onboarding.tax_id_type,
            "taxId": onboarding.tax_id,
            "legalName": onboarding.legal_name,
            "displayName": onboarding.display_name,
            "legalEntityType": onboarding.legal_entity_type,
            "registryJurisdiction": onboarding.registry_jurisdiction,
            "registryNumber": onboarding.registry_number,
            "fiscalAddress": onboarding.fiscal_address,
            "legalAddress": onboarding.legal_address,
            "primaryActivity": onboarding.primary_activity,
            "website": onboarding.website,
        },
        "referent": {
            "firstName": onboarding.contact_first_name,
            "lastName": onboarding.contact_last_name,
            "email": onboarding.contact_email,
            "jobTitleId": onboarding.contact_job_title_id,
            "jobTitle": onboarding.contact_job_title,
            "phone": onboarding.contact_phone,
            "actingCapacity": onboarding.acting_capacity.value,
            "emailVerified": False,
        },
        "verification": {
            "source": onboarding.verification_source,
            "message": onboarding.verification_message,
            "checkedAt": onboarding.verification_checked_at,
            "developmentSimulation": result.development_simulation,
        },
        "nextStep": next_step,
    }


@router.delete("/dev-purge")
def dev_purge_onboarding(
    country: str,
    taxIdType: str,
    taxId: str,
    db: DbSession,
) -> dict:
    """Borra físicamente onboardings de prueba por identificación fiscal.

    Solo local/dev/test. Nunca elimina una Organization provisionada.
    """
    if not settings.dev_account_purge_allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No disponible.")

    normalized_country = country.strip().upper()
    normalized_tax_id_type = taxIdType.strip().upper()
    normalized_tax_id = normalize_tax_id(taxId)

    existing_org = db.scalar(
        select(Organization).where(
            Organization.country == normalized_country,
            Organization.tax_id == normalized_tax_id,
        )
    )
    if existing_org is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El CUIT pertenece a una organización ya provisionada. Esta herramienta no elimina organizaciones reales.",
        )

    rows = db.scalars(
        select(OrganizationOnboarding).where(
            OrganizationOnboarding.country == normalized_country,
            OrganizationOnboarding.tax_id_type == normalized_tax_id_type,
            OrganizationOnboarding.tax_id == normalized_tax_id,
        )
    ).all()

    deleted = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()

    return {
        "country": normalized_country,
        "taxIdType": normalized_tax_id_type,
        "taxId": normalized_tax_id,
        "deletedOnboardings": deleted,
    }
