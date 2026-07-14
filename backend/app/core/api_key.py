"""API Key generation, hashing, and validation."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import NamedTuple

from app.config import settings


class ApiKeyPair(NamedTuple):
    """Raw key (shown once to user) + hashed key (stored in DB)."""

    raw_key: str
    hashed_key: str
    key_prefix: str


def generate_api_key() -> ApiKeyPair:
    """Generate a secure API key in format: nf_<prefix>_<raw_secret>.

    The raw key is returned once for the user. Only the hash is stored in DB.
    """
    prefix = secrets.token_hex(4)  # 8-character hex prefix
    raw_secret = secrets.token_hex(32)  # 64-character hex secret
    raw_key = f"nf_{prefix}_{raw_secret}"
    hashed_key = _hash_api_key(raw_key)
    return ApiKeyPair(raw_key=raw_key, hashed_key=hashed_key, key_prefix=prefix)


def _hash_api_key(raw_key: str) -> str:
    """SHA-256 HMAC hash of the API key using the JWT secret as a pepper."""
    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    """Constant-time comparison of a raw key against a stored hash."""
    expected = _hash_api_key(raw_key)
    return hmac.compare_digest(expected, hashed_key)


def extract_raw_key(authorization: str) -> str | None:
    """Extract raw API key from 'Authorization: Bearer nf_<prefix>_<secret>'.

    Returns None if the format is invalid.
    """
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("nf_"):
        return None
    return token
