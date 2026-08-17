"""Authentication dependency for the personal internal tool.

The whole API is protected by a single static token from settings
(env var ``API_TOKEN``), passed either in the ``X-Api-Token`` header
or as ``Authorization: Bearer <token>``.
No users, no API keys, no JWT.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import settings


def _token_matches(provided: str | None) -> bool:
    """Constant-time comparison of the provided token against the configured one."""
    if not provided:
        return False
    expected = settings.api_token.encode("utf-8")
    actual = provided.strip().encode("utf-8")
    return hmac.compare_digest(actual, expected)


def verify_api_token(
    x_api_token: Annotated[str | None, Header(alias="X-Api-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require the static API token via ``X-Api-Token`` or ``Authorization: Bearer``."""
    provided: str | None = None
    if x_api_token:
        provided = x_api_token
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization[len("Bearer "):]

    if not _token_matches(provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

