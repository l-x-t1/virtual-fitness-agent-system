from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.security import decode_access_token
from app.repositories import FitnessRepository, session_scope
from app.services.auth_service import public_user

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("请先登录")
    payload = decode_access_token(credentials.credentials)
    with session_scope() as session:
        user = FitnessRepository(session).user_by_id(int(payload["sub"]))
    if not user:
        raise AuthenticationError()
    return public_user(user)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise PermissionDenied()
    return user
