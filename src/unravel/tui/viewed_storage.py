"""Disk persistence for "viewed" hunk marks, scoped per source (PR or range).

Lives under ``$XDG_CACHE_HOME/unravel/viewed/`` (defaulting to
``~/.cache/unravel/viewed/``), one JSON file per source. The payload is a set
of stable hunk ``content_hash`` values, so a re-run on the same PR with a
different head SHA still matches the viewed marks for hunks whose textual
content is unchanged. Altered hunks get a new content_hash and therefore start
unchecked, which is the intended behaviour.

CLI-only: web persistence is handled by the ``hunk_viewed`` DB table.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from unravel.models import SourceInfo
from unravel.tui.review_state import PrContext


def _root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "unravel" / "viewed"


def _key_for(source_info: SourceInfo | None, pr_ctx: PrContext | None) -> str:
    if pr_ctx is not None:
        safe_repo = re.sub(r"[^a-zA-Z0-9._-]", "_", pr_ctx.repo_nwo)
        return f"{safe_repo}--pr{pr_ctx.pr_number}"
    if source_info is not None:
        return re.sub(r"[^a-zA-Z0-9._-]", "_", source_info.label) or "unknown"
    return "unknown"


def _path_for(source_info: SourceInfo | None, pr_ctx: PrContext | None) -> Path:
    return _root() / f"{_key_for(source_info, pr_ctx)}.json"


def load_viewed(
    source_info: SourceInfo | None, pr_ctx: PrContext | None = None
) -> set[str]:
    """Return the set of viewed content_hashes for this source.

    Returns an empty set on missing/corrupt files rather than raising.
    """
    path = _path_for(source_info, pr_ctx)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    raw = data.get("viewed_content_hashes") or []
    return {str(h) for h in raw if isinstance(h, str) and h}


def save_viewed(
    source_info: SourceInfo | None,
    hashes: set[str],
    pr_ctx: PrContext | None = None,
) -> None:
    """Write the viewed set to disk. Idempotent."""
    path = _path_for(source_info, pr_ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "viewed_content_hashes": sorted(hashes),
        "updated_at": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2))
