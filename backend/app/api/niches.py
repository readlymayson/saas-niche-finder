from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import verify_api_token
from app.models.feedback import Feedback
from app.models.niche_idea import NicheIdea
from app.schemas.niches import (
    FeedbackCreate,
    FeedbackRead,
    NicheEntityExtractResponse,
    NicheRead,
)
from app.services.natasha_entities import NatashaEntityService

router = APIRouter()


@router.get("/niches/top", response_model=list[NicheRead])
async def get_top_niches(
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=100),
    min_score: float = Query(default=0.0),
) -> list[NicheRead]:
    rows = await db.execute(
        select(NicheIdea)
        .where(or_(NicheIdea.score.is_(None), NicheIdea.score >= min_score))
        .order_by(NicheIdea.score.desc().nullslast(), NicheIdea.id.desc())
        .limit(limit)
    )
    return [
        NicheRead(
            id=niche.id,
            slug=niche.slug,
            title=niche.title,
            summary=niche.summary,
            score=niche.score,
        )
        for niche in rows.scalars()
    ]


@router.get("/niches/search", response_model=list[NicheRead])
async def search_niches(
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(min_length=1, max_length=100),
) -> list[NicheRead]:
    needle = f"%{q.strip()}%"
    rows = await db.execute(
        select(NicheIdea)
        .where(or_(NicheIdea.title.ilike(needle), NicheIdea.summary.ilike(needle)))
        .order_by(NicheIdea.score.desc().nullslast(), NicheIdea.id.desc())
        .limit(50)
    )
    return [
        NicheRead(
            id=niche.id,
            slug=niche.slug,
            title=niche.title,
            summary=niche.summary,
            score=niche.score,
        )
        for niche in rows.scalars()
    ]


@router.get("/niches/{niche_id}", response_model=NicheRead)
async def get_niche(
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    niche_id: int,
) -> NicheRead:
    row = await db.execute(select(NicheIdea).where(NicheIdea.id == niche_id))
    niche = row.scalar_one_or_none()
    if niche is None:
        raise HTTPException(status_code=404, detail="Niche not found")
    return NicheRead(
        id=niche.id,
        slug=niche.slug,
        title=niche.title,
        summary=niche.summary,
        score=niche.score,
    )


@router.get("/niches/{niche_id}/similar", response_model=list[NicheRead])
async def similar_niches(
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    niche_id: int,
    limit: int = Query(default=5, ge=1, le=20),
) -> list[NicheRead]:
    base_q = await db.execute(select(NicheIdea).where(NicheIdea.id == niche_id))
    base = base_q.scalar_one_or_none()
    if base is None:
        raise HTTPException(status_code=404, detail="Niche not found")

    if base.embedding is not None:
        rows = await db.execute(
            select(NicheIdea)
            .where(NicheIdea.id != niche_id, NicheIdea.embedding.isnot(None))
            .order_by(
                NicheIdea.embedding.cosine_distance(base.embedding).asc(),
                NicheIdea.id.desc(),
            )
            .limit(limit)
        )
    else:
        rows = await db.execute(
            select(NicheIdea)
            .where(NicheIdea.id != niche_id)
            .order_by(
                func.abs(func.coalesce(NicheIdea.score, 0.0) - (base.score or 0.0)).asc(),
                NicheIdea.id.desc(),
            )
            .limit(limit)
        )
    return [
        NicheRead(
            id=niche.id,
            slug=niche.slug,
            title=niche.title,
            summary=niche.summary,
            score=niche.score,
        )
        for niche in rows.scalars()
    ]


@router.post("/feedback", response_model=FeedbackRead)
async def create_feedback(
    payload: FeedbackCreate,
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackRead:
    niche_q = await db.execute(select(NicheIdea).where(NicheIdea.id == payload.niche_id))
    niche = niche_q.scalar_one_or_none()
    if niche is None:
        raise HTTPException(status_code=404, detail="Niche not found")

    feedback = Feedback(
        niche_id=payload.niche_id,
        rating=payload.rating,
        comment=payload.comment,
        source=payload.source,
        score_snapshot=niche.score,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return FeedbackRead(
        id=feedback.id,
        niche_id=feedback.niche_id,
        rating=feedback.rating,
        comment=feedback.comment,
        source=feedback.source,
        score_snapshot=feedback.score_snapshot,
    )


@router.get("/niches/{niche_id}/entities", response_model=NicheEntityExtractResponse)
async def extract_niche_entities(
    niche_id: int,
    _: Annotated[None, Depends(verify_api_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NicheEntityExtractResponse:
    row = await db.execute(select(NicheIdea).where(NicheIdea.id == niche_id))
    niche = row.scalar_one_or_none()
    if niche is None:
        raise HTTPException(status_code=404, detail="Niche not found")
    service = NatashaEntityService()
    text = f"{niche.title}\n{niche.summary or ''}"
    entities = service.extract(text)
    return NicheEntityExtractResponse(
        organizations=entities.organizations,
        persons=entities.persons,
        locations=entities.locations,
    )
