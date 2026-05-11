"""GitHub REST API client.

Auth resolution: every call accepts an explicit ``token``. When the caller
passes a logged-in user's OAuth token, comments are attributed to them.
When ``token=None`` we fall back to the ``GITHUB_TOKEN`` env var (server PAT)
— used by the Phase 0 dev path and as a back-stop in self-host installs
without OAuth set up yet.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class GitHubConfigError(RuntimeError):
    """Raised when GitHub credentials are missing or malformed."""


class GitHubError(RuntimeError):
    """Raised when a GitHub API call fails after status check."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PullRequest:
    state: str
    is_draft: bool
    merged_at: datetime | None
    closed_at: datetime | None
    html_url: str
    title: str
    body: str
    head_sha: str
    author_login: str | None


@dataclass(frozen=True)
class Comment:
    github_id: int
    kind: str  # "issue" | "review" | "review_comment"
    author_login: str | None
    author_avatar_url: str | None
    body: str
    html_url: str | None
    anchor_path: str | None
    anchor_line: int | None
    anchor_side: str | None
    # Multi-line range. ``start_line`` / ``start_side`` are ``None`` on
    # single-line comments; on multi-line, the thread spans
    # ``[start_line, anchor_line]`` (inclusive).
    anchor_start_line: int | None
    anchor_start_side: str | None
    # GitHub flips ``position`` to ``None`` when the underlying line has
    # shifted past the diff's reach — that's what their UI labels "outdated".
    is_outdated: bool
    review_state: str | None
    in_reply_to_github_id: int | None
    # For ``review``: the review's own id (lets the client recognise it as the
    # parent of the matching ``review_comment`` rows). For ``review_comment``:
    # the parent review id reported by GitHub.
    pull_request_review_id: int | None
    github_created_at: datetime | None
    github_updated_at: datetime | None


def _resolve_token(override: str | None) -> str:
    if override:
        return override
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubConfigError(
            "No GitHub credentials. Sign in via /auth/github to use your "
            "OAuth identity, or set GITHUB_TOKEN in .env as a server-wide "
            "fallback PAT."
        )
    return token


def _client(token: str | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=GITHUB_API,
        timeout=DEFAULT_TIMEOUT,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {_resolve_token(token)}",
            "User-Agent": "unravel-saas/0.0.0-phase1",
        },
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # GitHub returns ISO 8601 with trailing ``Z`` — fromisoformat handles it on 3.11+.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _split_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError(f"Expected owner/repo, got {repo!r}")
    owner, name = repo.split("/", 1)
    return owner, name


def _pr_state(payload: dict[str, Any]) -> str:
    """Collapse GitHub's open/closed + merged into a single label.

    Order matters: a merged PR is also closed in GitHub's API, so check merged
    first. Draft is orthogonal to state; we surface it on the dedicated bool.
    """
    if payload.get("merged_at"):
        return "merged"
    if payload.get("state") == "closed":
        return "closed"
    if payload.get("draft"):
        return "draft"
    return "open"


async def fetch_pr(
    repo: str, number: int, *, token: str | None = None
) -> PullRequest:
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        resp = await http.get(f"/repos/{owner}/{name}/pulls/{number}")
        if resp.status_code != 200:
            raise GitHubError(
                resp.status_code,
                f"GET /pulls/{number} → {resp.status_code}: {resp.text[:200]}",
            )
        data = resp.json()

    return PullRequest(
        state=_pr_state(data),
        is_draft=bool(data.get("draft")),
        merged_at=_parse_dt(data.get("merged_at")),
        closed_at=_parse_dt(data.get("closed_at")),
        html_url=data.get("html_url") or "",
        title=data.get("title") or "",
        body=data.get("body") or "",
        head_sha=(data.get("head") or {}).get("sha") or "",
        author_login=(data.get("user") or {}).get("login"),
    )


async def list_issue_comments(
    repo: str, number: int, *, token: str | None = None
) -> list[Comment]:
    """Top-level PR comments (no anchor)."""
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        comments = await _paginate(
            http, f"/repos/{owner}/{name}/issues/{number}/comments"
        )
    return [_issue_comment_to_dto(c) for c in comments]


async def list_review_comments(
    repo: str, number: int, *, token: str | None = None
) -> list[Comment]:
    """Inline review comments anchored to file+line."""
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        comments = await _paginate(
            http, f"/repos/{owner}/{name}/pulls/{number}/comments"
        )
    return [_review_comment_to_dto(c) for c in comments]


async def list_reviews(
    repo: str, number: int, *, token: str | None = None
) -> list[Comment]:
    """PR-level reviews (summary body + state). Only those with a non-empty body."""
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        reviews = await _paginate(
            http, f"/repos/{owner}/{name}/pulls/{number}/reviews"
        )
    return [_review_to_dto(r) for r in reviews if (r.get("body") or "").strip()]


async def create_issue_comment(
    repo: str, number: int, body: str, *, token: str | None = None
) -> Comment:
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        resp = await http.post(
            f"/repos/{owner}/{name}/issues/{number}/comments",
            json={"body": body},
        )
        if resp.status_code not in (200, 201):
            raise GitHubError(
                resp.status_code,
                f"POST /issues/{number}/comments → {resp.status_code}: {resp.text[:200]}",
            )
        return _issue_comment_to_dto(resp.json())


