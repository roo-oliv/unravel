"""Remote cache: fetch pre-computed walkthroughs from GitHub PR comments.

When the Unravel GitHub Action runs on a PR it posts a comment containing both
a human-readable walkthrough and a base64-encoded JSON payload hidden inside an
HTML comment.  This module extracts that payload so ``unravel pr`` can skip the
expensive LLM call entirely.

The action also posts a SHA-stamped placeholder up-front (``status:in-progress``)
so reviewers see something while the analysis runs. ``fetch_from_pr_comment``
returns the placeholder so the CLI can offer to wait, run locally, or exit;
``poll_pr_comment`` is the helper that re-checks the comment until status flips.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Literal

from unravel.git import get_repo_nwo
from unravel.models import Walkthrough
from unravel.renderer import (
    COMMENT_MARKER_DATA_PREFIX,
    COMMENT_MARKER_SHA_PREFIX,
    COMMENT_MARKER_START,
    COMMENT_MARKER_STATUS_PREFIX,
    COMMENT_MARKER_SUFFIX,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
)

Status = Literal["in-progress", "done", "failed"]


@dataclass
class RemoteComment:
    """A v2 unravel-cache PR comment, with parsed envelope fields."""

    comment_id: int
    sha: str
    status: Status
    walkthrough: Walkthrough | None  # populated only when status == "done"


def fetch_from_pr_comment(
    pr_number: int,
    raw_diff: str,
    *,
    expected_sha: str,
    remote: str = "origin",
    repo: str | None = None,
) -> RemoteComment | None:
    """Return the most recent SHA-matching unravel comment on the PR.

    Returns ``None`` when:
    - ``gh`` is unavailable or the API call fails
    - the PR has no v2 unravel comment
    - every v2 comment has a SHA different from *expected_sha* (stale cache)
    """
    nwo = repo or get_repo_nwo(remote)
    if not nwo:
        return None
    if not shutil.which("gh"):
        return None

    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{nwo}/issues/{pr_number}/comments",
                "--paginate",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    try:
        comments = _parse_paginated_comments(result.stdout)
    except json.JSONDecodeError:
        return None

    # GitHub returns comments oldest-first; newest match wins.
    for comment in reversed(comments):
        body = comment.get("body") or ""
        if COMMENT_MARKER_START not in body:
            continue
        parsed = _parse_envelope(body)
        if parsed is None:
            continue
        if parsed["sha"] != expected_sha:
            continue
        comment_id = comment.get("id")
        if not isinstance(comment_id, int):
            continue
        walkthrough: Walkthrough | None = None
        if parsed["status"] == STATUS_DONE and parsed["data"]:
            walkthrough = _decode_walkthrough(parsed["data"], raw_diff)
            if walkthrough is None:
                # Body is malformed; skip and let caller fall through.
                continue
        return RemoteComment(
            comment_id=comment_id,
            sha=parsed["sha"],
            status=parsed["status"],
            walkthrough=walkthrough,
        )

    return None


def poll_pr_comment(
    comment_id: int,
    *,
    repo: str,
    raw_diff: str,
    expected_sha: str,
    interval: float = 10.0,
    timeout: float = 300.0,
) -> Walkthrough:
    """Poll a single comment by id until it flips to ``status:done``.

    Raises ``TimeoutError`` when *timeout* elapses without a done state.
    Raises ``RuntimeError`` if the comment's SHA changes (a new analysis
    started) or the comment goes into ``status:failed``.
    """
    if not shutil.which("gh"):
        raise RuntimeError("gh is required to poll PR comments")

    deadline = time.monotonic() + timeout
    while True:
        try:
            result = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{repo}/issues/comments/{comment_id}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
            payload = None

        if isinstance(payload, dict):
            body = payload.get("body") or ""
            parsed = _parse_envelope(body)
            if parsed is not None:
                if parsed["sha"] != expected_sha:
                    raise RuntimeError(
                        "Remote unravel comment is now for a different commit "
                        f"({parsed['sha'][:7]}); the PR has moved on."
                    )
                if parsed["status"] == STATUS_FAILED:
                    raise RuntimeError(
                        "Remote unravel reported failure — check the action logs."
                    )
                if parsed["status"] == STATUS_DONE and parsed["data"]:
                    walkthrough = _decode_walkthrough(parsed["data"], raw_diff)
                    if walkthrough is not None:
                        return walkthrough

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out after {timeout:.0f}s waiting for remote unravel."
            )
        time.sleep(interval)


def _parse_paginated_comments(raw: str) -> list[dict]:
    """Parse ``gh api --paginate`` output into a flat list of comments.

    ``--paginate`` concatenates each page's JSON array. The result is
    ``[{...}][{...}]`` rather than valid JSON, so we use ``raw_decode`` to
    walk the string one array at a time.
    """
    decoder = json.JSONDecoder()
    out: list[dict] = []
    idx = 0
    text = raw.strip()
    while idx < len(text):
        # Skip whitespace between pages.
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        page, end = decoder.raw_decode(text, idx)
        if isinstance(page, list):
            out.extend(c for c in page if isinstance(c, dict))
        idx = end
    return out


def _parse_envelope(body: str) -> dict | None:
    """Extract sha, status, and (optionally) data from a v2 comment body.

    Returns ``None`` if any required field is missing or malformed.
    """
    sha: str | None = None
    status: str | None = None
    data: str | None = None
    saw_start = False

    for line in body.splitlines():
        stripped = line.strip()
        if stripped == COMMENT_MARKER_START:
            saw_start = True
            continue
        if not saw_start:
            continue
        if stripped.startswith(COMMENT_MARKER_SHA_PREFIX):
            sha = _strip_marker(stripped, COMMENT_MARKER_SHA_PREFIX)
        elif stripped.startswith(COMMENT_MARKER_STATUS_PREFIX):
            status = _strip_marker(stripped, COMMENT_MARKER_STATUS_PREFIX)
        elif stripped.startswith(COMMENT_MARKER_DATA_PREFIX):
            data = _strip_marker(stripped, COMMENT_MARKER_DATA_PREFIX)

    if not sha or not status:
        return None
    if status not in (STATUS_IN_PROGRESS, STATUS_DONE, STATUS_FAILED):
        return None
    return {"sha": sha, "status": status, "data": data}


def _strip_marker(line: str, prefix: str) -> str:
    payload = line[len(prefix):]
    if payload.endswith(COMMENT_MARKER_SUFFIX):
        payload = payload[: -len(COMMENT_MARKER_SUFFIX)]
    return payload.strip()


def _decode_walkthrough(payload: str, raw_diff: str) -> Walkthrough | None:
    try:
        decoded = base64.b64decode(payload).decode("utf-8")
        data = json.loads(decoded)
        return Walkthrough.from_dict(data, raw_diff=raw_diff)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
