"""Tests for the local Claude CLI provider."""

from __future__ import annotations

import json
import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from unravel.config import UnravelConfig
from unravel.git import parse_diff
from unravel.models import Walkthrough
from unravel.providers.claude_cli import (
    ClaudeCLIProvider,
    _extract_usage,
    _messages_to_prompt,
)


def _stream_lines(events: list[dict]) -> list[str]:
    return [json.dumps(e) + "\n" for e in events]


def _mock_proc(
    stdout_lines: list[str],
    *,
    stderr: str = "",
    returncode: int = 0,
) -> MagicMock:
    proc = MagicMock()
    proc.stdout = iter(stdout_lines)
    proc.stderr = StringIO(stderr)
    proc.stdin = MagicMock()
    proc.wait.return_value = returncode
    proc.kill = MagicMock()
    return proc


def _result_event(result_text: str, **overrides) -> dict:
    event = {
        "type": "result",
        "subtype": "success",
        "result": result_text,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 25,
        },
        "total_cost_usd": 0.00123,
        "duration_ms": 1234,
        "session_id": "abc",
    }
    event.update(overrides)
    return event


class TestValidateConfig:
    def test_raises_when_binary_missing(self):
        cfg = UnravelConfig(provider="claude-cli")
        cfg.claude_cli.path = "/nonexistent/bin/claude-xyz-abc"
        provider = ClaudeCLIProvider(cfg)
        with pytest.raises(ValueError, match="not found"):
            provider.validate_config()

    def test_ok_when_binary_present(self):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        with patch("unravel.providers.claude_cli.shutil.which", return_value="/bin/claude"):
            provider.validate_config()  # should not raise


class TestAnalyze:
    def test_happy_path(self, sample_response_text: str, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        events = [
            {"type": "system", "subtype": "init", "session_id": "s1"},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "working..."}]},
            },
            _result_event(sample_response_text),
        ]
        proc = _mock_proc(_stream_lines(events))

        with patch("unravel.providers.claude_cli.subprocess.Popen", return_value=proc):
            walkthrough = provider.analyze(hunks, simple_diff, {})

        assert isinstance(walkthrough, Walkthrough)
        assert walkthrough.metadata["provider"] == "claude-cli"
        assert walkthrough.metadata["input_tokens"] == 100
        assert walkthrough.metadata["output_tokens"] == 200
        assert walkthrough.metadata["cache_read_tokens"] == 50
        assert walkthrough.metadata["cache_creation_tokens"] == 25
        assert walkthrough.metadata["total_cost_usd"] == pytest.approx(0.00123)

    def test_non_zero_exit_raises(self, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        proc = _mock_proc([], stderr="boom: something broke", returncode=2)
        with patch("unravel.providers.claude_cli.subprocess.Popen", return_value=proc):
            with pytest.raises(ValueError, match="exited with code 2"):
                provider.analyze(hunks, simple_diff, {})

    def test_timeout_raises_connection_error(self, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        cfg.claude_cli.timeout_seconds = 1
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        proc = _mock_proc([_stream_lines([_result_event("{}")])[0]])
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1)

        with patch("unravel.providers.claude_cli.subprocess.Popen", return_value=proc):
            with pytest.raises(ConnectionError, match="timed out"):
                provider.analyze(hunks, simple_diff, {})

    def test_missing_binary_raises_value_error(self, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        with patch(
            "unravel.providers.claude_cli.subprocess.Popen",
            side_effect=FileNotFoundError("no claude"),
        ):
            with pytest.raises(ValueError, match="not found"):
                provider.analyze(hunks, simple_diff, {})

    def test_no_result_event_raises(self, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        events = [{"type": "system", "subtype": "init", "session_id": "s1"}]
        proc = _mock_proc(_stream_lines(events))

        with patch("unravel.providers.claude_cli.subprocess.Popen", return_value=proc):
            with pytest.raises(ValueError, match="no result"):
                provider.analyze(hunks, simple_diff, {})

    def test_retries_on_bad_json(self, sample_response_text: str, simple_diff: str):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        hunks = parse_diff(simple_diff)

        bad_proc = _mock_proc(_stream_lines([_result_event("not json")]))
        good_proc = _mock_proc(_stream_lines([_result_event(sample_response_text)]))

        with patch(
            "unravel.providers.claude_cli.subprocess.Popen",
            side_effect=[bad_proc, good_proc],
        ):
            walkthrough = provider.analyze(hunks, simple_diff, {})

        assert isinstance(walkthrough, Walkthrough)
        # Usage is summed across both calls.
        assert walkthrough.metadata["input_tokens"] == 200


class TestArgvConstruction:
    def test_passes_model_by_default(self):
        cfg = UnravelConfig(provider="claude-cli", model="claude-sonnet-4-6")
        provider = ClaudeCLIProvider(cfg)
        argv = provider._build_argv("SYSTEM")
        assert "--model" in argv
        assert "claude-sonnet-4-6" in argv
        assert "--system-prompt" in argv

    def test_omits_model_when_respect_user_model(self):
        cfg = UnravelConfig(provider="claude-cli")
        cfg.claude_cli.respect_user_model = True
        provider = ClaudeCLIProvider(cfg)
        argv = provider._build_argv("SYSTEM")
        assert "--model" not in argv

    def test_disables_tools(self):
        cfg = UnravelConfig(provider="claude-cli")
        provider = ClaudeCLIProvider(cfg)
        argv = provider._build_argv("SYSTEM")
        i = argv.index("--tools")
        assert argv[i + 1] == ""


class TestHelpers:
    def test_extract_usage_maps_cache_fields(self):
        event = _result_event("x")
        usage = _extract_usage(event)
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 200
        assert usage["cache_read_tokens"] == 50
        assert usage["cache_creation_tokens"] == 25
        assert usage["total_cost_usd"] == pytest.approx(0.00123)

    def test_extract_usage_handles_missing_fields(self):
        assert _extract_usage({}) == {}

    def test_messages_to_prompt_single(self):
        out = _messages_to_prompt([{"role": "user", "content": "hi"}])
        assert out == "hi"

    def test_messages_to_prompt_multi(self):
        out = _messages_to_prompt(
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "bad"},
                {"role": "user", "content": "retry"},
            ]
        )
        assert "first" in out
        assert "bad" in out
        assert "retry" in out
        assert "[ASSISTANT]" in out
