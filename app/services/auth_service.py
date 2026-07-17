from database import execute, get_row

from app.core.exceptions import AppError, AuthenticationError
from app.core.security import create_access_token, hash_password, verify_password


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
    user = get_row("SELECT * FROM users WHERE username = ?", (username.strip(),))
    if not user:
        raise AuthenticationError("用户名或密码错误")
    valid, needs_upgrade = verify_password(password, user["password"])
    if not valid:
        raise AuthenticationError("用户名或密码错误")
    if needs_upgrade:
        execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(password), user["id"]))
        user["password"] = ""
    return token_payload(user)


def register(username: str, password: str, nickname: str) -> dict:
    try:
        user_id = execute(
            "INSERT INTO users(username, password, nickname) VALUES (?, ?, ?)",
            (username.strip(), hash_password(password), nickname.strip()),
        )
    except Exception as exc:
        raise AppError("用户名已存在", 409, "CONFLICT") from exc
    return token_payload(get_row("SELECT * FROM users WHERE id = ?", (user_id,)))
