from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib

from app.core.config import settings


@dataclass(frozen=True)
class EmailDeliveryMessage:
    recipient: str
    subject: str
    body: str
    sender_profile: str


@dataclass(frozen=True)
class EmailDeliveryResult:
    provider: str
    accepted: bool
    development_capture: str | None = None


class EmailDeliveryProvider:
    def send(
        self,
        message: EmailDeliveryMessage,
        *,
        development_capture: str | None = None,
    ) -> EmailDeliveryResult:
        raise NotImplementedError


class DevelopmentEmailDeliveryProvider(EmailDeliveryProvider):
    def send(
        self,
        message: EmailDeliveryMessage,
        *,
        development_capture: str | None = None,
    ) -> EmailDeliveryResult:
        if settings.is_production:
            raise RuntimeError("El provider DEV de email no está permitido en producción.")
        return EmailDeliveryResult(
            provider="DEV",
            accepted=True,
            development_capture=development_capture,
        )


class SmtpEmailDeliveryProvider(EmailDeliveryProvider):
    def send(
        self,
        message: EmailDeliveryMessage,
        *,
        development_capture: str | None = None,
    ) -> EmailDeliveryResult:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise RuntimeError("SMTP no está configurado completamente.")

        email = EmailMessage()
        email["To"] = message.recipient
        email["From"] = formataddr(
            (settings.smtp_from_name, settings.smtp_from_email)
        ) if settings.smtp_from_name else settings.smtp_from_email
        email["Subject"] = message.subject
        email.set_content(message.body)

        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as client:
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls()
                client.ehlo()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(email)

        return EmailDeliveryResult(provider="SMTP", accepted=True)


def get_email_delivery_provider() -> EmailDeliveryProvider:
    provider = settings.email_delivery_provider.strip().lower()
    if provider == "dev":
        return DevelopmentEmailDeliveryProvider()
    if provider == "smtp":
        return SmtpEmailDeliveryProvider()
    raise RuntimeError(f"Provider de email no soportado: {settings.email_delivery_provider}")
