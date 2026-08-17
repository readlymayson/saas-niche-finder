from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.vector import VectorType


class RawPost(Base):
    """Raw scraped post from VC.ru, Telegram, or other sources.

    Stores the original content before ML processing.
    After ML processing, `is_processed=True` and embeddings/pain signals are set.
    """

    __tablename__ = "raw_posts"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_raw_post_source_ext"),
        Index("idx_raw_posts_source_unprocessed", "source", "is_processed"),
        Index("idx_raw_posts_pain_points", "is_pain_point"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Original post ID in source"
    )
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    body_text: Mapped[str] = mapped_column(Text())
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comments_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Extracted comments (JSON array)"
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
