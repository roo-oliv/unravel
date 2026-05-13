"""Thin subprocess wrappers around the ``gh`` CLI for TUI review features.

Deliberate non-goals:

- No token plumbing. ``gh`` already has the user's credentials.
- No retries. ``gh`` itself retries network errors; we only surface them.
- No caching. The TUI does its own snapshotting; callers re-invoke to refresh.

Every public function returns parsed Python (lists/dicts/dataclasses) or
raises :class:`GhCliError` with the trimmed stderr. Subprocess calls are
blocking and intended to be invoked from a Textual worker thread.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from unravel.tui.review_state import (
    IssueComment,
    PrSnapshot,
    ReviewComment,
    ReviewSummary,
    parse_pr_state,
)


class GhCliError(Exception):
    """Raised when a ``gh`` invocation exits non-zero or returns malformed JSON."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def _ensure_gh() -> None:
    if not shutil.which("gh"):
        raise GhCliError(
            "GitHub CLI (gh) is required. Install it from https://cli.github.com"
        )


def _run(
    args: list[str], *, stdin: str | None = None, timeout: float = 30.0
) -> str:
    _ensure_gh()
    try:
        result = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GhCliError(f"Command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhCliError(f"{' '.join(args[:3])} timed out") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip() or "unknown error"
        raise GhCliError(stderr, stderr=stderr) from exc
    return result.stdout


def _run_json(args: list[str], *, stdin: str | None = None) -> Any:
    out = _run(args, stdin=stdin)
    if not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise GhCliError(f"Could not parse gh output as JSON: {exc}") from exc


def current_user() -> str | None:
    """Return the authenticated ``gh`` user's login, or ``None`` if not logged in."""
    try:
        out = _run(["gh", "api", "user", "--jq", ".login"]).strip()
        return out or None
    except GhCliError:
        return None


# ---------- Fetching ----------


def fetch_pr(repo_nwo: str, pr_number: int) -> dict[str, Any]:
    """Return ``gh pr view`` JSON. Keep raw so the snapshot builder can pick fields."""
    return _run_json(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "-R",
            repo_nwo,
            "--json",
            "state,isDraft,mergedAt,closedAt,author,title,body,headRefOid,url",
        ]
    )


def fetch_issue_comments(repo_nwo: str, pr_number: int) -> list[dict[str, Any]]:
    return (
        _run_json(
            [
                "gh",
                "api",
                "--paginate",
                f"/repos/{repo_nwo}/issues/{pr_number}/comments",
            ]
        )
        or []
    )


def fetch_review_summaries(repo_nwo: str, pr_number: int) -> list[dict[str, Any]]:
    return (
        _run_json(
            [
                "gh",
                "api",
                "--paginate",
                f"/repos/{repo_nwo}/pulls/{pr_number}/reviews",
            ]
        )
        or []
    )


def fetch_review_comments(repo_nwo: str, pr_number: int) -> list[dict[str, Any]]:
    return (
        _run_json(
            [
                "gh",
                "api",
                "--paginate",
                f"/repos/{repo_nwo}/pulls/{pr_number}/comments",
            ]
        )
        or []
    )


# ---------- Writing ----------


def post_issue_comment(repo_nwo: str, pr_number: int, body: str) -> None:
    """Create a PR-level top-level comment via ``gh pr comment``."""
    _run(
        ["gh", "pr", "comment", str(pr_number), "-R", repo_nwo, "--body-file", "-"],
        stdin=body,
    )


def submit_review(
    repo_nwo: str, pr_number: int, payload: dict[str, Any]
) -> dict[str, Any]:
    """POST a full pull-request review (verdict + summary + inline comments)."""
    body = json.dumps(payload)
    out = _run(
        [
            "gh",
            "api",
            "-X",
            "POST",
            f"/repos/{repo_nwo}/pulls/{pr_number}/reviews",
            "--input",
            "-",
        ],
        stdin=body,
        timeout=60.0,
    )
    try:
        return json.loads(out) if out.strip() else {}
    except json.JSONDecodeError as exc:  # pragma: no cover — unexpected
        raise GhCliError(f"Bad submit_review response: {exc}") from exc


# ---------- Snapshot builder ----------


def build_snapshot(repo_nwo: str, pr_number: int) -> PrSnapshot:
    """Run all four GitHub queries and assemble a :class:`PrSnapshot`.

    Sequential rather than parallel: ``gh`` warms a shared HTTP keepalive
    pool internally, and most PRs fetch all four buckets in under a second
    combined. Parallelism via threads would be a footgun (re-auth races,
    keyring locks on macOS).
    """
    pr = fetch_pr(repo_nwo, pr_number)
    state = parse_pr_state(pr)
    snapshot = PrSnapshot(
        state=state,
        title=pr.get("title") or "",
        body=pr.get("body") or "",
        html_url=pr.get("url") or "",
        head_sha=pr.get("headRefOid") or "",
        author=(pr.get("author") or {}).get("login") or "",
    )

    for raw in fetch_issue_comments(repo_nwo, pr_number):
        snapshot.issue_comments.append(
            IssueComment(
                id=raw["id"],
                author=(raw.get("user") or {}).get("login") or "ghost",
                body=raw.get("body") or "",
                created_at=raw.get("created_at") or "",
                html_url=raw.get("html_url") or "",
            )
        )

    for raw in fetch_review_summaries(repo_nwo, pr_number):
        snapshot.review_summaries.append(
            ReviewSummary(
                id=raw["id"],
                author=(raw.get("user") or {}).get("login") or "ghost",
                state=(raw.get("state") or "COMMENTED").upper(),  # type: ignore[arg-type]
                body=raw.get("body") or "",
                submitted_at=raw.get("submitted_at"),
                commit_id=raw.get("commit_id"),
            )
        )

    for raw in fetch_review_comments(repo_nwo, pr_number):
        # GitHub sets ``line`` to null + ``original_line`` to the historic
        # value when a comment becomes outdated (the commit moved). Either
        # is_outdated comes from a position drift OR from line being null.
        line = raw.get("line")
        original_line = raw.get("original_line")
        is_outdated = line is None and original_line is not None
        snapshot.review_comments.append(
            ReviewComment(
                id=raw["id"],
                review_id=raw.get("pull_request_review_id"),
                in_reply_to_id=raw.get("in_reply_to_id"),
                author=(raw.get("user") or {}).get("login") or "ghost",
                body=raw.get("body") or "",
                path=raw.get("path") or "",
                line=line if line is not None else original_line,
                side=(raw.get("side") or "RIGHT").upper(),  # type: ignore[arg-type]
                start_line=raw.get("start_line") or raw.get("original_start_line"),
                start_side=(raw.get("start_side") or None),
                is_outdated=is_outdated,
                created_at=raw.get("created_at") or "",
            )
        )

    return snapshot
