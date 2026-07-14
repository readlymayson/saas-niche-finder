"""DaaS API v1 — Real endpoints backed by the ETL data pipeline."""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rate_limit import RedisRateLimiter, get_rate_limiter, RPM_LIMITS
from app.db.session import get_db
from app.db.vector import VectorType, cosine_distance
from app.deps import get_api_key_user
from app.models.niche import NicheIdea
from app.models.user import User

router = APIRouter()


# ──────────────────────────────────────────
# Pydantic response models (API contract)
# ──────────────────────────────────────────


class NichePainPoint(BaseModel):
    """A verified pain point extracted from real user comments."""

    text: str = Field(description="Original text of the pain point")
    source_url: str = Field(description="URL of the source post")
    source_title: str = Field(description="Title of the source post")
    author: str | None = Field(None, description="Comment author name")
    published_at: str | None = Field(None, description="ISO date of the source post")


class NicheCompetitor(BaseModel):
    """Competitor mention found in the niche."""

    name: str = Field(description="Competitor/product name mentioned")
    mention_count: int = Field(description="How many times mentioned")
    sentiment: str = Field(default="neutral", description="Sentiment: positive/negative/neutral")


class NicheMetrics(BaseModel):
    """Key metrics for niche assessment."""

    yandex_wordstat_requests: int = Field(
        description="Monthly search requests from Яндекс.Вордстат"
    )
    yandex_wordstat_trend: str = Field(
        default="stable", description="Trend: growing/stable/declining"
    )
    vcru_mentions: int = Field(description="Number of mentions on VC.ru")
    pain_point_count: int = Field(description="Number of verified pain points found")
    competitor_count: int = Field(description="Number of competitors identified")
    rubert_embedding: list[float] | None = Field(
        None,
        description="RuBERT embedding vector (768 dims) for semantic search",
    )


class NicheScore(BaseModel):
    """Comprehensive niche scoring result."""

    id: int = Field(description="Niche unique ID")
    niche_name: str = Field(description="Name of the B2B niche")
    category: str = Field(description="Category: saas, marketplace, edtech, fintech, etc.")
    overall_score: float = Field(description="Overall attractiveness score 0.0–100.0")
    confidence: float = Field(description="AI confidence score 0.0–1.0")
    metrics: NicheMetrics = Field(description="Key metrics for this niche")
    pain_points: list[NichePainPoint] = Field(description="Top verified pain points")
    competitors: list[NicheCompetitor] = Field(description="Competitor landscape")
    summary_ru: str = Field(description="Russian-language summary for the niche")


class NicheSearchResults(BaseModel):
    """Paginated search results."""

    items: list[NicheScore]
    total: int
    page: int
    page_size: int
    has_more: bool


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────


def _niche_to_score(niche: NicheIdea) -> NicheScore:
    """Convert a NicheIdea ORM model to the NicheScore Pydantic model."""
    pain_points_raw = niche.pain_points_json or []
    pain_points = [
        NichePainPoint(
            text=pp.get("text", ""),
            source_url=pp.get("source_url", ""),
            source_title=pp.get("source_title", ""),
            author=pp.get("author"),
            published_at=pp.get("published_at"),
        )
        for pp in pain_points_raw
    ]

    competitors_raw = niche.competitors_json or []
    competitors = [
        NicheCompetitor(
            name=c.get("name", ""),
            mention_count=c.get("mention_count", 0),
            sentiment=c.get("sentiment", "neutral"),
        )
        for c in competitors_raw
    ]

    return NicheScore(
        id=niche.id,
        niche_name=niche.niche_name,
        category=niche.category,
        overall_score=niche.overall_score,
        confidence=niche.confidence,
        metrics=NicheMetrics(
            yandex_wordstat_requests=niche.wordstat_requests,
            yandex_wordstat_trend=niche.wordstat_trend or "stable",
            vcru_mentions=niche.vcru_mention_count,
            pain_point_count=niche.pain_point_count,
            competitor_count=niche.competitor_count,
            rubert_embedding=niche.embedding,
        ),
        pain_points=pain_points[:20],  # limit to 20
        competitors=competitors[:20],
        summary_ru=niche.summary_ru or "",
    )


# ──────────────────────────────────────────
# API Key rate-limited dependency
# ──────────────────────────────────────────


