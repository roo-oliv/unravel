"""Tests for prompt construction and response parsing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from unravel.config import UnravelConfig
from unravel.git import parse_diff
from unravel.models import Walkthrough
from unravel.narrator import validate_walkthrough
from unravel.prompts import build_analysis_prompt
from unravel.providers.claude_api import ClaudeAPIProvider


class TestBuildAnalysisPrompt:
    def test_returns_system_and_user(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        system, user = build_analysis_prompt(simple_diff, hunks, {})
        assert "causal threads" in system
        assert "JSON Schema" in system
        assert "```diff" in user
        assert "src/auth.py" in user

    def test_includes_file_summary(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        _, user = build_analysis_prompt(simple_diff, hunks, {})
        assert "2 files" in user
        assert "3 hunks" in user

    def test_includes_pr_metadata(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        metadata = {
            "title": "Fix auth errors",
            "author": {"login": "dev123"},
            "body": "This PR improves error handling.",
        }
        _, user = build_analysis_prompt(simple_diff, hunks, metadata)
        assert "Fix auth errors" in user
        assert "dev123" in user
        assert "improves error handling" in user

    def test_empty_metadata(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        _, user = build_analysis_prompt(simple_diff, hunks, {})
        assert "PR context" not in user

    def test_schema_is_valid_json(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        system, _ = build_analysis_prompt(simple_diff, hunks, {})
        json_start = system.index("```json\n") + len("```json\n")
        json_end = system.index("\n```", json_start)
        schema = json.loads(system[json_start:json_end])
        assert schema["type"] == "object"
        assert "threads" in schema["properties"]


class TestClaudeAPIProviderParsing:
    def test_parse_response(self, sample_response_text: str, simple_diff: str):
        """Test that the provider can parse a valid JSON response into a Walkthrough."""
        config = UnravelConfig(provider="claude-api", api_key="test-key")
        provider = ClaudeAPIProvider(config)

        hunks = parse_diff(simple_diff)

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = sample_response_text

        mock_final = MagicMock()
        mock_final.content = [mock_text_block]

        mock_stream = MagicMock()
        mock_stream.__iter__ = MagicMock(return_value=iter([]))
        mock_stream.get_final_message.return_value = mock_final

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream_ctx
        provider._client = mock_client
        walkthrough = provider.analyze(hunks, simple_diff, {})

        assert isinstance(walkthrough, Walkthrough)
        assert len(walkthrough.threads) == 2
        assert walkthrough.metadata["provider"] == "claude-api"


class TestValidateWalkthrough:
    def test_valid_walkthrough(self, sample_walkthrough: Walkthrough, simple_diff: str):
        hunks = parse_diff(simple_diff)
        warnings = validate_walkthrough(sample_walkthrough, hunks)
        # The sample response doesn't cover all hunks perfectly, but let's check structure
        assert isinstance(warnings, list)
        assert all(isinstance(w, str) for w in warnings)

    def test_broken_dependency(self):
        wt = Walkthrough(
            threads=[],
            overview="test",
            suggested_order=[],
        )
        from unravel.models import Thread

        wt.threads = [
            Thread(
                id="a",
                title="A",
                summary="s",
                root_cause="r",
                steps=[],
                dependencies=["nonexistent"],
            )
        ]
        warnings = validate_walkthrough(wt, [])
        assert any("nonexistent" in w for w in warnings)

    def test_missing_from_suggested_order(self):
        from unravel.models import Thread

        wt = Walkthrough(
            threads=[
                Thread(id="a", title="A", summary="s", root_cause="r", steps=[]),
                Thread(id="b", title="B", summary="s", root_cause="r", steps=[]),
            ],
            overview="test",
            suggested_order=["a"],
        )
        warnings = validate_walkthrough(wt, [])
        assert any("'b' missing from suggested_order" in w for w in warnings)
