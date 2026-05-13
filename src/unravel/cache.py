"""Local cache for walkthrough analyses.

Caches the full LLM-analyzed walkthrough keyed by (raw_diff, provider, model)
so that re-running unravel on the same diff skips the expensive LLM call.
The cache lives under ``$XDG_CACHE_HOME/unravel`` (defaulting to
``~/.cache/unravel``) and stores one JSON file per entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from unravel.models import Walkthrough

CACHE_VERSION = 1


def _cache_root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "unravel"


def cache_dir() -> Path:
    """Return the cache directory, creating it if it doesn't exist."""
    path = _cache_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(raw_diff: str, provider: str, model: str) -> str:
    """Build a stable hash identifying this diff + model combination."""
    h = hashlib.sha256()
    h.update(provider.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(raw_diff.encode("utf-8"))
    return h.hexdigest()


def _entry_path(key: str) -> Path:
    return cache_dir() / f"{key}.json"


@dataclass
class CacheEntry:
    walkthrough: Walkthrough
    cached_at: float
    source_label: str
    provider: str
    model: str


def load(
    raw_diff: str,
    provider: str,
    model: str,
) -> CacheEntry | None:
    """Return the cached walkthrough for this diff, or ``None`` on miss."""
    key = cache_key(raw_diff, provider, model)
    path = _entry_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    wrapper = data.get("unravel_cache") or {}
    wt_data = data.get("walkthrough")
    if not isinstance(wt_data, dict):
        return None
    try:
        walkthrough = Walkthrough.from_dict(wt_data, raw_diff=raw_diff)
    except (KeyError, TypeError):
        return None

    return CacheEntry(
        walkthrough=walkthrough,
        cached_at=float(wrapper.get("cached_at", 0.0)),
        source_label=str(wrapper.get("source_label", "")),
        provider=str(wrapper.get("provider", provider)),
        model=str(wrapper.get("model", model)),
    )


def save(
    raw_diff: str,
    provider: str,
    model: str,
    walkthrough: Walkthrough,
    *,
    source_label: str,
) -> Path:
    """Persist ``walkthrough`` to the cache and return the entry path."""
    key = cache_key(raw_diff, provider, model)
    path = _entry_path(key)
    payload = {
        "unravel_cache": {
            "version": CACHE_VERSION,
            "cached_at": time.time(),
            "source_label": source_label,
            "provider": provider,
            "model": model,
        },
        "walkthrough": walkthrough.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def clear_all() -> int:
    """Remove every cache entry. Returns the count of removed entries."""
    root = _cache_root()
    if not root.exists():
        return 0
    count = sum(1 for _ in root.glob("*.json"))
    shutil.rmtree(root)
    return count


@dataclass
class CacheListing:
    path: Path
    cached_at: float
    source_label: str
    provider: str
    model: str


def list_entries() -> list[CacheListing]:
    """Return metadata for every cached entry, newest first."""
    root = _cache_root()
    if not root.exists():
        return []
    out: list[CacheListing] = []
    for p in root.glob("*.json"):
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("unravel_cache") or {}
        out.append(
            CacheListing(
                path=p,
                cached_at=float(meta.get("cached_at", 0.0)),
                source_label=str(meta.get("source_label", "")),
                provider=str(meta.get("provider", "")),
                model=str(meta.get("model", "")),
            )
        )
    out.sort(key=lambda e: e.cached_at, reverse=True)
    return out


def find_previous_for_source(
    source_label: str,
    current_raw_diff: str,
    provider: str,
    model: str,
) -> Walkthrough | None:
    """Return the most recent cached walkthrough for ``source_label`` whose
    diff differs from the current one.

    Used to feed the previous walkthrough back to the model on a re-run so it
    can preserve thread structure for unchanged hunks. Filters by provider so
    we don't mix output styles across providers.
    """
    if not source_label:
        return None
    current_key = cache_key(current_raw_diff, provider, model)
    candidates = [
        entry
        for entry in list_entries()
        if entry.source_label == source_label and entry.provider == provider
    ]
    for entry in candidates:
        if entry.path.stem == current_key:
            continue
        try:
            data = json.loads(entry.path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        wt_data = data.get("walkthrough")
        if not isinstance(wt_data, dict):
            continue
        try:
            return Walkthrough.from_dict(wt_data)
        except (KeyError, TypeError):
            continue
    return None
