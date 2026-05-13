"""Round-trip tests for the pending-review on-disk cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from unravel.tui import review_storage
from unravel.tui.review_state import (
    PendingReview,
    PendingReviewComment,
    PrContext,
)


@pytest.fixture
def tmp_xdg(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def _make_pending() -> PendingReview:
    p = PendingReview(summary="Looks good with a few nits")
    p.comments.append(
        PendingReviewComment(path="src/foo.py", line=12, side="RIGHT", body="nit")
    )
    p.comments.append(
        PendingReviewComment(
            path="src/bar.py",
            line=42,
            side="RIGHT",
            start_line=40,
            start_side="RIGHT",
            body="range",
        )
    )
    return p


def test_load_missing_returns_none(tmp_xdg):
    ctx = PrContext(repo_nwo="o/r", pr_number=1)
    assert review_storage.load_pending(ctx) is None


def test_save_then_load_round_trips(tmp_xdg):
    ctx = PrContext(repo_nwo="o/r", pr_number=42)
    pending = _make_pending()
    review_storage.save_pending(ctx, pending)

    restored = review_storage.load_pending(ctx)
    assert restored is not None
    assert restored.summary == pending.summary
    assert len(restored.comments) == 2
    assert restored.comments[0] == pending.comments[0]
    assert restored.comments[1] == pending.comments[1]


def test_keyed_per_pr(tmp_xdg):
    ctx_a = PrContext(repo_nwo="o/r", pr_number=1)
    ctx_b = PrContext(repo_nwo="o/r", pr_number=2)
    pa = PendingReview(summary="A")
    pa.comments.append(
        PendingReviewComment(path="a.py", line=1, side="RIGHT", body="one")
    )
    review_storage.save_pending(ctx_a, pa)

    assert review_storage.load_pending(ctx_b) is None
    assert review_storage.load_pending(ctx_a).comments[0].body == "one"


def test_repo_slug_is_sanitized(tmp_xdg):
    ctx = PrContext(repo_nwo="some-org/weird repo!", pr_number=5)
    review_storage.save_pending(ctx, _make_pending())
    # No raw slash leaks through into the filename — would create a subdir.
    files = list((tmp_xdg / "unravel" / "pending_reviews").iterdir())
    assert len(files) == 1
    assert "/" not in files[0].name


def test_discard_removes_file(tmp_xdg):
    ctx = PrContext(repo_nwo="o/r", pr_number=7)
    review_storage.save_pending(ctx, _make_pending())
    review_storage.discard_pending(ctx)
    assert review_storage.load_pending(ctx) is None

    # Idempotent — calling discard a second time should not raise.
    review_storage.discard_pending(ctx)


def test_corrupt_file_returns_none(tmp_xdg):
    ctx = PrContext(repo_nwo="o/r", pr_number=9)
    review_storage._path_for(ctx).parent.mkdir(parents=True, exist_ok=True)
    review_storage._path_for(ctx).write_text("{ not json")
    assert review_storage.load_pending(ctx) is None


def test_skips_malformed_comments_keeps_others(tmp_xdg):
    ctx = PrContext(repo_nwo="o/r", pr_number=10)
    path = review_storage._path_for(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"summary": "ok", "comments": ['
        '{"path": "a.py", "line": 1, "side": "RIGHT", "body": "kept"},'
        '{"path": "b.py", "side": "RIGHT", "body": "missing line"}'
        ']}'
    )
    restored = review_storage.load_pending(ctx)
    assert restored is not None
    assert [c.body for c in restored.comments] == ["kept"]
