"""Tests for the CLI helpers that handle the three-way in-progress prompt."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import typer

from unravel import cli, remote_cache
from unravel.models import Walkthrough
from unravel.remote_cache import RemoteComment

FAKE_SHA = "a" * 40


def _config() -> SimpleNamespace:
    return SimpleNamespace(provider="claude-api", resolved_model="claude-x")


def test_try_remote_cache_done_hit(
    monkeypatch, sample_walkthrough: Walkthrough
) -> None:
    monkeypatch.setattr(
        remote_cache,
        "fetch_from_pr_comment",
        lambda *a, **k: RemoteComment(
            comment_id=1,
            sha=FAKE_SHA,
            status="done",
            walkthrough=sample_walkthrough,
        ),
    )
    saved: dict = {}
    monkeypatch.setattr(
        cli.cache,
        "save",
        lambda *a, **k: saved.setdefault("called", True),
    )

    result = cli._try_remote_cache(
        pr_number=1,
        raw_diff="d",
        expected_sha=FAKE_SHA,
        remote="origin",
        repo_nwo="acme/repo",
        config=_config(),
        source_label="pr:#1",
    )
    assert result is sample_walkthrough
    assert saved.get("called") is True


def test_try_remote_cache_miss(monkeypatch) -> None:
    monkeypatch.setattr(remote_cache, "fetch_from_pr_comment", lambda *a, **k: None)

    result = cli._try_remote_cache(
        pr_number=1,
        raw_diff="d",
        expected_sha=FAKE_SHA,
        remote="origin",
        repo_nwo="acme/repo",
        config=_config(),
        source_label="pr:#1",
    )
    assert result is None


def test_try_remote_cache_in_progress_user_chooses_local(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_cache,
        "fetch_from_pr_comment",
        lambda *a, **k: RemoteComment(
            comment_id=2,
            sha=FAKE_SHA,
            status="in-progress",
            walkthrough=None,
        ),
    )
    monkeypatch.setattr(cli, "_prompt_inprogress_action", lambda short: "local")

    result = cli._try_remote_cache(
        pr_number=1,
        raw_diff="d",
        expected_sha=FAKE_SHA,
        remote="origin",
        repo_nwo="acme/repo",
        config=_config(),
        source_label="pr:#1",
    )
    assert result is None


def test_try_remote_cache_in_progress_user_chooses_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_cache,
        "fetch_from_pr_comment",
        lambda *a, **k: RemoteComment(
            comment_id=2,
            sha=FAKE_SHA,
            status="in-progress",
            walkthrough=None,
        ),
    )
    monkeypatch.setattr(cli, "_prompt_inprogress_action", lambda short: "exit")

    with pytest.raises(typer.Exit):
        cli._try_remote_cache(
            pr_number=1,
            raw_diff="d",
            expected_sha=FAKE_SHA,
            remote="origin",
            repo_nwo="acme/repo",
            config=_config(),
            source_label="pr:#1",
        )


def test_try_remote_cache_in_progress_wait_success(
    monkeypatch, sample_walkthrough: Walkthrough
) -> None:
    monkeypatch.setattr(
        remote_cache,
        "fetch_from_pr_comment",
        lambda *a, **k: RemoteComment(
            comment_id=3,
            sha=FAKE_SHA,
            status="in-progress",
            walkthrough=None,
        ),
    )
    monkeypatch.setattr(cli, "_prompt_inprogress_action", lambda short: "wait")
    monkeypatch.setattr(
        remote_cache, "poll_pr_comment", lambda *a, **k: sample_walkthrough
    )
    monkeypatch.setattr(cli.cache, "save", lambda *a, **k: None)

    result = cli._try_remote_cache(
        pr_number=1,
        raw_diff="d",
        expected_sha=FAKE_SHA,
        remote="origin",
        repo_nwo="acme/repo",
        config=_config(),
        source_label="pr:#1",
    )
    assert result is sample_walkthrough


def test_try_remote_cache_in_progress_wait_timeout_falls_through(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_cache,
        "fetch_from_pr_comment",
        lambda *a, **k: RemoteComment(
            comment_id=4,
            sha=FAKE_SHA,
            status="in-progress",
            walkthrough=None,
        ),
    )
    monkeypatch.setattr(cli, "_prompt_inprogress_action", lambda short: "wait")

    def boom(*a, **k):
        raise TimeoutError("nope")

    monkeypatch.setattr(remote_cache, "poll_pr_comment", boom)

    result = cli._try_remote_cache(
        pr_number=1,
        raw_diff="d",
        expected_sha=FAKE_SHA,
        remote="origin",
        repo_nwo="acme/repo",
        config=_config(),
        source_label="pr:#1",
    )
    assert result is None


def test_resolve_head_sha() -> None:
    assert cli._resolve_head_sha({"headRefOid": "abc"}) == "abc"
    assert cli._resolve_head_sha({}) is None
    assert cli._resolve_head_sha(None) is None


def test_prompt_inprogress_action_non_tty(monkeypatch) -> None:
    monkeypatch.setattr(cli, "console", cli.console)
    # Force stdin.isatty() to False
    monkeypatch.setattr(
        "sys.stdin",
        SimpleNamespace(isatty=lambda: False),
    )
    assert cli._prompt_inprogress_action("abcdef0") == "local"
