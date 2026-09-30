"""Tokens de sesión (JWT) y cifrado de credenciales."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

JWT_ALGORITHM = "HS256"


class InvalidSessionToken(Exception):
    pass


def create_access_token(account_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(account_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidSessionToken() from exc


def _fernet() -> Fernet:
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode())

    if settings.is_production:
        raise RuntimeError("ENCRYPTION_KEY es obligatoria en production.")

    # Desarrollo: clave derivada del secreto JWT para no exigir configuración extra.
    digest = hashlib.sha256(f"enc:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            "No se pudo descifrar la credencial. ¿Cambió ENCRYPTION_KEY o JWT_SECRET?"
        ) from exc


def mask_secret(value: str) -> str:
    tail = value[-4:] if len(value) >= 8 else ""
    return f"••••••••{tail}"
