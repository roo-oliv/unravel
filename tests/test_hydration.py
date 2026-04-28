"""Tests for hunk hydration."""

from __future__ import annotations

from unravel.git import parse_diff
from unravel.hydration import hydrate_walkthrough, orphaned_hunks
from unravel.models import Hunk, Thread, ThreadStep, Walkthrough


class TestHydrateWalkthrough:
    def test_exact_id_match(self, simple_diff: str):
        parsed = parse_diff(simple_diff)
        first = parsed[0]

        wt = Walkthrough(
            threads=[
                Thread(
                    id="t1",
                    title="T1",
                    summary="s",
                    root_cause="r",
                    steps=[
                        ThreadStep(
                            hunks=[Hunk(id=first.id)],
                            narration="test",
                            order=1,
                        )
                    ],
                )
            ],
            overview="test",
            suggested_order=["t1"],
            hunk_captions={first.id: "Init guard"},
        )

        wt, warnings = hydrate_walkthrough(wt, parsed)
        resolved = wt.threads[0].steps[0].hunks[0]
        assert resolved.content == first.content
        assert resolved.language == first.language
        assert resolved.file_path == first.file_path
        assert resolved.additions == first.additions
        assert resolved.deletions == first.deletions
        assert resolved.caption == "Init guard"
        assert warnings == []

    def test_missing_caption_warns_with_summary(self, simple_diff: str):
        # Partial captions: H1 has one, H2 doesn't. Should produce a single
        # summary warning naming the missing IDs (not one per hunk).
        parsed = parse_diff(simple_diff)
        first, second = parsed[0], parsed[1]

        wt = Walkthrough(
            threads=[
                Thread(
                    id="t1",
                    title="T1",
                    summary="s",
                    root_cause="r",
                    steps=[
                        ThreadStep(
                            hunks=[Hunk(id=first.id), Hunk(id=second.id)],
                            narration="test",
                            order=1,
                        )
                    ],
                )
            ],
            overview="test",
            suggested_order=["t1"],
            hunk_captions={first.id: "Init guard"},
        )

        wt, warnings = hydrate_walkthrough(wt, parsed)
        caption_warnings = [w for w in warnings if "caption" in w]
        assert len(caption_warnings) == 1
        assert second.id in caption_warnings[0]
        assert first.id not in caption_warnings[0]

    def test_empty_hunk_captions_does_not_warn(self, simple_diff: str):
        # Old-cache behavior: an entirely empty hunk_captions dict means the
        # walkthrough predates captions; we should silently render without them
        # rather than flooding stdout.
        parsed = parse_diff(simple_diff)
        first = parsed[0]

        wt = Walkthrough(
            threads=[
                Thread(
                    id="t1",
                    title="T1",
                    summary="s",
                    root_cause="r",
                    steps=[
                        ThreadStep(
                            hunks=[Hunk(id=first.id)],
                            narration="test",
                            order=1,
                        )
                    ],
                )
            ],
            overview="test",
            suggested_order=["t1"],
        )

        wt, warnings = hydrate_walkthrough(wt, parsed)
        assert not any("caption" in w for w in warnings)

    def test_unknown_id_warns(self, simple_diff: str):
        parsed = parse_diff(simple_diff)

        wt = Walkthrough(
            threads=[
                Thread(
                    id="t1",
                    title="T1",
                    summary="s",
                    root_cause="r",
                    steps=[
                        ThreadStep(
                            hunks=[Hunk(id="H999")],
                            narration="test",
                            order=1,
                        )
                    ],
                )
            ],
            overview="test",
            suggested_order=["t1"],
        )

        wt, warnings = hydrate_walkthrough(wt, parsed)
        assert wt.threads[0].steps[0].hunks[0].content == ""
        assert any("H999" in w for w in warnings)

    def test_with_fixture(self, sample_walkthrough: Walkthrough, simple_diff: str):
        parsed = parse_diff(simple_diff)
        wt, warnings = hydrate_walkthrough(sample_walkthrough, parsed)
        hydrated_count = sum(
            1
            for t in wt.threads
            for s in t.steps
            for h in s.hunks
            if h.content
        )
        assert hydrated_count > 0
        assert warnings == []


class TestOrphanedHunks:
    def test_no_orphans(self, sample_walkthrough: Walkthrough, simple_diff: str):
        parsed = parse_diff(simple_diff)
        hydrate_walkthrough(sample_walkthrough, parsed)
        assert orphaned_hunks(sample_walkthrough, parsed) == []

    def test_detects_orphans(self, simple_diff: str):
        parsed = parse_diff(simple_diff)
        wt = Walkthrough(
            threads=[
                Thread(
                    id="t1",
                    title="T1",
                    summary="s",
                    root_cause="r",
                    steps=[
                        ThreadStep(
                            hunks=[Hunk(id=parsed[0].id)],
                            narration="only the first",
                            order=1,
                        )
                    ],
                )
            ],
            overview="test",
            suggested_order=["t1"],
        )
        hydrate_walkthrough(wt, parsed)
        orphans = orphaned_hunks(wt, parsed)
        orphan_ids = {o.id for o in orphans}
        assert orphan_ids == {h.id for h in parsed[1:]}
