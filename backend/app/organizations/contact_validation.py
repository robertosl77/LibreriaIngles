from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType


class WebsiteUnreachableError(ValueError):
    pass


@dataclass(frozen=True)
class WebsiteCheckResult:
    state: str
    normalized_url: str | None
    message: str
    status_code: int | None = None


@dataclass(frozen=True)
class PhoneNormalizationResult:
    e164: str
    display: str
    phone_type: str


def normalize_website(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("Ingresá el sitio web de la organización.")

    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("El sitio web debe usar HTTP o HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("El sitio web no puede incluir usuario ni contraseña.")

    host = (parsed.hostname or "").strip().rstrip(".")
    if not host or "." not in host:
        raise ValueError("Ingresá un dominio válido, por ejemplo empresa.com.ar.")

    try:
        host_ascii = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("El dominio ingresado no es válido.") from exc

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("El puerto indicado en el sitio web no es válido.") from exc

    if port not in {None, 80, 443}:
        raise ValueError("Para el sitio web sólo se admiten los puertos estándar 80 y 443.")

    netloc = host_ascii
    if port is not None:
        netloc = f"{netloc}:{port}"

    path = parsed.path or ""
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _ensure_public_host(url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise ValueError("El sitio web no tiene un dominio válido.")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("El puerto indicado en el sitio web no es válido.") from exc

    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebsiteUnreachableError("No pudimos encontrar ese dominio en Internet en este momento.") from exc

    ips = {entry[4][0] for entry in addresses}
    if not ips:
        raise WebsiteUnreachableError("No pudimos encontrar ese dominio en Internet en este momento.")

    for raw_ip in ips:
        ip = ipaddress.ip_address(raw_ip)
        if not ip.is_global:
            raise ValueError("Por seguridad, el sitio debe resolver a una dirección pública de Internet.")


def check_website(value: str) -> WebsiteCheckResult:
    """Valida sintaxis y resolución DNS sin hacer requests al host arbitrario.

    Evitamos convertir este endpoint público en un proxy/SSRF. La disponibilidad HTTP real
    puede variar aunque el dominio exista.
    """
    try:
        normalized = normalize_website(value)
    except ValueError as exc:
        return WebsiteCheckResult("INVALID", None, str(exc))

    try:
        _ensure_public_host(normalized)
    except WebsiteUnreachableError:
        return WebsiteCheckResult(
            "UNREACHABLE",
            normalized,
            "No pudimos confirmar ese dominio en este momento.",
        )
    except ValueError as exc:
        return WebsiteCheckResult("INVALID", None, str(exc))

    return WebsiteCheckResult(
        "VERIFIED",
        normalized,
        "Dominio encontrado en Internet.",
    )


def normalize_phone(value: str, country: str = "AR") -> PhoneNormalizationResult:
    raw = value.strip()
    if not raw:
        raise ValueError("Ingresá un teléfono de contacto.")

    region = country.upper().strip() or "AR"
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("No pudimos interpretar el teléfono. Revisá código de área y número.") from exc

    if not phonenumbers.is_possible_number(number):
        raise ValueError("El teléfono tiene una cantidad de dígitos inválida.")
    if not phonenumbers.is_valid_number(number):
        raise ValueError("El teléfono no corresponde a una numeración válida para el país seleccionado.")

    kind = phonenumbers.number_type(number)
    kind_name = {
        PhoneNumberType.MOBILE: "MOBILE",
        PhoneNumberType.FIXED_LINE: "FIXED_LINE",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "FIXED_OR_MOBILE",
    }.get(kind, "OTHER")

    return PhoneNormalizationResult(
        e164=phonenumbers.format_number(number, PhoneNumberFormat.E164),
        display=phonenumbers.format_number(number, PhoneNumberFormat.INTERNATIONAL),
        phone_type=kind_name,
    )
