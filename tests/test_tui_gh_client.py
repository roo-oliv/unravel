"""Tests for the TUI's gh CLI wrapper.

We don't shell out to a real ``gh`` here: the tests monkeypatch
``subprocess.run`` so we can assert (a) the exact argv the wrapper builds
and (b) that the wrapper turns parsed JSON into PrSnapshot fields.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from unravel.tui import gh_client
from unravel.tui.review_state import PrSnapshot


class FakeResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def fake_subprocess(monkeypatch):
    calls: list[dict[str, Any]] = []
    responses: dict[tuple[str, ...], FakeResult] = {}

    def fake_run(args, input=None, capture_output=False, text=False, check=False, timeout=None):  # noqa: ARG001
        calls.append({"args": list(args), "input": input})
        key = tuple(args[:5])
        result = responses.get(key, FakeResult(stdout=""))
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, args, output=result.stdout, stderr=result.stderr
            )
        return result

    monkeypatch.setattr("unravel.tui.gh_client.subprocess.run", fake_run)
    # ensure shutil.which("gh") returns something truthy
    monkeypatch.setattr(
        "unravel.tui.gh_client.shutil.which", lambda name: f"/usr/local/bin/{name}"
    )
    return calls, responses


class TestArgvShape:
    def test_fetch_pr_argv(self, fake_subprocess):
        calls, responses = fake_subprocess
        responses[("gh", "pr", "view", "12", "-R")] = FakeResult(stdout='{"state":"OPEN"}')
        gh_client.fetch_pr("roo-oliv/unravel", 12)
        argv = calls[0]["args"]
        assert argv[:6] == [
            "gh", "pr", "view", "12", "-R", "roo-oliv/unravel"
        ]
        assert "--json" in argv
        json_arg = argv[argv.index("--json") + 1]
        for needed in ("state", "isDraft", "headRefOid", "url", "author"):
            assert needed in json_arg

    def test_issue_comments_uses_paginate(self, fake_subprocess):
        calls, responses = fake_subprocess
        responses[("gh", "api", "--paginate", "/repos/o/r/issues/3/comments", None)] = (
            FakeResult(stdout="[]")
        )
        # Different key shape — wrapper uses 4 args, key only first 5 → match prefix
        responses[("gh", "api", "--paginate", "/repos/o/r/issues/3/comments")] = (
            FakeResult(stdout="[]")
        )
        gh_client.fetch_issue_comments("o/r", 3)
        argv = calls[0]["args"]
        assert argv == [
            "gh",
            "api",
            "--paginate",
            "/repos/o/r/issues/3/comments",
        ]

    def test_submit_review_posts_json_via_stdin(self, fake_subprocess):
        calls, responses = fake_subprocess
        responses[("gh", "api", "-X", "POST", "/repos/o/r/pulls/3/reviews")] = FakeResult(
            stdout='{"id": 99}'
        )
        result = gh_client.submit_review(
            "o/r", 3, {"event": "COMMENT", "commit_id": "sha", "comments": []}
        )
        argv = calls[0]["args"]
        assert argv == [
            "gh",
            "api",
            "-X",
            "POST",
            "/repos/o/r/pulls/3/reviews",
            "--input",
            "-",
        ]
        # Stdin is the JSON payload
        assert json.loads(calls[0]["input"])["event"] == "COMMENT"
        assert result == {"id": 99}

    def test_post_issue_comment_uses_pr_comment(self, fake_subprocess):
        calls, responses = fake_subprocess
        responses[("gh", "pr", "comment", "3", "-R")] = FakeResult(stdout="")
        gh_client.post_issue_comment("o/r", 3, "hello world")
        argv = calls[0]["args"]
        assert argv == [
            "gh",
            "pr",
            "comment",
            "3",
            "-R",
            "o/r",
            "--body-file",
            "-",
        ]
        assert calls[0]["input"] == "hello world"


class TestErrorHandling:
    def test_non_zero_exit_raises_gh_cli_error(self, monkeypatch):
        def failing(*args, **kwargs):  # noqa: ARG001
            raise subprocess.CalledProcessError(
                1, args[0], output="", stderr="HTTP 404: Not Found"
            )

        monkeypatch.setattr("unravel.tui.gh_client.subprocess.run", failing)
        monkeypatch.setattr(
            "unravel.tui.gh_client.shutil.which", lambda name: f"/usr/bin/{name}"
        )
        with pytest.raises(gh_client.GhCliError) as exc:
            gh_client.fetch_pr("o/r", 1)
        assert "404" in str(exc.value)

    def test_missing_gh_binary_raises(self, monkeypatch):
        monkeypatch.setattr(
            "unravel.tui.gh_client.shutil.which", lambda name: None
        )
        with pytest.raises(gh_client.GhCliError) as exc:
            gh_client.fetch_pr("o/r", 1)
        assert "GitHub CLI" in str(exc.value)


class TestBuildSnapshot:
    def test_parses_full_response(self, fake_subprocess):
        calls, responses = fake_subprocess

        # PR view
        responses[("gh", "pr", "view", "9", "-R")] = FakeResult(
            stdout=json.dumps(
                {
                    "state": "OPEN",
                    "isDraft": False,
                    "title": "Feature X",
                    "body": "Adds X",
                    "headRefOid": "abc1234",
                    "url": "https://github.com/o/r/pull/9",
                    "author": {"login": "alice"},
                }
            )
        )
        # Issue comments
        responses[("gh", "api", "--paginate", "/repos/o/r/issues/9/comments")] = (
            FakeResult(
                stdout=json.dumps(
                    [
                        {
                            "id": 1,
                            "user": {"login": "bob"},
                            "body": "first",
                            "created_at": "2026-01-01T00:00:00Z",
                            "html_url": "https://github.com/x",
                        }
                    ]
                )
            )
        )
        # Reviews
        responses[("gh", "api", "--paginate", "/repos/o/r/pulls/9/reviews")] = (
            FakeResult(
                stdout=json.dumps(
                    [
                        {
                            "id": 100,
                            "user": {"login": "carol"},
                            "state": "APPROVED",
                            "body": "lgtm",
                            "submitted_at": "2026-01-02T00:00:00Z",
                            "commit_id": "abc1234",
                        }
                    ]
                )
            )
        )
        # Inline comments — one current, one outdated
        responses[("gh", "api", "--paginate", "/repos/o/r/pulls/9/comments")] = (
            FakeResult(
                stdout=json.dumps(
                    [
                        {
                            "id": 200,
                            "pull_request_review_id": 100,
                            "user": {"login": "carol"},
                            "body": "nit",
                            "path": "src/foo.py",
                            "line": 42,
                            "side": "RIGHT",
                            "start_line": None,
                            "start_side": None,
                            "in_reply_to_id": None,
                            "created_at": "2026-01-02T00:00:00Z",
                        },
                        {
                            "id": 201,
                            "pull_request_review_id": 100,
                            "user": {"login": "carol"},
                            "body": "stale",
                            "path": "src/foo.py",
                            "line": None,
                            "original_line": 12,
                            "side": "RIGHT",
                            "start_line": None,
                            "start_side": None,
                            "in_reply_to_id": None,
                            "created_at": "2026-01-02T00:00:00Z",
                        },
                    ]
                )
            )
        )

        snap = gh_client.build_snapshot("o/r", 9)
        assert isinstance(snap, PrSnapshot)
        assert snap.state == "open"
        assert snap.title == "Feature X"
        assert snap.head_sha == "abc1234"
        assert snap.author == "alice"
        assert len(snap.issue_comments) == 1 and snap.issue_comments[0].author == "bob"
        assert len(snap.review_summaries) == 1
        assert snap.review_summaries[0].state == "APPROVED"
        assert len(snap.review_comments) == 2
        live, stale = snap.review_comments
        assert live.line == 42 and not live.is_outdated
        assert stale.line == 12 and stale.is_outdated
