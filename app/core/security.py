from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError

ACCESS_TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def is_password_hash(value: str) -> bool:
    return value.startswith(("$2a$", "$2b$", "$2y$"))


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    if is_password_hash(stored):
        return bcrypt.checkpw(password.encode(), stored.encode()), False
    return password == stored, password == stored


def create_access_token(user: dict[str, Any]) -> tuple[str, int]:
    user_id = user.get("id")
    if user_id is None:
        raise ValueError("user id is required to create access token")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": user.get("role", "user"),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "nbf": now,
        "exp": expires,
        "jti": str(uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.timestamp())


def decode_access_token(token: str) -> dict[str, Any]:
    if not token:
        raise AuthenticationError("Missing bearer token")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "jti", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AuthenticationError("Invalid token type")
    try:
        int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid token subject") from exc
    return payload
