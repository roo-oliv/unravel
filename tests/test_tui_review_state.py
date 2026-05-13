"""Tests for the review_state dataclasses + payload builder + helpers."""

from __future__ import annotations

from unravel.tui.review_state import (
    PendingReview,
    PendingReviewComment,
    PrContext,
    build_review_payload,
    hunk_window_contains,
    parse_pr_state,
)


class TestPrContextFromMetadata:
    def test_returns_none_when_metadata_missing(self):
        assert PrContext.from_metadata(None) is None
        assert PrContext.from_metadata({}) is None

    def test_returns_none_when_source_not_pr(self):
        assert (
            PrContext.from_metadata({"source": {"kind": "range", "spec": "HEAD~3"}})
            is None
        )

    def test_returns_none_when_repo_or_number_missing(self):
        assert PrContext.from_metadata({"source": {"kind": "pr", "number": 7}}) is None
        assert (
            PrContext.from_metadata({"source": {"kind": "pr", "repo": "o/r"}}) is None
        )

    def test_parses_full_pr_source(self):
        ctx = PrContext.from_metadata(
            {
                "source": {
                    "kind": "pr",
                    "repo": "roo-oliv/unravel",
                    "number": 12,
                    "head_sha": "deadbeef",
                    "html_url": "https://github.com/roo-oliv/unravel/pull/12",
                }
            }
        )
        assert ctx == PrContext(
            repo_nwo="roo-oliv/unravel",
            pr_number=12,
            head_sha="deadbeef",
            html_url="https://github.com/roo-oliv/unravel/pull/12",
        )


class TestParsePrState:
    def test_draft_wins_over_open(self):
        assert parse_pr_state({"state": "OPEN", "isDraft": True}) == "draft"

    def test_state_normalized(self):
        assert parse_pr_state({"state": "OPEN", "isDraft": False}) == "open"
        assert parse_pr_state({"state": "MERGED"}) == "merged"
        assert parse_pr_state({"state": "CLOSED"}) == "closed"

    def test_unknown_defaults_to_open(self):
        assert parse_pr_state({}) == "open"


class TestBuildReviewPayload:
    def _comment(self, **kw) -> PendingReviewComment:
        defaults = dict(path="src/foo.py", line=10, side="RIGHT", body="nit")
        defaults.update(kw)
        return PendingReviewComment(**defaults)

    def test_single_line_omits_start_fields(self):
        pending = PendingReview(comments=[self._comment()])
        payload = build_review_payload(pending, "COMMENT", "sha123")
        assert payload["comments"][0] == {
            "path": "src/foo.py",
            "line": 10,
            "side": "RIGHT",
            "body": "nit",
        }
        assert payload["commit_id"] == "sha123"
        assert payload["event"] == "COMMENT"
        assert "body" not in payload  # empty summary stripped

    def test_summary_included_when_non_empty(self):
        pending = PendingReview(summary="  Overall LGTM  ")
        payload = build_review_payload(pending, "APPROVE", "sha")
        assert payload["body"] == "Overall LGTM"
        assert payload["comments"] == []

    def test_multiline_range_keeps_start_fields(self):
        pending = PendingReview(
            comments=[
                self._comment(
                    line=20,
                    start_line=15,
                    start_side="RIGHT",
                    body="range comment",
                )
            ]
        )
        payload = build_review_payload(pending, "REQUEST_CHANGES", "sha")
        c = payload["comments"][0]
        assert c["start_line"] == 15
        assert c["start_side"] == "RIGHT"
        assert c["line"] == 20

    def test_degenerate_range_collapses_to_single_line(self):
        # start_line == line → no range, drop start fields
        pending = PendingReview(
            comments=[self._comment(line=10, start_line=10, start_side="RIGHT")]
        )
        payload = build_review_payload(pending, "COMMENT", "sha")
        assert "start_line" not in payload["comments"][0]
        assert "start_side" not in payload["comments"][0]

    def test_start_side_falls_back_to_side(self):
        pending = PendingReview(
            comments=[self._comment(line=20, start_line=15, start_side=None)]
        )
        payload = build_review_payload(pending, "COMMENT", "sha")
        assert payload["comments"][0]["start_side"] == "RIGHT"


class TestHunkWindow:
    def test_right_side_inclusive_lower_exclusive_upper(self):
        assert hunk_window_contains(
            line=5, side="RIGHT", new_start=5, new_count=3, old_start=0, old_count=0
        )
        assert hunk_window_contains(
            line=7, side="RIGHT", new_start=5, new_count=3, old_start=0, old_count=0
        )
        assert not hunk_window_contains(
            line=8, side="RIGHT", new_start=5, new_count=3, old_start=0, old_count=0
        )
        assert not hunk_window_contains(
            line=4, side="RIGHT", new_start=5, new_count=3, old_start=0, old_count=0
        )

    def test_left_side_uses_old_window(self):
        assert hunk_window_contains(
            line=10, side="LEFT", new_start=0, new_count=0, old_start=10, old_count=2
        )
        assert not hunk_window_contains(
            line=12, side="LEFT", new_start=0, new_count=0, old_start=10, old_count=2
        )

    def test_null_line_never_matches(self):
        assert not hunk_window_contains(
            line=None, side="RIGHT", new_start=1, new_count=5, old_start=1, old_count=5
        )
