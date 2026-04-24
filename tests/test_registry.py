"""Tests for provider auto-detection + dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from unravel.config import UnravelConfig
from unravel.providers import get_provider
from unravel.providers.claude_api import ClaudeAPIProvider
from unravel.providers.claude_cli import ClaudeCLIProvider


class TestAutoResolution:
    def test_auto_picks_cli_when_binary_present(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = UnravelConfig(provider="auto")
        with patch("unravel.providers.registry.shutil.which", return_value="/bin/claude"):
            provider = get_provider(cfg)
        assert isinstance(provider, ClaudeCLIProvider)
        assert cfg.provider == "claude-cli"

    def test_auto_falls_back_to_api_when_cli_missing_and_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = UnravelConfig(provider="auto")
        with patch("unravel.providers.registry.shutil.which", return_value=None):
            provider = get_provider(cfg)
        assert isinstance(provider, ClaudeAPIProvider)
        assert cfg.provider == "claude-api"

    def test_auto_defaults_to_cli_when_nothing_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = UnravelConfig(provider="auto")
        with patch("unravel.providers.registry.shutil.which", return_value=None):
            provider = get_provider(cfg)
        # No CLI, no API key → we pick claude-cli so validate_config surfaces
        # an install hint rather than an API-key error.
        assert isinstance(provider, ClaudeCLIProvider)
        assert cfg.provider == "claude-cli"


class TestExplicitProviders:
    def test_explicit_claude_api(self):
        cfg = UnravelConfig(provider="claude-api", api_key="sk")
        assert isinstance(get_provider(cfg), ClaudeAPIProvider)

    def test_legacy_anthropic_alias_still_works(self):
        cfg = UnravelConfig(provider="anthropic", api_key="sk")
        assert isinstance(get_provider(cfg), ClaudeAPIProvider)
        assert cfg.provider == "claude-api"

    def test_explicit_claude_cli(self):
        cfg = UnravelConfig(provider="claude-cli")
        assert isinstance(get_provider(cfg), ClaudeCLIProvider)

    def test_unknown_provider_raises(self):
        cfg = UnravelConfig(provider="foo")
        with pytest.raises(ValueError, match="Unsupported provider"):
            get_provider(cfg)
