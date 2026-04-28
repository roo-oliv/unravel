"""Tests for remote cache (PR comment fetch/parse)."""

from __future__ import annotations

import base64
import json

import pytest

from unravel import remote_cache
from unravel.models import Walkthrough
from unravel.remote_cache import (
    RemoteComment,
    _decode_walkthrough,
    _parse_envelope,
    _parse_paginated_comments,
)
from unravel.renderer import (
    COMMENT_MARKER_DATA_PREFIX,
    COMMENT_MARKER_END,
    COMMENT_MARKER_SHA_PREFIX,
    COMMENT_MARKER_START,
    COMMENT_MARKER_STATUS_PREFIX,
    render_github_comment,
    render_github_comment_placeholder,
)

FAKE_SHA = "a" * 40
OTHER_SHA = "b" * 40


def _done_body(walkthrough: Walkthrough, sha: str = FAKE_SHA) -> str:
    return render_github_comment(walkthrough, head_sha=sha)


def _placeholder_body(sha: str = FAKE_SHA) -> str:
    return render_github_comment_placeholder(head_sha=sha, pr_number=1)


def test_parse_envelope_done_roundtrip(sample_walkthrough: Walkthrough) -> None:
    body = _done_body(sample_walkthrough)
    parsed = _parse_envelope(body)

    assert parsed is not None
    assert parsed["sha"] == FAKE_SHA
    assert parsed["status"] == "done"
    assert parsed["data"] is not None
    walkthrough = _decode_walkthrough(parsed["data"], raw_diff="fake diff")
    assert walkthrough is not None
    assert walkthrough.overview == sample_walkthrough.overview
    assert walkthrough.raw_diff == "fake diff"


def test_parse_envelope_in_progress() -> None:
    body = _placeholder_body()
    parsed = _parse_envelope(body)

    assert parsed is not None
    assert parsed["sha"] == FAKE_SHA
    assert parsed["status"] == "in-progress"
    assert parsed["data"] is None


def test_parse_envelope_no_marker() -> None:
    assert _parse_envelope("Just a normal comment.") is None


def test_parse_envelope_missing_sha() -> None:
    body = (
        f"{COMMENT_MARKER_START}\n"
        f"{COMMENT_MARKER_STATUS_PREFIX}done -->\n"
        f"{COMMENT_MARKER_END}\n"
    )
    assert _parse_envelope(body) is None


def test_parse_envelope_unknown_status() -> None:
    body = (
        f"{COMMENT_MARKER_START}\n"
        f"{COMMENT_MARKER_SHA_PREFIX}{FAKE_SHA} -->\n"
        f"{COMMENT_MARKER_STATUS_PREFIX}weird -->\n"
        f"{COMMENT_MARKER_END}\n"
    )
    assert _parse_envelope(body) is None


def test_decode_walkthrough_malformed_base64() -> None:
    assert _decode_walkthrough("not-valid-base64!!!", "") is None


def test_decode_walkthrough_invalid_json() -> None:
    encoded = base64.b64encode(b"not json").decode("ascii")
    assert _decode_walkthrough(encoded, "") is None


def test_decode_walkthrough_missing_fields() -> None:
    encoded = base64.b64encode(json.dumps({"foo": "bar"}).encode()).decode("ascii")
    assert _decode_walkthrough(encoded, "") is None


def test_parse_paginated_comments_concatenated_pages() -> None:
    raw = '[{"id": 1, "body": "a"}]\n[{"id": 2, "body": "b"}]\n'
    comments = _parse_paginated_comments(raw)
    assert [c["id"] for c in comments] == [1, 2]


def test_parse_paginated_comments_empty() -> None:
    assert _parse_paginated_comments("") == []


# --- fetch_from_pr_comment integration via subprocess monkeypatch ---


def _gh_comments_payload(comments: list[dict]) -> str:
    return json.dumps(comments)


def _stub_subprocess_run(monkeypatch, payload: str) -> None:
    class Result:
        stdout = payload
        stderr = ""
        returncode = 0

    def fake_run(*args, **kwargs):
        return Result()

    monkeypatch.setattr(remote_cache.subprocess, "run", fake_run)
    monkeypatch.setattr(remote_cache.shutil, "which", lambda _: "/usr/bin/gh")


