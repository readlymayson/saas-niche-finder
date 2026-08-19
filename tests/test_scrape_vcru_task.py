"""Regression tests for the `scrape_vcru` and `aggregate_niches` Celery tasks.

Verifies that saved RawPost rows carry a non-null `external_id`
(required by the `raw_posts.external_id` NOT NULL constraint) and that
`aggregate_niches` creates NicheIdea rows with non-null, unique `slug`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.models.niche_idea import NicheIdea
from app.models.raw_post import RawPost
from app.workers.tasks import aggregate_niches, scrape_vcru


class _FakeVcPost:
    def __init__(self, url: str, title: str = "t", body_text: str = "b") -> None:
        self.url = url
        self.title = title
        self.body_text = body_text
        self.comments = []


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalar_one_or_none(self):  # noqa: ANN201
        return self._rows[0] if self._rows else None

    def scalars(self):  # noqa: ANN201
        return self

    def all(self):  # noqa: ANN201
        return self._rows


class _FakeSession:
    """Minimal AsyncSession stand-in recording added rows."""

    def __init__(self) -> None:
        self.added: list = []
        self._pain_posts: list[RawPost] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info) -> None:  # noqa: ANN002, D105
        pass

    async def execute(self, stmt):  # noqa: ANN001, ANN201
        # aggregate_niches first selects pain RawPosts, then existing NicheIdea.
        table = getattr(getattr(stmt, "_raw_columns", (None,))[0], "name", None)
        if table == "raw_posts":
            return _FakeResult(self._pain_posts)
        return _FakeResult([])

    async def commit(self) -> None:  # noqa: D102
        pass

    def add(self, obj) -> None:  # noqa: ANN001, ANN201, D102
        self.added.append(obj)


def _fake_session_maker():
    """Return a fake `async_session_maker()` that always yields the same session."""

    session = _FakeSession()

    def _maker() -> _FakeSession:
        return session

    return _maker, session


def test_scrape_vcru_sets_external_id_from_url() -> None:
    """RawPost rows saved by scrape_vcru must have non-null external_id."""
    url = "https://vc.ru/services/12345-article"
    maker, session = _fake_session_maker()
    fake_posts = [_FakeVcPost(url=url, title="Статья", body_text="Текст")]

    with (
        patch("app.services.vc_parser.VcFetcher") as mock_fetcher_cls,
        patch("app.workers.tasks.async_session_maker", maker),
    ):
        instance = mock_fetcher_cls.return_value
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.fetch_posts_from_rss = AsyncMock(return_value=fake_posts)

        stats = scrape_vcru()

    assert stats["posts_saved"] == 1
    assert len(session.added) == 1
    saved = session.added[0]
    assert saved.source == "vcru"
    assert saved.external_id == url
    assert saved.source_id == url


def test_aggregate_niches_sets_slug_and_title() -> None:
    """NicheIdea rows created by aggregate_niches must have non-null slug/title."""
    post = RawPost(
        id=1,
        source="vcru",
        external_id="https://vc.ru/1",
        url="https://vc.ru/1",
        title="CRM для продаж",
        body_text="CRM для продаж — боль компаний",
        is_processed=True,
        is_pain_point=True,
        pain_probability=0.9,
    )
    maker, session = _fake_session_maker()
    # aggregate_niches queries pain posts and then checks for existing niche
    session._pain_posts = [post]

    with patch("app.workers.tasks.async_session_maker", maker):
        stats = aggregate_niches()

    assert stats["niches_created"] == 1
    assert len(session.added) == 1
    niche = session.added[0]
    assert isinstance(niche, NicheIdea)
    assert niche.slug  # non-empty
    assert niche.title == "CRM и управление продажами"
    assert niche.niche_name == "CRM и управление продажами"
    assert niche.slug == "crm-i-upravlenie-prodazhami"