async def rate_limit_for_user(
    user: User,
    limiter: RedisRateLimiter,
    tier: str = "developer",
) -> None:
    """Apply rate limiting for an API key user."""
    rpm = RPM_LIMITS.get(tier, RPM_LIMITS["free"])
    identifier = f"user:{user.id}:{tier}"
    await limiter.check(identifier, max_requests=rpm)


# ──────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────


@router.get(
    "/niches/top",
    response_model=NicheSearchResults,
    summary="Get top scored niches",
    description=(
        "Returns the highest-scored B2B niches ranked by overall_score.\n\n"
        "Includes full metadata: pain points with original texts, Wordstat "
        "request counts, competitor mentions, and RuBERT embeddings.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/top?limit=10&offset=0"\n'
        '```\n\n'
        '**Python example:**\n'
        '```python\n'
        'import requests\n'
        'resp = requests.get(\n'
        '    "https://api.nichefinder.com/v1/niches/top",\n'
        '    headers={"Authorization": "Bearer nf_abc123_..."}\n'
        ')\n'
        'data = resp.json()\n'
        '```'
    ),
)
async def get_top_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=100, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    category: str | None = Query(
        default=None, description="Filter by category (saas, marketplace, etc.)"
    ),
) -> NicheSearchResults:
    """Get top scored B2B niches, ordered by overall_score descending."""
    await rate_limit_for_user(user, limiter, tier="developer")

    # Build query
    query = select(NicheIdea)

    if category:
        query = query.where(NicheIdea.category == category)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Fetch page
    query = query.order_by(NicheIdea.overall_score.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    niches = list(result.scalars().all())

    items = [_niche_to_score(n) for n in niches]
    page = offset // limit + 1 if limit > 0 else 1
    has_more = (offset + limit) < total

    return NicheSearchResults(
        items=items,
        total=total,
        page=page,
        page_size=limit,
        has_more=has_more,
    )


@router.get(
    "/niches/search",
    response_model=NicheSearchResults,
    summary="Search B2B niches by keyword or semantic similarity",
    description=(
        "Hybrid search across niches:\n"
        "1. **By text**: full-text ILIKE search on niche_name and summary_ru\n"
        "2. **By embedding** (if query_embed=true): cosine similarity via pgvector\n\n"
        "Returns matched niches with complete scoring data, pain points, and competitor info.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/search?q=логистика&limit=10"\n'
        '```\n\n'
        '**Node.js example:**\n'
        '```javascript\n'
        'const resp = await fetch(\n'
        '  "https://api.nichefinder.com/v1/niches/search?q=логистика",\n'
        '  { headers: { Authorization: "Bearer nf_abc123_..." } }\n'
        ')\n'
        'const data = await resp.json()\n'
        '```'
    ),
)
async def search_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=10, ge=1, le=100, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    query_embed: bool = Query(
        default=False,
        description="Use semantic search (RuBERT embedding). Slower but more accurate.",
    ),
) -> NicheSearchResults:
    """Search niches by text or semantic similarity."""
    await rate_limit_for_user(user, limiter, tier="developer")

    if query_embed:
        # ── Semantic search via pgvector ──
        from app.ml.service import get_embedding

        try:
            query_vec = get_embedding(q)
        except Exception:
            query_vec = None

        if query_vec:
            # Cosine distance: lower = more similar
            dist_col = cosine_distance(NicheIdea.embedding, query_vec)
            query = (
                select(NicheIdea)
                .where(NicheIdea.embedding.isnot(None))
                .order_by(dist_col)
                .limit(limit + offset)
            )
            result = await db.execute(query)
            all_niches = list(result.scalars().all())
            niches = all_niches[offset:offset + limit] if offset < len(all_niches) else []
            total = len(all_niches)
        else:
            niches = []
            total = 0
    else:
        # ── Full-text search via ILIKE ──
        pattern = f"%{q}%"
        count_query = select(func.count()).select_from(
            select(NicheIdea).where(
                NicheIdea.niche_name.ilike(pattern)
                | NicheIdea.summary_ru.ilike(pattern)
            ).subquery()
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = (
            select(NicheIdea)
            .where(
                NicheIdea.niche_name.ilike(pattern)
                | NicheIdea.summary_ru.ilike(pattern)
            )
            .order_by(NicheIdea.overall_score.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        niches = list(result.scalars().all())

    items = [_niche_to_score(n) for n in niches]
    page = offset // limit + 1 if limit > 0 else 1
    has_more = (offset + limit) < total

    return NicheSearchResults(
        items=items,
        total=total,
        page=page,
        page_size=limit,
        has_more=has_more,
    )


@router.get(
    "/niches/{niche_id}",
    response_model=NicheScore,
    summary="Get detailed niche by ID",
    description=(
        "Returns full scoring details for a specific niche, including all pain points "
        "with original texts, Wordstat metrics, and competitor analysis.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/42"\n'
        '```'
    ),
)
async def get_niche_detail(
    niche_id: int,
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NicheScore:
    """Get a single niche with full detail by ID."""
    await rate_limit_for_user(user, limiter, tier="developer")

    result = await db.execute(select(NicheIdea).where(NicheIdea.id == niche_id))
    niche = result.scalar_one_or_none()

    if niche is None:
        raise HTTPException(status_code=404, detail="Niche not found")

    return _niche_to_score(niche)


@router.get(
    "/niches/{niche_id}/similar",
    response_model=list[NicheScore],
    summary="Find semantically similar niches",
    description=(
        "Uses pgvector cosine distance to find niches with similar embeddings.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/42/similar?limit=5"\n'
        '```'
    ),
)
async def get_similar_niches(
    niche_id: int,
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=5, ge=1, le=20),
) -> list[NicheScore]:
    """Find niches semantically similar to the given one using pgvector."""
    await rate_limit_for_user(user, limiter, tier="developer")

    # Get source niche embedding
    result = await db.execute(select(NicheIdea).where(NicheIdea.id == niche_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Niche not found")
    if not source.embedding:
        raise HTTPException(status_code=400, detail="Niche has no embedding vector")

    # Find nearest neighbors via cosine distance
    dist_col = cosine_distance(NicheIdea.embedding, source.embedding)
    query = (
        select(NicheIdea)
        .where(NicheIdea.id != niche_id, NicheIdea.embedding.isnot(None))
        .order_by(dist_col)
        .limit(limit)
    )
    result = await db.execute(query)
    similar = list(result.scalars().all())

    return [_niche_to_score(n) for n in similar]


@router.get(
    "/niches/export",
    summary="Export niches as CSV or JSONL",
    description=(
        "Batch export of niche data for data science teams. "
        "Supports CSV and JSONL formats. Includes all metadata "
        "including RuBERT embeddings.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/export?format=csv&category=saas"\n'
        '```'
    ),
)
async def export_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(default="jsonl", pattern="^(csv|jsonl)$"),
    category: str | None = Query(default=None),
) -> Any:
    """Streaming export of all niches in CSV or JSONL format."""
    await rate_limit_for_user(user, limiter, tier="enterprise")

    query = select(NicheIdea).order_by(NicheIdea.overall_score.desc())
    if category:
        query = query.where(NicheIdea.category == category)

    result = await db.execute(query)
    niches = list(result.scalars().all())

    if format == "csv":
        return _export_csv(niches)
    else:
        return _export_jsonl(niches)


def _export_csv(niches: list[NicheIdea]) -> StreamingResponse:
    """Stream niches as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id",
        "niche_name",
        "category",
        "overall_score",
        "confidence",
        "wordstat_requests",
        "wordstat_trend",
        "vcru_mentions",
        "pain_point_count",
        "competitors_count",
        "summary_ru",
    ])

    for n in niches:
        writer.writerow([
            n.id,
            n.niche_name,
            n.category,
            n.overall_score,
            n.confidence,
            n.wordstat_requests,
            n.wordstat_trend,
            n.vcru_mention_count,
            n.pain_point_count,
            n.competitor_count,
            n.summary_ru or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=niches_export.csv",
            "Content-Length": str(len(csv_bytes)),
        },
    )


def _export_jsonl(niches: list[NicheIdea]) -> StreamingResponse:
    """Stream niches as JSONL (one JSON object per line)."""
    lines: list[str] = []
    for n in niches:
        obj = {
            "id": n.id,
            "niche_name": n.niche_name,
            "category": n.category,
            "overall_score": n.overall_score,
            "confidence": n.confidence,
            "wordstat_requests": n.wordstat_requests,
            "wordstat_trend": n.wordstat_trend,
            "vcru_mentions": n.vcru_mention_count,
            "pain_point_count": n.pain_point_count,
            "competitors": n.competitors_json,
            "pain_points": n.pain_points_json,
            "summary_ru": n.summary_ru or "",
            "embedding": n.embedding,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))

    content = "\n".join(lines).encode("utf-8")

    return StreamingResponse(
        iter([content]),
        media_type="application/jsonl",
        headers={
            "Content-Disposition": "attachment; filename=niches_export.jsonl",
            "Content-Length": str(len(content)),
        },
    )

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import RedisRateLimiter, get_rate_limiter, RPM_LIMITS
from app.db.session import get_db
from app.deps import get_api_key_user
from app.models.user import User

router = APIRouter()


# ──────────────────────────────────────────
# Response models (rich metadata for DS teams)
# ──────────────────────────────────────────


class NichePainPoint(BaseModel):
    """A verified pain point extracted from real user comments."""

    text: str = Field(description="Original text of the pain point from VC.ru comments")
    source_url: str = Field(description="URL of the source post")
    source_title: str = Field(description="Title of the source post")
    author: str | None = Field(None, description="Comment author name")
    published_at: str | None = Field(None, description="ISO date of the source post")


class NicheCompetitor(BaseModel):
    """Competitor mention found in the niche."""

    name: str = Field(description="Competitor/product name mentioned")
    mention_count: int = Field(description="How many times mentioned")
    sentiment: str = Field(default="neutral", description="Sentiment: positive/negative/neutral")


class NicheMetrics(BaseModel):
    """Key metrics for niche assessment."""

    yandex_wordstat_requests: int = Field(
        description="Monthly search requests from Яндекс.Вордстат"
    )
    yandex_wordstat_trend: str = Field(
        default="stable", description="Trend: growing/stable/declining"
    )
    vcru_mentions: int = Field(description="Number of mentions on VC.ru in last 3 months")
    pain_point_count: int = Field(description="Number of verified pain points found")
    competitor_count: int = Field(description="Number of competitors identified")
    rubert_embedding: list[float] | None = Field(
        None,
        description="RuBERT embedding vector (768 dims) for semantic search",
    )


class NicheScore(BaseModel):
    """Comprehensive niche scoring result."""

    niche_name: str = Field(description="Name of the B2B niche")
    category: str = Field(description="Category: saas, marketplace, edtech, fintech, etc.")
    overall_score: float = Field(description="Overall attractiveness score 0.0–100.0")
    confidence: float = Field(description="AI confidence score 0.0–1.0")
    metrics: NicheMetrics = Field(description="Key metrics for this niche")
    pain_points: list[NichePainPoint] = Field(description="Top verified pain points")
    competitors: list[NicheCompetitor] = Field(description="Competitor landscape")
    summary_ru: str = Field(description="Russian-language summary for the niche")


class NicheSearchResults(BaseModel):
    """Paginated search results."""

    items: list[NicheScore]
    total: int
    page: int
    page_size: int
    has_more: bool


# ──────────────────────────────────────────
# API Key rate-limited dependency
# ──────────────────────────────────────────


async def rate_limit_for_user(
    user: User,
    limiter: RedisRateLimiter,
    tier: str = "developer",
) -> None:
    """Apply rate limiting for an API key user.

    Tier limits:
      - free: 10 req/min (sandbox)
      - developer: 300 req/min (5 RPS)
      - enterprise: 3000 req/min (50 RPS)
    """
    rpm = RPM_LIMITS.get(tier, RPM_LIMITS["free"])
    identifier = f"user:{user.id}:{tier}"
    await limiter.check(identifier, max_requests=rpm)


# ──────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────


@router.get(
    "/niches/top",
    response_model=NicheSearchResults,
    summary="Get top scored niches",
    description=(
        "Returns the highest-scored B2B niches based on Яндекс.Вордстат data, "
        "VC.ru comments analysis, and competitive landscape assessment.\n\n"
        "Includes full metadata: pain points with original texts, exact Wordstat "
        "request counts, competitor mentions, and RuBERT embeddings (768-dim).\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/top?limit=10&offset=0"\n'
        '```\n\n'
        '**Python example:**\n'
        '```python\n'
        'import requests\n'
        'resp = requests.get(\n'
        '    "https://api.nichefinder.com/v1/niches/top",\n'
        '    headers={"Authorization": "Bearer nf_abc123_..."}\n'
        ')\n'
        'data = resp.json()\n'
        '```'
    ),
)
async def get_top_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=100, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    category: str | None = Query(
        default=None, description="Filter by category (saas, marketplace, etc.)"
    ),
) -> NicheSearchResults:
    """Get top scored B2B niches."""
    await rate_limit_for_user(user, limiter, tier="developer")

    # TODO: Replace with actual DB query once niches are stored
    # For now returns a sample structure showing the data model
    sample = NicheScore(
        niche_name="B2B SaaS для логистики",
        category="saas",
        overall_score=87.5,
        confidence=0.92,
        metrics=NicheMetrics(
            yandex_wordstat_requests=14500,
            yandex_wordstat_trend="growing",
            vcru_mentions=230,
            pain_point_count=12,
            competitor_count=8,
            rubert_embedding=[0.0] * 10,  # truncated for sample
        ),
        pain_points=[
            NichePainPoint(
                text="У нас до сих пор всё в Excel, менеджеры путаются в заказах",
                source_url="https://vc.ru/finance/123456-b2b-saas",
                source_title="B2B SaaS для логистики",
                author="Иван Петров",
                published_at="2026-06-15T10:00:00Z",
            ),
            NichePainPoint(
                text="Нет нормальной интеграции с 1С, приходится дублировать данные",
                source_url="https://vc.ru/finance/123456-b2b-saas",
                source_title="B2B SaaS для логистики",
                author=None,
                published_at="2026-06-15T10:30:00Z",
            ),
        ],
        competitors=[
            NicheCompetitor(name="LogistikPro", mention_count=15, sentiment="negative"),
            NicheCompetitor(name="SAP TM", mention_count=8, sentiment="neutral"),
        ],
        summary_ru="Ниша B2B-логистики показывает устойчивый рост. "
        "Основные боли: Excel-учёт, отсутствие интеграции с 1С, "
        "сложности маршрутизации. 8 конкурентов, но у всех слабые места.",
    )

    return NicheSearchResults(
        items=[sample],
        total=1,
        page=offset // limit + 1,
        page_size=limit,
        has_more=False,
    )


@router.get(
    "/niches/search",
    response_model=NicheSearchResults,
    summary="Search B2B niches by keyword",
    description=(
        "Full-text search across analyzed niches. Supports Russian-language queries.\n\n"
        "Returns matched niches with complete scoring data, pain points, and competitor info.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/search?q=логистика&limit=10"\n'
        '```\n\n'
        '**Node.js example:**\n'
        '```javascript\n'
        'const resp = await fetch(\n'
        '  "https://api.nichefinder.com/v1/niches/search?q=логистика",\n'
        '  { headers: { Authorization: "Bearer nf_abc123_..." } }\n'
        ')\n'
        'const data = await resp.json()\n'
        '```'
    ),
)
async def search_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2, description="Search query in Russian or English"),
    limit: int = Query(default=10, ge=1, le=100, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> NicheSearchResults:
    """Search niches by keyword."""
    await rate_limit_for_user(user, limiter, tier="developer")

    # TODO: Replace with actual search implementation
    return NicheSearchResults(
        items=[],
        total=0,
        page=offset // limit + 1,
        page_size=limit,
        has_more=False,
    )


@router.get(
    "/niches/{niche_id}",
    response_model=NicheScore,
    summary="Get detailed niche by ID",
    description=(
        "Returns full scoring details for a specific niche, including all pain points "
        "with original comment texts, exact Wordstat metrics, and competitor analysis.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/42"\n'
        '```'
    ),
)
async def get_niche_detail(
    niche_id: int,
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NicheScore:
    """Get a single niche with full detail."""
    await rate_limit_for_user(user, limiter, tier="developer")

    raise HTTPException(status_code=404, detail="Niche not found")


@router.get(
    "/niches/export",
    summary="Export niches as CSV or JSONL",
    description=(
        "Batch export of niche data for data science teams. "
        "Supports CSV and JSONL formats. Includes all metadata "
        "including RuBERT embeddings.\n\n"
        "**cURL example:**\n"
        '```bash\n'
        'curl -H "Authorization: Bearer nf_abc123_..." \\\n'
        '  "https://api.nichefinder.com/v1/niches/export?format=csv&category=saas"\n'
        '```'
    ),
)
async def export_niches(
    user: Annotated[User, Depends(get_api_key_user)],
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    category: str | None = Query(default=None),
) -> dict:
    """Export niches for data science teams."""
    await rate_limit_for_user(user, limiter, tier="enterprise")

    # TODO: Implement actual export
    return {"message": f"Export in {format} format — coming soon"}
