"""Password hashing + JWT primitives."""

from jose import jwt

from utils import security


def test_hash_and_verify_roundtrip():
    h = security.get_password_hash("supersecret123")
    assert h != "supersecret123"
    assert security.verify_password("supersecret123", h) is True
    assert security.verify_password("wrong", h) is False


def test_password_over_72_bytes_does_not_crash():
    # bcrypt's 72-byte limit must be handled, not raised.
    long_pw = "a" * 200
    h = security.get_password_hash(long_pw)
    assert security.verify_password(long_pw, h) is True


def test_verify_handles_garbage_hash():
    assert security.verify_password("x", "not-a-bcrypt-hash") is False


def test_token_roundtrip():
    token = security.create_access_token({"sub": "42"})
    payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
    assert payload["sub"] == "42"
    assert "exp" in payload
