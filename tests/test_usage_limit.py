from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.usage_limit import enforce_niche_view_quota, reset_memory_views_for_tests


@pytest.fixture(autouse=True)
def _clear_views() -> None:
    reset_memory_views_for_tests()
    yield
    reset_memory_views_for_tests()


def _user(*, pro: bool = False) -> User:
    u = User(id=1, email="u@test.com", hashed_password="x")
    if pro:
        u.subscription_plan = "pro"
        u.subscription_status = "active"
    return u


@pytest.mark.asyncio
async def test_free_tier_blocks_after_limit() -> None:
    user = _user()
    for _ in range(5):
        await enforce_niche_view_quota(user)
    with pytest.raises(HTTPException) as exc:
        await enforce_niche_view_quota(user)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_pro_unlimited() -> None:
    user = _user(pro=True)
    for _ in range(20):
        await enforce_niche_view_quota(user)
