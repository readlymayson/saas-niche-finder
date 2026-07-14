from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key import _hash_api_key, verify_api_key
from app.core.security import decode_token
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("typ") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        email = payload.get("sub")
        if not isinstance(email, str):
            raise HTTPException(status_code=401, detail="Invalid token subject")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from None
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_api_key_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate via API Key (nf_... token) or fall back to JWT.

    API keys are passed as: Authorization: Bearer nf_<prefix>_<secret>
    JWT tokens also work for backward compatibility.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide API key or JWT as Bearer token.",
        )

    token = credentials.credentials

    # API Key authentication (keys start with "nf_")
    if token.startswith("nf_"):
        hashed = _hash_api_key(token)
        result = await db.execute(
            select(ApiKey).where(ApiKey.hashed_key == hashed, ApiKey.is_active.is_(True))
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key",
            )
        # Update last used timestamp
        api_key.last_used_at = datetime.now(UTC)
        await db.commit()

        result = await db.execute(select(User).where(User.id == api_key.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # Fallback to JWT authentication
    return await get_current_user(credentials, db)

