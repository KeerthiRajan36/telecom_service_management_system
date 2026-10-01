from datetime import timedelta

import pytest
from jose import JWTError, jwt

from app.core import security
from app.core.config import settings

security.pwd_context.update(bcrypt__rounds=4)


def test_password_hash_is_salted_and_verifiable():
    h1 = security.hash_password("Secret123!")
    h2 = security.hash_password("Secret123!")
    assert h1 != h2, "bcrypt must salt each hash"
    assert h1 != "Secret123!"
    assert security.verify_password("Secret123!", h1)
    assert not security.verify_password("wrong", h1)


def test_access_token_roundtrip_carries_role_and_type():
    token = security.create_access_token("user-1", "support_agent")
    payload = security.decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "support_agent"
    assert payload["type"] == security.TOKEN_TYPE_ACCESS


def test_refresh_token_carries_jti_and_type():
    payload = security.decode_token(security.create_refresh_token("user-1", "jti-123"))
    assert payload["jti"] == "jti-123"
    assert payload["type"] == security.TOKEN_TYPE_REFRESH


def test_reset_token_has_reset_type():
    assert security.decode_token(security.create_password_reset_token("u"))["type"] == security.TOKEN_TYPE_RESET


def test_expired_token_is_rejected():
    token = security._create_token("u", security.TOKEN_TYPE_ACCESS, timedelta(seconds=-5))
    with pytest.raises(JWTError):
        security.decode_token(token)


def test_tampered_token_is_rejected():
    token = security.create_access_token("u", "customer")
    with pytest.raises(JWTError):
        security.decode_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))


def test_token_signed_with_other_key_is_rejected():
    forged = jwt.encode({"sub": "u", "type": "access"}, "some-other-key", algorithm=settings.ALGORITHM)
    with pytest.raises(JWTError):
        security.decode_token(forged)
