"""API Key management endpoints for the Developer Portal."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key import generate_api_key
from app.db.session import get_db
from app.deps import get_current_user
from app.models.api_key import ApiKey
from app.models.user import User

router = APIRouter()


class ApiKeyResponse(BaseModel):
    """Public info about an API key (never includes the raw key)."""

    id: int
    key_prefix: str
    name: str
    is_active: bool
    last_used_at: str | None
    created_at: str


class ApiKeyCreatedResponse(BaseModel):
    """Returned when a new key is created — raw_key shown only once."""

    id: int
    key_prefix: str
    name: str
    raw_key: str
    is_active: bool
    created_at: str


class CreateApiKeyBody(BaseModel):
    name: str | None = "default"


class UpdateApiKeyBody(BaseModel):
    name: str | None = None
    is_active: bool | None = None


def _format_dt(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyResponse]:
    """List all API keys for the authenticated user."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=k.id,
            key_prefix=k.key_prefix,
            name=k.name,
            is_active=k.is_active,
            last_used_at=_format_dt(k.last_used_at),
            created_at=_format_dt(k.created_at),
        )
        for k in keys
    ]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreatedResponse:
    """Generate a new API key.

    The raw key is returned only once in this response.
    Store it securely — it cannot be retrieved again.
    """
    pair = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        key_prefix=pair.key_prefix,
        hashed_key=pair.hashed_key,
        name=body.name or "default",
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyCreatedResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        raw_key=pair.raw_key,
        is_active=api_key.is_active,
        created_at=_format_dt(api_key.created_at),
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke (delete) an API key by ID."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.delete(api_key)
    await db.commit()


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: int,
    body: UpdateApiKeyBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyResponse:
    """Update API key name or active status."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if body.name is not None:
        api_key.name = body.name
    if body.is_active is not None:
        api_key.is_active = body.is_active
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        is_active=api_key.is_active,
        last_used_at=_format_dt(api_key.last_used_at),
        created_at=_format_dt(api_key.created_at),
    )
