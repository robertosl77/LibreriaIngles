from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib

from app.core.config import settings


SRMACROS_VALIDATION_SENDER = "SRMACROS_VALIDATION"
_SUPPORTED_SENDER_PROFILES = {SRMACROS_VALIDATION_SENDER}


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


@dataclass(frozen=True)
class EmailSenderIdentity:
    profile: str
    from_email: str
    from_name: str


def _require_known_sender_profile(profile: str) -> None:
    if profile not in _SUPPORTED_SENDER_PROFILES:
        raise RuntimeError(f"Perfil de remitente no soportado: {profile}")


def resolve_email_sender_identity(profile: str) -> EmailSenderIdentity:
    """Resuelve un perfil semántico a la identidad física del remitente actual.

    P02 inaugura un único perfil de plataforma. El caso de notificación sólo conoce
    el código del perfil; las credenciales y el proveedor permanecen fuera del dominio
    consumidor. #95 podrá ampliar este registro sin modificar el onboarding.
    """

    _require_known_sender_profile(profile)
    if profile == SRMACROS_VALIDATION_SENDER:
        if not settings.smtp_from_email:
            raise RuntimeError("El perfil SRMACROS_VALIDATION no tiene remitente SMTP configurado.")
        return EmailSenderIdentity(
            profile=profile,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name,
        )
    raise RuntimeError(f"Perfil de remitente no soportado: {profile}")


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
        _require_known_sender_profile(message.sender_profile)
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
        if not settings.smtp_host:
            raise RuntimeError("SMTP no está configurado completamente.")

        sender = resolve_email_sender_identity(message.sender_profile)
        email = EmailMessage()
        email["To"] = message.recipient
        email["From"] = (
            formataddr((sender.from_name, sender.from_email))
            if sender.from_name
            else sender.from_email
        )
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
