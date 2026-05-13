"""Data shapes for the GitHub PR review TUI: snapshot, pending review, payloads.

Two halves:

- *Snapshot* — what the API server would call "PrDTO + comments": the
  read-only mirror of what GitHub currently says about the PR. Built from
  the parsed responses of ``gh pr view`` / ``gh api .../comments`` /
  ``gh api .../reviews``.
- *Pending review* — the GitHub-style "start review" workflow: a list of
  inline comments queued in memory until the user picks a verdict
  (APPROVE / COMMENT / REQUEST_CHANGES) and submits the lot as a single
  ``POST /repos/{nwo}/pulls/{num}/reviews`` payload.

Both live entirely in the TUI session — no persistence between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Side = Literal["LEFT", "RIGHT"]
PrState = Literal["open", "draft", "merged", "closed"]
ReviewState = Literal["APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"]
Verdict = Literal["APPROVE", "COMMENT", "REQUEST_CHANGES"]
# What the submit dialog returned: a Verdict means "send to GitHub";
# "DISCARD" means "drop the pending review entirely without submitting".
SubmitAction = Literal["APPROVE", "COMMENT", "REQUEST_CHANGES", "DISCARD"]


@dataclass(frozen=True)
class PrContext:
    """Stable identifiers needed to address a PR through ``gh``.

    Sourced from ``walkthrough.metadata["source"]`` when the walkthrough
    came from ``unravel pr``. ``head_sha`` is required by the GitHub review
    API to anchor inline comments to a specific commit.
    """

    repo_nwo: str
    pr_number: int
    head_sha: str | None = None
    html_url: str | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> PrContext | None:
        """Build a PrContext from ``walkthrough.metadata['source']`` if it's a PR."""
        if not metadata:
            return None
        source = metadata.get("source")
        if not isinstance(source, dict) or source.get("kind") != "pr":
            return None
        repo = source.get("repo")
        number = source.get("number")
        if not repo or not number:
            return None
        return cls(
            repo_nwo=str(repo),
            pr_number=int(number),
            head_sha=source.get("head_sha"),
            html_url=source.get("html_url"),
        )


@dataclass
class IssueComment:
    id: int
    author: str
    body: str
    created_at: str
    html_url: str = ""


@dataclass
class ReviewSummary:
    id: int
    author: str
    state: ReviewState
    body: str
    submitted_at: str | None
    commit_id: str | None = None


@dataclass
class ReviewComment:
    """An inline review comment (anchored to a file + line range)."""

    id: int
    review_id: int | None
    in_reply_to_id: int | None
    author: str
    body: str
    path: str
    line: int | None
    side: Side
    start_line: int | None
    start_side: Side | None
    is_outdated: bool
    created_at: str


@dataclass
class PrSnapshot:
    state: PrState
    title: str
    body: str
    html_url: str
    head_sha: str
    author: str
    issue_comments: list[IssueComment] = field(default_factory=list)
    review_summaries: list[ReviewSummary] = field(default_factory=list)
    review_comments: list[ReviewComment] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PendingReviewComment:
    """A locally-queued inline comment, not yet submitted to GitHub.

    Mirrors the modern REST shape: anchored by file path + line(+ side),
    with optional ``start_line``/``start_side`` for multi-line ranges.
    """

    path: str
    line: int
    side: Side
    body: str
    start_line: int | None = None
    start_side: Side | None = None

    def is_multiline(self) -> bool:
        return self.start_line is not None and self.start_line != self.line


@dataclass
class PendingReview:
    comments: list[PendingReviewComment] = field(default_factory=list)
    summary: str = ""

    def is_empty(self) -> bool:
        return not self.comments and not self.summary.strip()

    def clear(self) -> None:
        self.comments.clear()
        self.summary = ""


def build_review_payload(
    pending: PendingReview, verdict: Verdict, head_sha: str
) -> dict[str, Any]:
    """Convert a ``PendingReview`` + verdict into the JSON body for
    ``POST /repos/{nwo}/pulls/{num}/reviews``.

    Drops ``start_line``/``start_side`` when the range collapsed to a single
    line. Omits ``body`` when the summary is empty. Always includes
    ``commit_id`` so GitHub anchors comments to the snapshot the user saw.
    """
    body: dict[str, Any] = {
        "commit_id": head_sha,
        "event": verdict,
    }
    summary = pending.summary.strip()
    if summary:
        body["body"] = summary

    comments_payload: list[dict[str, Any]] = []
    for c in pending.comments:
        entry: dict[str, Any] = {
            "path": c.path,
            "line": c.line,
            "side": c.side,
            "body": c.body,
        }
        if c.is_multiline():
            entry["start_line"] = c.start_line
            entry["start_side"] = c.start_side or c.side
        comments_payload.append(entry)
    body["comments"] = comments_payload
    return body


def parse_pr_state(view_json: dict[str, Any]) -> PrState:
    """Collapse GitHub's ``state`` + ``isDraft`` into one value."""
    if view_json.get("isDraft"):
        return "draft"
    raw = (view_json.get("state") or "").upper()
    if raw == "OPEN":
        return "open"
    if raw == "MERGED":
        return "merged"
    if raw == "CLOSED":
        return "closed"
    # Unknown → fall back to open for the badge default.
    return "open"


def hunk_window_contains(
    *,
    line: int | None,
    side: Side,
    new_start: int,
    new_count: int,
    old_start: int,
    old_count: int,
) -> bool:
    """Whether a review comment anchored to (line, side) sits inside a hunk."""
    if line is None:
        return False
    if side == "RIGHT":
        return new_start <= line < (new_start + max(new_count, 1))
    return old_start <= line < (old_start + max(old_count, 1))