def test_fetch_done_match(monkeypatch, sample_walkthrough: Walkthrough) -> None:
    body = _done_body(sample_walkthrough)
    payload = _gh_comments_payload([{"id": 99, "body": body}])
    _stub_subprocess_run(monkeypatch, payload)

    hit = remote_cache.fetch_from_pr_comment(
        1, raw_diff="diff", expected_sha=FAKE_SHA, repo="acme/repo"
    )
    assert isinstance(hit, RemoteComment)
    assert hit.status == "done"
    assert hit.comment_id == 99
    assert hit.walkthrough is not None
    assert hit.walkthrough.overview == sample_walkthrough.overview


def test_fetch_sha_mismatch_returns_none(
    monkeypatch, sample_walkthrough: Walkthrough
) -> None:
    body = _done_body(sample_walkthrough, sha=OTHER_SHA)
    payload = _gh_comments_payload([{"id": 99, "body": body}])
    _stub_subprocess_run(monkeypatch, payload)

    hit = remote_cache.fetch_from_pr_comment(
        1, raw_diff="diff", expected_sha=FAKE_SHA, repo="acme/repo"
    )
    assert hit is None


def test_fetch_in_progress_returns_remote_comment(monkeypatch) -> None:
    body = _placeholder_body()
    payload = _gh_comments_payload([{"id": 7, "body": body}])
    _stub_subprocess_run(monkeypatch, payload)

    hit = remote_cache.fetch_from_pr_comment(
        1, raw_diff="diff", expected_sha=FAKE_SHA, repo="acme/repo"
    )
    assert isinstance(hit, RemoteComment)
    assert hit.status == "in-progress"
    assert hit.walkthrough is None
    assert hit.comment_id == 7


def test_fetch_picks_newest_matching(
    monkeypatch, sample_walkthrough: Walkthrough
) -> None:
    older = _done_body(sample_walkthrough, sha=OTHER_SHA)  # mismatch, skipped
    newer = _placeholder_body()  # matching SHA, in-progress
    payload = _gh_comments_payload(
        [{"id": 1, "body": older}, {"id": 2, "body": newer}]
    )
    _stub_subprocess_run(monkeypatch, payload)

    hit = remote_cache.fetch_from_pr_comment(
        1, raw_diff="diff", expected_sha=FAKE_SHA, repo="acme/repo"
    )
    assert hit is not None
    assert hit.comment_id == 2


# --- poll_pr_comment ---


def test_poll_returns_when_status_flips(
    monkeypatch, sample_walkthrough: Walkthrough
) -> None:
    placeholder = json.dumps({"id": 7, "body": _placeholder_body()})
    done = json.dumps({"id": 7, "body": _done_body(sample_walkthrough)})
    responses = [placeholder, placeholder, done]

    class Result:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def fake_run(*args, **kwargs):
        return Result(responses.pop(0))

    monkeypatch.setattr(remote_cache.subprocess, "run", fake_run)
    monkeypatch.setattr(remote_cache.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(remote_cache.time, "sleep", lambda _s: None)

    walkthrough = remote_cache.poll_pr_comment(
        7,
        repo="acme/repo",
        raw_diff="diff",
        expected_sha=FAKE_SHA,
        interval=0.0,
        timeout=10.0,
    )
    assert walkthrough.overview == sample_walkthrough.overview


def test_poll_times_out(monkeypatch) -> None:
    placeholder = json.dumps({"id": 7, "body": _placeholder_body()})

    class Result:
        stdout = placeholder
        stderr = ""
        returncode = 0

    monkeypatch.setattr(remote_cache.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(remote_cache.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(remote_cache.time, "sleep", lambda _s: None)

    # Force time to advance past the deadline immediately.
    counter = {"t": 0.0}

    def fake_monotonic() -> float:
        counter["t"] += 100.0
        return counter["t"]

    monkeypatch.setattr(remote_cache.time, "monotonic", fake_monotonic)

    with pytest.raises(TimeoutError):
        remote_cache.poll_pr_comment(
            7,
            repo="acme/repo",
            raw_diff="diff",
            expected_sha=FAKE_SHA,
            interval=0.0,
            timeout=1.0,
        )


def test_poll_raises_on_sha_change(monkeypatch) -> None:
    other = json.dumps({"id": 7, "body": _placeholder_body(sha=OTHER_SHA)})

    class Result:
        stdout = other
        stderr = ""
        returncode = 0

    monkeypatch.setattr(remote_cache.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(remote_cache.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(remote_cache.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError):
        remote_cache.poll_pr_comment(
            7,
            repo="acme/repo",
            raw_diff="diff",
            expected_sha=FAKE_SHA,
            interval=0.0,
            timeout=10.0,
        )
