"""Tests for auth utilities."""

from app.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    plain = "super-secret-123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip() -> None:
    token = create_access_token(subject="user-id-abc")
    payload = decode_token(token)
    assert payload["sub"] == "user-id-abc"
    assert payload["type"] == "access"


def test_decode_invalid_token_raises() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.jwt.token")
    assert exc_info.value.status_code == 401
