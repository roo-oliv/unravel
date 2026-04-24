"""Provider factory."""

from __future__ import annotations

import os
import shutil

from unravel.config import PROVIDER_ENV_KEYS, UnravelConfig
from unravel.providers.base import BaseProvider


def get_provider(config: UnravelConfig) -> BaseProvider:
    """Return a provider for ``config.provider``, resolving ``"auto"`` in-place.

    When ``config.provider`` is ``"auto"`` we pick a concrete backend and
    mutate ``config.provider`` so downstream code (cache keys, status lines,
    metadata) sees the resolved name instead of ``"auto"``.
    """
    if config.provider == "auto":
        config.provider = _auto_detect(config)

    match config.provider:
        case "anthropic":
            from unravel.providers.anthropic import AnthropicProvider

            return AnthropicProvider(config)
        case "claude-cli":
            from unravel.providers.claude_cli import ClaudeCLIProvider

            return ClaudeCLIProvider(config)
        case _:
            supported = ["auto", "anthropic", "claude-cli"]
            raise ValueError(
                f"Unsupported provider: '{config.provider}'. "
                f"Supported providers: {', '.join(supported)}"
            )


def _auto_detect(config: UnravelConfig) -> str:
    """Pick a concrete backend when the user hasn't specified one.

    Order:
      1. Local Claude CLI if the configured binary resolves on PATH.
      2. Anthropic API if ``ANTHROPIC_API_KEY`` is set.
      3. Claude CLI — so a subsequent ``validate_config`` surfaces a clear
         install/configure error rather than a confusing API-key error.
    """
    if shutil.which(config.claude_cli.path):
        return "claude-cli"
    if os.environ.get(PROVIDER_ENV_KEYS["anthropic"]):
        return "anthropic"
    return "claude-cli"
