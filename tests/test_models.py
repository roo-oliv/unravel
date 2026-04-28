"""Tests for domain data classes."""

from __future__ import annotations

import json

from unravel.models import Hunk, Thread, ThreadStep, Walkthrough


class TestHunk:
    def test_round_trip(self):
        hunk = Hunk(
            file_path="src/main.py",
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=7,
            content="+added line\n-removed line\n",
            language="python",
        )
        data = hunk.to_dict()
        restored = Hunk.from_dict(data)
        assert restored.file_path == hunk.file_path
        assert restored.old_start == hunk.old_start
        assert restored.new_count == hunk.new_count
        assert restored.content == hunk.content
        assert restored.language == hunk.language

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "file_path": "a.py",
            "old_start": 1,
            "old_count": 1,
            "new_start": 1,
            "new_count": 1,
            "content": "",
            "extra_key": "ignored",
        }
        hunk = Hunk.from_dict(data)
        assert hunk.file_path == "a.py"

    def test_new_fields_round_trip(self):
        hunk = Hunk(
            file_path="a.py",
            additions=4,
            deletions=2,
            caption="New imports",
        )
        restored = Hunk.from_dict(hunk.to_dict())
        assert restored.additions == 4
        assert restored.deletions == 2
        assert restored.caption == "New imports"

    def test_from_dict_defaults_missing_new_fields(self):
        # Old cache payloads predate additions/deletions/caption.
        data = {
            "file_path": "a.py",
            "old_start": 1,
            "old_count": 1,
            "new_start": 1,
            "new_count": 1,
            "content": "",
        }
        hunk = Hunk.from_dict(data)
        assert hunk.additions == 0
        assert hunk.deletions == 0
        assert hunk.caption == ""


class TestThreadStep:
    def test_round_trip(self):
        step = ThreadStep(
            hunks=[
                Hunk(
                    file_path="a.py",
                    old_start=1,
                    old_count=2,
                    new_start=1,
                    new_count=3,
                    content="diff content",
                )
            ],
            narration="This adds validation.",
            order=1,
        )
        data = step.to_dict()
        restored = ThreadStep.from_dict(data)
        assert len(restored.hunks) == 1
        assert restored.narration == step.narration
        assert restored.order == step.order


class TestThread:
    def test_round_trip(self):
        thread = Thread(
            id="add-validation",
            title="Add input validation",
            summary="Validates user input before processing.",
            root_cause="Missing validation caused crashes on bad input.",
            steps=[
                ThreadStep(
                    hunks=[
                        Hunk(
                            file_path="handler.py",
                            old_start=5,
                            old_count=3,
                            new_start=5,
                            new_count=6,
                            content="diff",
                        )
                    ],
                    narration="Add validation check.",
                    order=1,
                )
            ],
            dependencies=["setup-types"],
        )
        data = thread.to_dict()
        restored = Thread.from_dict(data)
        assert restored.id == thread.id
        assert restored.dependencies == ["setup-types"]
        assert len(restored.steps) == 1


class TestWalkthrough:
    def test_json_round_trip(self, sample_walkthrough: Walkthrough, simple_diff: str):
        json_str = sample_walkthrough.to_json()
        restored = Walkthrough.from_json(json_str, raw_diff=simple_diff)
        assert len(restored.threads) == len(sample_walkthrough.threads)
        assert restored.overview == sample_walkthrough.overview
        assert restored.suggested_order == sample_walkthrough.suggested_order

    def test_raw_diff_excluded_from_json(self, sample_walkthrough: Walkthrough):
        data = json.loads(sample_walkthrough.to_json())
        assert "raw_diff" not in data

    def test_from_dict_with_fixture(self, sample_response_dict: dict, simple_diff: str):
        wt = Walkthrough.from_dict(sample_response_dict, raw_diff=simple_diff)
        assert len(wt.threads) == 2
        assert wt.threads[0].id == "auth-error-handling"
        assert wt.threads[1].dependencies == ["auth-error-handling"]
        assert wt.raw_diff == simple_diff

    def test_hunk_captions_round_trip(self, sample_walkthrough: Walkthrough, simple_diff: str):
        sample_walkthrough.hunk_captions = {"H1": "New imports", "H2": "Constants update"}
        restored = Walkthrough.from_json(
            sample_walkthrough.to_json(), raw_diff=simple_diff
        )
        assert restored.hunk_captions == {"H1": "New imports", "H2": "Constants update"}

    def test_from_dict_defaults_missing_hunk_captions(
        self, sample_response_dict: dict, simple_diff: str
    ):
        # Simulate an old cached payload that predates hunk_captions.
        legacy = {k: v for k, v in sample_response_dict.items() if k != "hunk_captions"}
        wt = Walkthrough.from_dict(legacy, raw_diff=simple_diff)
        assert wt.hunk_captions == {}
