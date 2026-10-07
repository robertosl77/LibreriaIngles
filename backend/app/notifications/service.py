from sqlalchemy import select

from app.notifications.delivery import (
    EmailDeliveryMessage,
    SRMACROS_VALIDATION_SENDER,
    get_email_delivery_provider,
)
from app.notifications.models import NotificationCase


ORGANIZATION_EMAIL_VERIFICATION = "ORGANIZATION_EMAIL_VERIFICATION"

_BUILTIN_CASES: dict[str, dict[str, object]] = {
    ORGANIZATION_EMAIL_VERIFICATION: {
        "channel": "EMAIL",
        "subject_template": "Código de verificación de Librería Inglés",
        "body_template": (
            "Hola {first_name},\n\n"
            "Tu código de verificación es: {code}\n\n"
            "El código vence en {expiration_minutes} minutos.\n"
            "Si no iniciaste este trámite, podés ignorar este mensaje.\n"
        ),
        "sender_profile": SRMACROS_VALIDATION_SENDER,
        "platform_only": True,
        "organization_override_allowed": False,
        "active": True,
    }
}


def get_notification_case(db, code: str) -> NotificationCase:
    row = db.scalar(select(NotificationCase).where(NotificationCase.code == code))
    if row is not None:
        if not row.active:
            raise RuntimeError(f"El caso de notificación {code} está deshabilitado.")
        return row

    definition = _BUILTIN_CASES.get(code)
    if definition is None:
        raise RuntimeError(f"Caso de notificación desconocido: {code}")

    row = NotificationCase(code=code, **definition)
    db.add(row)
    db.flush()
    return row


def _render(template: str, variables: dict[str, object]) -> str:
    try:
        return template.format_map(variables)
    except KeyError as exc:
        raise RuntimeError(
            f"Falta la variable {exc.args[0]} para renderizar la notificación."
        ) from exc


def send_notification(
    db,
    *,
    code: str,
    recipient: str,
    variables: dict[str, object],
    development_capture: str | None = None,
):
    case = get_notification_case(db, code)
    if case.channel != "EMAIL":
        raise RuntimeError(f"Canal no soportado para {code}: {case.channel}")

    message = EmailDeliveryMessage(
        recipient=recipient,
        subject=_render(case.subject_template, variables),
        body=_render(case.body_template, variables),
        sender_profile=case.sender_profile,
    )
    provider = get_email_delivery_provider()
    return provider.send(message, development_capture=development_capture)
