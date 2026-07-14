"""Data models for the ETL pipeline — RawPost and NicheIdea."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.vector import VectorType


class RawPost(Base):
    """Raw scraped post from VC.ru, Telegram, or other sources.

    Stores the original content before ML processing.
    After ML processing, `is_processed=True` and embeddings/pain signals are set.
    """

    __tablename__ = "raw_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="Source: vcru / telegram"
    )
    source_id: Mapped[str] = mapped_column(
        String(255), nullable=True, comment="Original post ID in source"
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Full body text for ML processing"
    )
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ML fields (filled after processing)
    is_processed: Mapped[bool] = mapped_column(
        default=False, index=True, comment="Has been through ML pipeline"
    )
    is_pain_point: Mapped[bool | None] = mapped_column(
        default=None, comment="ML classification: is this a business pain?"
    )
    pain_probability: Mapped[float | None] = mapped_column(
        Float, default=None, comment="ML confidence score for pain classification"
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        VectorType(768), nullable=True, comment="RuBERT embedding vector (768-dim)"
    )

    # Metadata
    comments_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Extracted comments (JSON array)"
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="When scraped"
    )

    __table_args__ = (
        Index("idx_raw_posts_source_unprocessed", "source", "is_processed"),
        Index("idx_raw_posts_pain_points", "is_pain_point"),
    )


class NicheIdea(Base):
    """Aggregated niche idea with scoring data.

    One NicheIdea = one B2B niche, built from multiple RawPost entries.
    The embedding is the mean-pooled representation of all related pain posts.
    """

    __tablename__ = "niche_ideas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    niche_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Short name: e.g. 'B2B SaaS для логистики'"
    )
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="saas", index=True, comment="saas/marketplace/edtech/etc"
    )

    # Scoring
    overall_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, index=True, comment="Attractiveness 0-100"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="AI confidence 0-1"
    )

    # Яндекс.Вордстат metrics
    wordstat_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Monthly search requests"
    )
    wordstat_trend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="stable", comment="growing/stable/declining"
    )

    # Content metrics
    vcru_mention_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="VC.ru mentions in last 3 months"
    )
    pain_point_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Verified pain points"
    )
    competitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Competitors identified"
    )

    # Summary & metadata
    summary_ru: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Russian-language summary"
    )
    pain_points_json: Mapped[list[dict] | None] = mapped_column(
        JSONB, nullable=True, comment='List of {"text","source_url","source_title","author"}'
    )
    competitors_json: Mapped[list[dict] | None] = mapped_column(
        JSONB, nullable=True, comment='List of {"name","mention_count","sentiment"}'
    )

    # Embedding for semantic search (768-dim from RuBERT)
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
