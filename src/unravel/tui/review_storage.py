"""Disk persistence for pending review state, keyed per PR.

Lives under ``$XDG_CACHE_HOME/unravel/pending_reviews/`` (defaulting to
``~/.cache/unravel/pending_reviews/``), one JSON file per (repo, PR).

Save is called on every pending-review mutation, so if the user quits
mid-session — intentionally or otherwise — the next ``unravel pr <num>``
on the same PR restores their queued comments. The file is removed when
a review is submitted or explicitly discarded.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from unravel.tui.review_state import PendingReview, PendingReviewComment, PrContext


def _root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "unravel" / "pending_reviews"


def _path_for(ctx: PrContext) -> Path:
    safe_repo = re.sub(r"[^a-zA-Z0-9._-]", "_", ctx.repo_nwo)
    return _root() / f"{safe_repo}--{ctx.pr_number}.json"


def load_pending(ctx: PrContext) -> PendingReview | None:
    """Return the pending review for this PR, or ``None`` if nothing saved.

    Returns ``None`` on missing/corrupt files rather than raising — the TUI
    should be able to start cleanly even when the cache is hostile.
    """
    path = _path_for(ctx)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    pending = PendingReview(summary=str(data.get("summary") or ""))
    for raw in data.get("comments") or []:
        try:
            pending.comments.append(
                PendingReviewComment(
                    path=raw["path"],
                    line=int(raw["line"]),
                    side=raw["side"],
                    body=raw["body"],
                    start_line=raw.get("start_line"),
                    start_side=raw.get("start_side"),
                )
            )
        except (KeyError, ValueError, TypeError):
            # Skip malformed entries rather than failing the whole load.
            continue
    return pending


def save_pending(ctx: PrContext, pending: PendingReview) -> None:
    """Write the pending review to disk. Idempotent."""
    path = _path_for(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": pending.summary,
        "comments": [
            {
                "path": c.path,
                "line": c.line,
                "side": c.side,
                "body": c.body,
                "start_line": c.start_line,
                "start_side": c.start_side,
            }
            for c in pending.comments
        ],
    }
    path.write_text(json.dumps(payload, indent=2))


def discard_pending(ctx: PrContext) -> None:
    """Remove the on-disk pending review for this PR, if any."""
    path = _path_for(ctx)
    try:
        path.unlink()
    except FileNotFoundError:
        return
