import socket

import pytest

from app.organizations.contact_validation import (
    check_website,
    normalize_phone,
    normalize_website,
)
from app.organizations.verification import argentina_cuit_error


def test_cuit_reports_length_and_invalid_value_separately() -> None:
    assert "11" in argentina_cuit_error("30-1234")
    assert "12 dígitos" in argentina_cuit_error("30-123456789-1")
    assert "no es válido" in argentina_cuit_error("30-12345678-2")
    assert "no es válido" in argentina_cuit_error("31-12345678-1")
    assert argentina_cuit_error("30-12345678-1") is None


def test_cuit_tolerates_spaces_and_hyphens_but_not_dots() -> None:
    assert argentina_cuit_error("30 - 12345678 - 1") is None
    assert "números, espacios o guiones" in argentina_cuit_error("30.12345678.1")


def test_website_adds_https_when_user_enters_only_domain() -> None:
    assert normalize_website("cacatua.com.ar") == "https://cacatua.com.ar"
    assert normalize_website("www.cacatua.com.ar") == "https://www.cacatua.com.ar"
    assert normalize_website("https://cacatua.com.ar") == "https://cacatua.com.ar"


def test_website_rejects_non_web_schemes_and_nonstandard_ports() -> None:
    with pytest.raises(ValueError, match="HTTP o HTTPS"):
        normalize_website("ftp://cacatua.com.ar")
    with pytest.raises(ValueError, match="puertos estándar"):
        normalize_website("https://cacatua.com.ar:8080")


def test_website_check_only_accepts_public_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
    result = check_website("cacatua.com.ar")
    assert result.state == "VERIFIED"
    assert result.normalized_url == "https://cacatua.com.ar"
    assert result.message == "Dominio encontrado en Internet."


def test_website_check_does_not_block_on_transient_dns_failure(monkeypatch) -> None:
    def fail_dns(*args, **kwargs):
        raise socket.gaierror("temporary failure")

    monkeypatch.setattr(socket, "getaddrinfo", fail_dns)
    result = check_website("cacatua.com.ar")
    assert result.state == "UNREACHABLE"
    assert result.normalized_url == "https://cacatua.com.ar"
    assert result.message == "No pudimos confirmar ese dominio en este momento."
    assert "continuar" not in result.message.lower()


def test_website_check_rejects_private_dns_target(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    result = check_website("interno.example")
    assert result.state == "INVALID"
    assert "dirección pública" in result.message


def test_argentina_phone_is_normalized_to_e164() -> None:
    result = normalize_phone("+54 9 11 2345-6789", "AR")
    assert result.e164 == "+5491123456789"
    assert result.display.startswith("+54")
    assert result.phone_type in {"MOBILE", "FIXED_OR_MOBILE"}


def test_invalid_phone_has_spanish_error() -> None:
    with pytest.raises(ValueError, match="cantidad de dígitos|numeración válida"):
        normalize_phone("123", "AR")
