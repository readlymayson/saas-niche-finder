from __future__ import annotations

from datetime import UTC, datetime

from app.models.raw_post import RawPost
from app.services.niche_pipeline import (
    _gpt_json_from_post_and_draft,
    _keyword_from_post,
    _safe_slug,
    _wordstat_snapshot_from_draft,
)


def test_safe_slug_from_title() -> None:
    assert _safe_slug("CRM для SMB!!!", 99) == "crm-smb"


def test_keyword_from_post_prefers_title() -> None:
    post = RawPost(
        id=1,
        source="vc",
        external_id="x",
        title="B2B SaaS",
        body_text="длинный текст",
    )
    assert _keyword_from_post(post) == "B2B SaaS"


def test_wordstat_snapshot_from_draft() -> None:
    draft = {"wordstat": {"payload": {"growth": 12.5, "rows": []}}}
    snap = _wordstat_snapshot_from_draft(draft)
    assert snap["growth"] == 12.5
    assert "payload" in snap


def test_gpt_json_merges_post_extra() -> None:
    post = RawPost(
        id=1,
        source="vc",
        external_id="x",
        title="t",
        body_text="b",
        collected_at=datetime.now(UTC),
        extra={"pain_frequency": 7, "competitors_count": 1},
    )
    gpt = _gpt_json_from_post_and_draft(post, None)
    assert gpt["pain_frequency"] == 7
