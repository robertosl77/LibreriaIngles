from sqlalchemy import select

from app.core.config import settings
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
        "subject_template": "Código de verificación de {brand}",
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


def seed_notification_cases(db) -> None:
    """T-220 (E-04): los casos base se siembran al arrancar (bootstrap), no al leerlos."""
    existing = set(db.scalars(select(NotificationCase.code)).all())
    for code, definition in _BUILTIN_CASES.items():
        if code not in existing:
            db.add(NotificationCase(code=code, **definition))
    db.flush()


def get_notification_case(db, code: str) -> NotificationCase:
    row = db.scalar(select(NotificationCase).where(NotificationCase.code == code))
    if row is not None:
        if not row.active:
            raise RuntimeError(f"El caso de notificación {code} está deshabilitado.")
        return row

    definition = _BUILTIN_CASES.get(code)
    if definition is None:
        raise RuntimeError(f"Caso de notificación desconocido: {code}")
    # Sin sembrar todavía: se usa la definición base en memoria (la lectura no escribe).
    return NotificationCase(code=code, **definition)


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

    # T-220 (E-13): la marca es una variable más, disponible en todas las plantillas.
    variables = {"brand": settings.brand_name, **variables}
    message = EmailDeliveryMessage(
        recipient=recipient,
        subject=_render(case.subject_template, variables),
        body=_render(case.body_template, variables),
        sender_profile=case.sender_profile,
    )
    provider = get_email_delivery_provider()
    return provider.send(message, development_capture=development_capture)
