from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType


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

    port = parsed.port
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
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("No pudimos resolver el dominio en Internet.") from exc

    ips = {entry[4][0] for entry in addresses}
    if not ips:
        raise ValueError("No pudimos resolver el dominio en Internet.")

    for raw_ip in ips:
        ip = ipaddress.ip_address(raw_ip)
        if not ip.is_global:
            raise ValueError("Por seguridad, el sitio debe resolver a una dirección pública de Internet.")


def check_website(value: str) -> WebsiteCheckResult:
    try:
        current = normalize_website(value)
        _ensure_public_host(current)
    except ValueError as exc:
        return WebsiteCheckResult("INVALID", None, str(exc))

    attempts = [current]
    if current.startswith("https://"):
        attempts.append("http://" + current.removeprefix("https://"))

    last_error = "El sitio no respondió dentro del tiempo esperado."
    for initial in attempts:
        target = initial
        try:
            with httpx.Client(
                timeout=httpx.Timeout(5.0),
                follow_redirects=False,
                trust_env=False,
                headers={"User-Agent": "LibreriaIngles/0.1 website-check"},
            ) as client:
                for _ in range(5):
                    _ensure_public_host(target)
                    with client.stream("GET", target) as response:
                        code = response.status_code
                        location = response.headers.get("location")

                    if code in {301, 302, 303, 307, 308} and location:
                        candidate = normalize_website(urljoin(target, location))
                        _ensure_public_host(candidate)
                        target = candidate
                        continue

                    message = "El sitio respondió correctamente."
                    if target.startswith("http://"):
                        message = "El sitio responde, pero no pudimos confirmar HTTPS."
                    return WebsiteCheckResult(
                        "VERIFIED",
                        target,
                        message,
                        status_code=code,
                    )
                last_error = "El sitio redirige demasiadas veces."
        except (httpx.HTTPError, ValueError) as exc:
            last_error = str(exc) or last_error

    return WebsiteCheckResult(
        "UNREACHABLE",
        current,
        "No pudimos confirmar el sitio ahora. Podés continuar y revisarlo más tarde.",
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
