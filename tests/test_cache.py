"""Tests for the walkthrough cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from unravel import cache
from unravel.models import Walkthrough


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect the cache to a tmp dir so tests don't touch the user's real cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    yield tmp_path


class TestCacheKey:
    def test_stable_for_identical_input(self):
        a = cache.cache_key("diff", "claude-api", "claude-sonnet-4-6")
        b = cache.cache_key("diff", "claude-api", "claude-sonnet-4-6")
        assert a == b

    def test_changes_when_diff_changes(self):
        a = cache.cache_key("diff A", "claude-api", "m")
        b = cache.cache_key("diff B", "claude-api", "m")
        assert a != b

    def test_changes_when_model_changes(self):
        a = cache.cache_key("diff", "claude-api", "claude-sonnet-4-6")
        b = cache.cache_key("diff", "claude-api", "claude-opus-4-6")
        assert a != b

    def test_changes_when_provider_changes(self):
        a = cache.cache_key("diff", "claude-api", "m")
        b = cache.cache_key("diff", "openai", "m")
        assert a != b


class TestRoundTrip:
    def test_load_miss_returns_none(self):
        assert cache.load("diff", "claude-api", "m") is None

    def test_save_then_load(
        self, sample_walkthrough: Walkthrough, simple_diff: str
    ):
        cache.save(
            simple_diff,
            "claude-api",
            "claude-sonnet-4-6",
            sample_walkthrough,
            source_label="range:HEAD~1..HEAD",
        )
        entry = cache.load(simple_diff, "claude-api", "claude-sonnet-4-6")
        assert entry is not None
        assert entry.source_label == "range:HEAD~1..HEAD"
        assert entry.provider == "claude-api"
        assert entry.model == "claude-sonnet-4-6"
        assert len(entry.walkthrough.threads) == len(sample_walkthrough.threads)
        assert entry.walkthrough.raw_diff == simple_diff

    def test_miss_on_different_diff(
        self, sample_walkthrough: Walkthrough, simple_diff: str
    ):
        cache.save(
            simple_diff,
            "claude-api",
            "m",
            sample_walkthrough,
            source_label="",
        )
        assert cache.load(simple_diff + "\n", "claude-api", "m") is None

    def test_corrupt_entry_returns_none(self, isolated_cache: Path):
        (isolated_cache / "unravel").mkdir()
        path = cache.cache_dir() / (
            cache.cache_key("diff", "p", "m") + ".json"
        )
        path.write_text("{ not valid json")
        assert cache.load("diff", "p", "m") is None


class TestClearAll:
    def test_clear_empty(self):
        assert cache.clear_all() == 0

    def test_clear_removes_entries(
        self, sample_walkthrough: Walkthrough, simple_diff: str
    ):
        cache.save(simple_diff, "p", "m1", sample_walkthrough, source_label="a")
        cache.save(simple_diff, "p", "m2", sample_walkthrough, source_label="b")
        assert cache.clear_all() == 2
        assert cache.load(simple_diff, "p", "m1") is None


class TestListEntries:
    def test_empty(self):
        assert cache.list_entries() == []

    def test_entries_newest_first(
        self, sample_walkthrough: Walkthrough, simple_diff: str
    ):
        cache.save(simple_diff, "p", "m1", sample_walkthrough, source_label="a")
        cache.save(
            simple_diff + "\n", "p", "m2", sample_walkthrough, source_label="b"
        )
        entries = cache.list_entries()
        assert len(entries) == 2
        # Newest first — m2 was saved last.
        assert entries[0].model == "m2"
        assert entries[1].model == "m1"
