import jwt
import pytest
from pydantic import ValidationError

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.training import SessionSubmit


def test_password_hash_and_legacy_upgrade_signal():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) == (True, False)
    assert verify_password("123456", "123456") == (True, True)
    assert verify_password("wrong", "123456") == (False, False)


def test_access_token_contains_required_claims():
    token, expires_at = create_access_token({"id": 7, "role": "admin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "admin"
    assert {"iat", "exp", "jti"} <= payload.keys()
    assert expires_at == payload["exp"]


def test_tampered_token_is_rejected():
    token, _ = create_access_token({"id": 1, "role": "user"})
    with pytest.raises(Exception):
        decode_access_token(token + "invalid")


@pytest.mark.parametrize(
    "payload",
    [
        {"exercise_name": "", "score": 80, "duration": 60},
        {"exercise_name": "深蹲", "score": -1, "duration": 60},
        {"exercise_name": "深蹲", "score": 101, "duration": 60},
        {"exercise_name": "深蹲", "score": 80, "duration": 9},
    ],
)
def test_session_validation_rejects_invalid_values(payload):
    with pytest.raises(ValidationError):
        SessionSubmit(**payload)


def test_session_validation_accepts_boundary_values():
    model = SessionSubmit(exercise_name="深蹲", score=100, duration=10)
    assert model.score == 100
