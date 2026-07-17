from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.security import decode_access_token
from app.services.auth_service import public_user
from database import get_row

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("请先登录")
    payload = decode_access_token(credentials.credentials)
    user = get_row("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),))
    if not user:
        raise AuthenticationError()
    return public_user(user)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise PermissionDenied()
    return user