async def fetch_file_at_ref(
    repo: str,
    path: str,
    ref: str,
    *,
    token: str | None = None,
) -> str:
    """Return the full text content of a file at a specific ref.

    Uses ``/contents`` with ``Accept: application/vnd.github.raw`` so GitHub
    streams the file verbatim instead of the base64-wrapped JSON envelope.
    Raises ``GitHubError`` on 404 (path doesn't exist at ref) and on size
    limits — GitHub refuses files > 100 MiB on this endpoint.
    """
    owner, name = _split_repo(repo)
    async with httpx.AsyncClient(
        base_url=GITHUB_API,
        timeout=DEFAULT_TIMEOUT,
        headers={
            "Accept": "application/vnd.github.raw",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {_resolve_token(token)}",
            "User-Agent": "unravel-saas/0.0.0-phase1",
        },
    ) as http:
        # Encode path components but keep '/' separators.
        from urllib.parse import quote

        encoded = quote(path, safe="/")
        resp = await http.get(
            f"/repos/{owner}/{name}/contents/{encoded}", params={"ref": ref}
        )
        if resp.status_code != 200:
            raise GitHubError(
                resp.status_code,
                f"GET /contents/{path}?ref={ref} → {resp.status_code}: {resp.text[:200]}",
            )
        return resp.text


async def create_review_comment_reply(
    repo: str,
    number: int,
    parent_comment_id: int,
    body: str,
    *,
    token: str | None = None,
) -> Comment:
    """Reply to an inline review comment thread.

    GitHub's reply endpoint requires the parent comment id (not the review id);
    the response is a brand-new ``review_comment`` whose ``in_reply_to_id``
    points at the parent. The reply inherits the parent's anchor and
    ``pull_request_review_id``.
    """
    owner, name = _split_repo(repo)
    async with _client(token) as http:
        resp = await http.post(
            f"/repos/{owner}/{name}/pulls/{number}/comments/{parent_comment_id}/replies",
            json={"body": body},
        )
        if resp.status_code not in (200, 201):
            raise GitHubError(
                resp.status_code,
                f"POST /pulls/{number}/comments/{parent_comment_id}/replies → "
                f"{resp.status_code}: {resp.text[:200]}",
            )
        return _review_comment_to_dto(resp.json())


async def _paginate(http: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
    """Walk through GitHub's Link-header pagination, collecting every page."""
    out: list[dict[str, Any]] = []
    url: str | None = f"{path}?per_page=100"
    while url:
        resp = await http.get(url)
        if resp.status_code != 200:
            raise GitHubError(
                resp.status_code,
                f"GET {url} → {resp.status_code}: {resp.text[:200]}",
            )
        out.extend(resp.json())
        # ``next`` link is the only one we care about; absent on the last page.
        url = _next_link(resp.headers.get("Link"))
    return out


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        seg = part.strip()
        if seg.endswith('rel="next"'):
            start = seg.find("<")
            end = seg.find(">")
            if start != -1 and end != -1:
                return seg[start + 1 : end]
    return None


def _issue_comment_to_dto(payload: dict[str, Any]) -> Comment:
    user = payload.get("user") or {}
    return Comment(
        github_id=int(payload["id"]),
        kind="issue",
        author_login=user.get("login"),
        author_avatar_url=user.get("avatar_url"),
        body=payload.get("body") or "",
        html_url=payload.get("html_url"),
        anchor_path=None,
        anchor_line=None,
        anchor_side=None,
        anchor_start_line=None,
        anchor_start_side=None,
        is_outdated=False,
        review_state=None,
        in_reply_to_github_id=None,
        pull_request_review_id=None,
        github_created_at=_parse_dt(payload.get("created_at")),
        github_updated_at=_parse_dt(payload.get("updated_at")),
    )


def _review_comment_to_dto(payload: dict[str, Any]) -> Comment:
    user = payload.get("user") or {}
    # GitHub uses ``position is None`` as the canonical "this comment no
    # longer maps to a current diff line" signal. ``line`` may still be set
    # (the historical line number) but the UI should mark it outdated.
    is_outdated = payload.get("position") is None and bool(
        payload.get("original_line")
    )
    return Comment(
        github_id=int(payload["id"]),
        kind="review_comment",
        author_login=user.get("login"),
        author_avatar_url=user.get("avatar_url"),
        body=payload.get("body") or "",
        html_url=payload.get("html_url"),
        anchor_path=payload.get("path"),
        anchor_line=payload.get("line") or payload.get("original_line"),
        anchor_side=payload.get("side"),
        anchor_start_line=payload.get("start_line")
        or payload.get("original_start_line"),
        anchor_start_side=payload.get("start_side"),
        is_outdated=is_outdated,
        review_state=None,
        in_reply_to_github_id=payload.get("in_reply_to_id"),
        pull_request_review_id=payload.get("pull_request_review_id"),
        github_created_at=_parse_dt(payload.get("created_at")),
        github_updated_at=_parse_dt(payload.get("updated_at")),
    )


def _review_to_dto(payload: dict[str, Any]) -> Comment:
    user = payload.get("user") or {}
    review_id = int(payload["id"])
    return Comment(
        github_id=review_id,
        kind="review",
        author_login=user.get("login"),
        author_avatar_url=user.get("avatar_url"),
        body=payload.get("body") or "",
        html_url=payload.get("html_url"),
        anchor_path=None,
        anchor_line=None,
        anchor_side=None,
        anchor_start_line=None,
        anchor_start_side=None,
        is_outdated=False,
        review_state=payload.get("state"),
        in_reply_to_github_id=None,
        # Self-reference so the client can join ``review_comment`` rows whose
        # ``pull_request_review_id`` matches this review without a separate lookup.
        pull_request_review_id=review_id,
        github_created_at=_parse_dt(payload.get("submitted_at")),
        github_updated_at=_parse_dt(payload.get("submitted_at")),
    )
