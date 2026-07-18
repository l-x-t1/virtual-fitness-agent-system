from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError, AuthenticationError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories import FitnessRepository, session_scope


def public_user(user: dict) -> dict:
    return {key: value for key, value in user.items() if key != "password"}


def token_payload(user: dict) -> dict:
    token, expires_at = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": public_user(user),
    }


def login(username: str, password: str) -> dict:
    with session_scope() as session:
        repo = FitnessRepository(session)
        user = repo.user_by_username(username)
        if not user:
            raise AuthenticationError("用户名或密码错误")
        valid, needs_upgrade = verify_password(password, user["password"])
        if not valid:
            raise AuthenticationError("用户名或密码错误")
        if needs_upgrade:
            repo.update_user_password(user["id"], hash_password(password))
            user["password"] = ""
        return token_payload(user)


def register(username: str, password: str, nickname: str) -> dict:
    try:
        with session_scope() as session:
            repo = FitnessRepository(session)
            user_id = repo.create_user(username.strip(), hash_password(password), nickname.strip())
            return token_payload(repo.user_by_id(user_id))
    except IntegrityError as exc:
        raise AppError("用户名已存在", 409, "CONFLICT") from exc
