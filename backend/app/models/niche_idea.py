from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.vector import VectorType


class NicheIdea(Base):
    """Aggregated niche idea with scoring data.

    One NicheIdea = one B2B niche, built from multiple RawPost entries.
    The embedding is the mean-pooled representation of all related pain posts.
    """

    __tablename__ = "niche_ideas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    yandex_gpt_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    wordstat_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Scoring (DaaS/ETL fields)
    niche_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="Short name: e.g. 'B2B SaaS для логистики'",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="saas",
        index=True,
        comment="saas/marketplace/edtech/etc",
    )
    overall_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, index=True, comment="Attractiveness 0-100"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="AI confidence 0-1"
    )
    wordstat_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Monthly search requests"
    )
    wordstat_trend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="stable", comment="growing/stable/declining"
    )
    vcru_mention_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="VC.ru mentions in last 3 months"
    )
    pain_point_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Verified pain points"
    )
    competitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Competitors identified"
    )
    summary_ru: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Russian-language summary"
    )
    pain_points_json: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment='List of {"text","source_url","source_title","author"}'
    )
    competitors_json: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment='List of {"name","mention_count","sentiment"}'
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        VectorType(768), nullable=True, comment="Mean-pooled RuBERT embedding"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_niche_ideas_score", "overall_score", "category"),
        Index("idx_niche_ideas_name", "niche_name"),
    )
