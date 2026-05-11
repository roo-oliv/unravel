"""Disk-backed fixture loader for Phase 0.

Fixtures are JSON files produced by ``unravel pr <num> --json``. The slug
maps 1:1 to the file stem under ``fixtures/`` at the repo root.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def fixtures_dir() -> Path:
    """Resolve the fixtures directory.

    Override with ``UNRAVEL_FIXTURES_DIR``. Defaults to ``<repo>/fixtures``
    relative to this module (six levels up: api → unravel → src → repo).
    """
    import os

    override = os.environ.get("UNRAVEL_FIXTURES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "fixtures"


@dataclass(frozen=True)
class FixtureEntry:
    slug: str
    path: Path


def list_fixtures() -> list[FixtureEntry]:
    base = fixtures_dir()
    if not base.is_dir():
        return []
    return sorted(
        (FixtureEntry(slug=p.stem, path=p) for p in base.glob("*.json")),
        key=lambda e: e.slug,
    )


def load_fixture(slug: str) -> dict:
    """Load a fixture by slug. Raises ``FileNotFoundError`` if missing."""
    base = fixtures_dir()
    path = base / f"{slug}.json"
    # Guard against path traversal — slug must resolve inside fixtures_dir.
    resolved = path.resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise FileNotFoundError(slug)
    if not resolved.is_file():
        raise FileNotFoundError(slug)
    with resolved.open("r", encoding="utf-8") as f:
        return json.load(f)
