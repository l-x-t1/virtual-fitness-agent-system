from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.security import decode_access_token
from app.repositories import FitnessRepository, session_scope
from app.services.auth_service import public_user

bearer = HTTPBearer(
    auto_error=False,
    scheme_name="JWTBearer",
    description="Use the JWT access token returned by /api/login or /api/register.",
)


def get_token_payload(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing bearer token")
    return decode_access_token(credentials.credentials)


def get_current_user(payload: dict = Depends(get_token_payload)) -> dict:
    with session_scope() as session:
        user = FitnessRepository(session).user_by_id(int(payload["sub"]))
    if not user:
        raise AuthenticationError("User no longer exists")
    return public_user(user)


def require_roles(*roles: str) -> Callable[[dict], dict]:
    allowed = set(roles)

    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if allowed and user.get("role") not in allowed:
            raise PermissionDenied()
        return user

    return dependency


_admin_required = require_roles("admin")


def require_admin(user: dict = Depends(_admin_required)) -> dict:
    return user
