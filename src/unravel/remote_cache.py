"""Remote cache: fetch pre-computed walkthroughs from GitHub PR comments.

When the Unravel GitHub Action runs on a PR it posts a comment containing both
a human-readable walkthrough and a base64-encoded JSON payload hidden inside an
HTML comment.  This module extracts that payload so ``unravel pr`` can skip the
expensive LLM call entirely.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess

from unravel.git import get_repo_nwo
from unravel.models import Walkthrough
from unravel.renderer import COMMENT_MARKER_DATA_PREFIX, COMMENT_MARKER_START


def fetch_from_pr_comment(
    pr_number: int,
    raw_diff: str,
    *,
    remote: str = "origin",
    repo: str | None = None,
) -> Walkthrough | None:
    """Return a cached walkthrough from the PR comment, or ``None`` on miss."""
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
                "--jq", ".[].body",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    for body in _split_comment_bodies(result.stdout):
        walkthrough = _extract_walkthrough(body, raw_diff)
        if walkthrough is not None:
            return walkthrough

    return None


def _split_comment_bodies(raw: str) -> list[str]:
    """Split concatenated ``--jq '.[].body'`` output into individual bodies.

    ``gh api --jq '.[].body'`` prints each comment body on its own line(s).
    We look for the start marker to delimit where each relevant body begins.
    """
    bodies: list[str] = []
    current: list[str] = []
    capturing = False

    for line in raw.splitlines(keepends=True):
        if COMMENT_MARKER_START in line:
            if capturing and current:
                bodies.append("".join(current))
            current = [line]
            capturing = True
        elif capturing:
            current.append(line)

    if capturing and current:
        bodies.append("".join(current))

    return bodies


def _extract_walkthrough(body: str, raw_diff: str) -> Walkthrough | None:
    """Parse the base64 payload from a single comment body."""
    if COMMENT_MARKER_START not in body:
        return None

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(COMMENT_MARKER_DATA_PREFIX):
            payload = stripped[len(COMMENT_MARKER_DATA_PREFIX):]
            # Remove trailing " -->"
            if payload.endswith("-->"):
                payload = payload[:-3].rstrip()
            try:
                decoded = base64.b64decode(payload).decode("utf-8")
                data = json.loads(decoded)
                return Walkthrough.from_dict(data, raw_diff=raw_diff)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                return None

    return None
