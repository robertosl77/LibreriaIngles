from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class OrganizationVerificationResult:
    state: VerificationState
    country: str
    tax_id_type: str
    tax_id: str
    source: str
    message: str
    checked_at: datetime
    legal_name: str | None = None
    legal_entity_type: str | None = None
    registry_jurisdiction: str | None = None
    registry_number: str | None = None
    fiscal_address: str | None = None
    legal_address: str | None = None
    primary_activity: str | None = None
    official_data: dict | None = None
    development_simulation: bool = False


class OrganizationVerificationProvider(Protocol):
    def lookup(self, *, country: str, tax_id_type: str, tax_id: str) -> OrganizationVerificationResult:
        ...


def normalize_tax_id(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_valid_argentina_cuit(value: str) -> bool:
    digits = normalize_tax_id(value)
    if len(digits) != 11:
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(digit) * weight for digit, weight in zip(digits[:10], weights, strict=True))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(digits[-1])


class DevelopmentArgentinaVerificationProvider:
    """Simulación explícita para probar P01 sin credenciales de ARCA/RNS.

    Nunca debe habilitarse en production. No afirma que los datos sean reales.
    """

    def lookup(self, *, country: str, tax_id_type: str, tax_id: str) -> OrganizationVerificationResult:
        normalized = normalize_tax_id(tax_id)
        suffix = normalized[-4:]
        official = {
            "developmentSimulation": True,
            "country": "AR",
            "taxIdType": "CUIT",
            "taxId": normalized,
            "legalName": f"EMPRESA DE PRUEBA {suffix} S.A.",
            "legalEntityType": "SOCIEDAD ANONIMA",
            "registryJurisdiction": "SIMULACION DEV",
            "registryNumber": f"DEV-{suffix}",
            "fiscalAddress": "Domicilio fiscal simulado para desarrollo",
            "legalAddress": "Domicilio legal simulado para desarrollo",
            "primaryActivity": "Actividad simulada para desarrollo",
        }
        return OrganizationVerificationResult(
            state=VerificationState.VERIFIED,
            country=country,
            tax_id_type=tax_id_type,
            tax_id=normalized,
            source="DEV_MOCK",
            message=(
                "DEV: verificación empresarial simulada. "
                "Los datos mostrados no provienen de ARCA ni de un registro oficial."
            ),
            checked_at=utcnow(),
            legal_name=official["legalName"],
            legal_entity_type=official["legalEntityType"],
            registry_jurisdiction=official["registryJurisdiction"],
            registry_number=official["registryNumber"],
            fiscal_address=official["fiscalAddress"],
            legal_address=official["legalAddress"],
            primary_activity=official["primaryActivity"],
            official_data=official,
            development_simulation=True,
        )


class PendingArgentinaVerificationProvider:
    """Placeholder de producción hasta conectar un proveedor oficial autenticado."""

    def lookup(self, *, country: str, tax_id_type: str, tax_id: str) -> OrganizationVerificationResult:
        return OrganizationVerificationResult(
            state=VerificationState.PENDING,
            country=country,
            tax_id_type=tax_id_type,
            tax_id=normalize_tax_id(tax_id),
            source="AR_OFFICIAL_PENDING",
            message=(
                "La estructura del CUIT es válida. "
                "La verificación contra una fuente oficial todavía no está configurada."
            ),
            checked_at=utcnow(),
        )


def provider_for(country: str, tax_id_type: str) -> OrganizationVerificationProvider:
    country = country.upper().strip()
    tax_id_type = tax_id_type.upper().strip()
    if country != "AR" or tax_id_type != "CUIT":
        raise ValueError("P01 solo habilita Argentina + CUIT en la interfaz inicial.")
    if settings.organization_verification_mock_allowed:
        return DevelopmentArgentinaVerificationProvider()
    return PendingArgentinaVerificationProvider()


def verify_organization(*, country: str, tax_id_type: str, tax_id: str) -> OrganizationVerificationResult:
    country = country.upper().strip()
    tax_id_type = tax_id_type.upper().strip()
    normalized = normalize_tax_id(tax_id)

    if country == "AR" and tax_id_type == "CUIT" and not is_valid_argentina_cuit(normalized):
        return OrganizationVerificationResult(
            state=VerificationState.REVIEW_REQUIRED,
            country=country,
            tax_id_type=tax_id_type,
            tax_id=normalized,
            source="LOCAL_VALIDATION",
            message="El CUIT no supera la validación de formato y dígito verificador.",
            checked_at=utcnow(),
        )

    try:
        provider = provider_for(country, tax_id_type)
    except ValueError as exc:
        return OrganizationVerificationResult(
            state=VerificationState.REVIEW_REQUIRED,
            country=country,
            tax_id_type=tax_id_type,
            tax_id=normalized,
            source="LOCAL_VALIDATION",
            message=str(exc),
            checked_at=utcnow(),
        )
    return provider.lookup(country=country, tax_id_type=tax_id_type, tax_id=normalized)
