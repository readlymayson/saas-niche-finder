from pydantic import BaseModel, Field


class NicheRead(BaseModel):
    """Публичное представление ниши в JSON-ответах ``GET /v1/niches/top``,

    ``GET /v1/niches/search`` и ``GET /v1/niches/{id}/similar``.

    ``summary`` и ``score`` допускают ``None``, если соответствующее значение
    отсутствует в данных.
    """

    id: int
    slug: str
    title: str
    summary: str | None
    score: float | None


class NicheEntityExtractResponse(BaseModel):
    organizations: list[str] = Field(default_factory=list)
    persons: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class FeedbackCreate(BaseModel):
    niche_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=4000)
    source: str = Field(default="api", max_length=32)


class FeedbackRead(BaseModel):
    id: int
    niche_id: int
    rating: int
    comment: str | None
    source: str
    score_snapshot: float | None
