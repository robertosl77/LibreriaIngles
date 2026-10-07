from app.notifications.delivery import (
    DevelopmentEmailDeliveryProvider,
    EmailDeliveryMessage,
    SmtpEmailDeliveryProvider,
    SRMACROS_VALIDATION_SENDER,
)


def test_development_provider_accepts_builtin_sender_profile(monkeypatch) -> None:
    from app.notifications import delivery

    monkeypatch.setattr(delivery.settings, "app_env", "test")
    result = DevelopmentEmailDeliveryProvider().send(
        EmailDeliveryMessage(
            recipient="destino@example.com",
            subject="Código",
            body="Prueba",
            sender_profile=SRMACROS_VALIDATION_SENDER,
        ),
        development_capture="123456",
    )

    assert result.accepted is True
    assert result.provider == "DEV"
    assert result.development_capture == "123456"


def test_smtp_provider_resolves_sender_profile(monkeypatch) -> None:
    from app.notifications import delivery

    sent: dict[str, object] = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(delivery.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(delivery.settings, "smtp_port", 587)
    monkeypatch.setattr(delivery.settings, "smtp_timeout_seconds", 10.0)
    monkeypatch.setattr(delivery.settings, "smtp_starttls", True)
    monkeypatch.setattr(delivery.settings, "smtp_username", "usuario")
    monkeypatch.setattr(delivery.settings, "smtp_password", "secreto")
    monkeypatch.setattr(delivery.settings, "smtp_from_email", "validacion@example.com")
    monkeypatch.setattr(delivery.settings, "smtp_from_name", "Sr. Marcos")
    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSmtp)

    result = SmtpEmailDeliveryProvider().send(
        EmailDeliveryMessage(
            recipient="destino@example.com",
            subject="Código",
            body="Tu código es 123456",
            sender_profile=SRMACROS_VALIDATION_SENDER,
        )
    )

    assert result.accepted is True
    assert result.provider == "SMTP"
    assert sent["host"] == "smtp.example.com"
    assert sent["starttls"] is True
    assert sent["login"] == ("usuario", "secreto")
    message = sent["message"]
    assert message["To"] == "destino@example.com"
    assert "validacion@example.com" in message["From"]
    assert message["Subject"] == "Código"
