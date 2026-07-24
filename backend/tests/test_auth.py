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


def test_long_password_does_not_crash() -> None:
    # bcrypt 5+ raises on >72-byte inputs; hash/verify must truncate instead of
    # 500-ing register/login. A long passphrase and a multi-byte one both work.
    long_ascii = "a" * 200
    hashed = hash_password(long_ascii)
    assert verify_password(long_ascii, hashed)
    # First 72 bytes match, so the truncated forms verify the same (bcrypt's
    # own behavior) — the point is no exception is raised.
    assert verify_password("a" * 72, hashed)

    multibyte = "🔒" * 40  # 160 bytes
    hashed_mb = hash_password(multibyte)
    assert verify_password(multibyte, hashed_mb)


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
