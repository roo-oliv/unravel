"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

import time
from collections.abc import Callable

import anthropic
from anthropic import APIConnectionError, APIStatusError, APITimeoutError

from unravel.config import UnravelConfig
from unravel.models import Hunk, Walkthrough
from unravel.prompts import build_analysis_prompt
from unravel.providers._retry import call_with_json_retry
from unravel.providers.base import BaseProvider

CLIENT_TIMEOUT_SECONDS = 600.0
CLIENT_MAX_RETRIES = 3
STATUS_THROTTLE_SECONDS = 0.25


class AnthropicProvider(BaseProvider):
    def __init__(self, config: UnravelConfig) -> None:
        super().__init__(config)
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.config.resolved_api_key,
                timeout=CLIENT_TIMEOUT_SECONDS,
                max_retries=CLIENT_MAX_RETRIES,
            )
        return self._client

    def validate_config(self) -> None:
        _ = self.config.resolved_api_key
        if not self.config.resolved_model:
            raise ValueError("No model configured for Anthropic provider.")

    def analyze(
        self,
        hunks: list[Hunk],
        raw_diff: str,
        metadata: dict,
        *,
        on_status: Callable[[str], None] | None = None,
    ) -> Walkthrough:
        system_prompt, user_prompt = build_analysis_prompt(raw_diff, hunks, metadata)

        def status(msg: str) -> None:
            if on_status:
                on_status(msg)

        status("Sending diff to Claude...")
        start = time.monotonic()

        def send(messages: list[dict]) -> tuple[str, dict]:
            return self._send_request(system_prompt, messages, status)

        response_text, usage = call_with_json_retry(send, user_prompt, status)

        elapsed = time.monotonic() - start
        status(f"Analysis complete in {elapsed:.1f}s")

        walkthrough = Walkthrough.from_json(response_text, raw_diff=raw_diff)
        walkthrough.metadata["model"] = self.config.resolved_model
        walkthrough.metadata["provider"] = "anthropic"
        walkthrough.metadata["elapsed_seconds"] = round(elapsed, 2)
        walkthrough.metadata["input_tokens"] = usage.get("input_tokens", 0)
        walkthrough.metadata["output_tokens"] = usage.get("output_tokens", 0)
        walkthrough.metadata["thinking_tokens"] = usage.get("thinking_tokens", 0)
        walkthrough.metadata["cache_read_tokens"] = usage.get(
            "cache_read_tokens", 0
        )
        walkthrough.metadata["cache_creation_tokens"] = usage.get(
            "cache_creation_tokens", 0
        )

        return walkthrough

    def _send_request(
        self,
        system_prompt: str,
        messages: list[dict],
        status: Callable[[str], None],
    ) -> tuple[str, dict]:
        kwargs: dict = {
            "model": self.config.resolved_model,
            "max_tokens": self.config.max_output_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
        }

        if self.config.thinking_budget > 0:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget,
            }

        start = time.monotonic()
        last_update = 0.0
        stage = "Connecting"
        thinking_chars = 0
        output_chars = 0
        text_parts: list[str] = []

        try:
            with self.client.messages.stream(**kwargs) as stream:
                for event in stream:
                    etype = getattr(event, "type", None)

                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        block_type = getattr(block, "type", None)
                        if block_type == "thinking":
                            stage = "Thinking"
                        elif block_type == "text":
                            stage = "Writing response"
                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        dtype = getattr(delta, "type", None)
                        if dtype == "thinking_delta":
                            thinking_chars += len(getattr(delta, "thinking", ""))
                        elif dtype == "text_delta":
                            text = getattr(delta, "text", "")
                            text_parts.append(text)
                            output_chars += len(text)

                    now = time.monotonic()
                    if now - last_update >= STATUS_THROTTLE_SECONDS:
                        elapsed = now - start
                        status(_format_progress(stage, elapsed, thinking_chars, output_chars))
                        last_update = now

                final_message = stream.get_final_message()
        except APITimeoutError as exc:
            raise ConnectionError(
                f"Claude API request timed out after {CLIENT_TIMEOUT_SECONDS:.0f}s. "
                "Check your network connection and try again."
            ) from exc
        except APIConnectionError as exc:
            raise ConnectionError(
                f"Lost connection to Claude API: {exc}. "
                "Check your network connection and try again."
            ) from exc
        except APIStatusError as exc:
            raise ValueError(
                f"Claude API returned {exc.status_code}: {exc.message}"
            ) from exc

        usage = _extract_usage(final_message, thinking_chars)

        for block in final_message.content:
            if block.type == "text":
                return block.text, usage

        if text_parts:
            return "".join(text_parts), usage

        raise ValueError("No text block found in Claude response.")


def _format_progress(
    stage: str, elapsed: float, thinking_chars: int, output_chars: int
) -> str:
    parts = [f"{stage}"]
    if thinking_chars:
        parts.append(f"~{thinking_chars // 4} thinking tokens")
    if output_chars:
        parts.append(f"~{output_chars // 4} output tokens")
    parts.append(f"{elapsed:.0f}s")
    return " · ".join(parts)


def _extract_usage(final_message, thinking_chars: int) -> dict:
    """Extract token usage from the final message.

    Anthropic returns exact counts in ``final_message.usage``. When the API
    doesn't expose a dedicated thinking-token count, fall back to an estimate
    based on streamed thinking characters (~4 chars/token).
    """
    usage = getattr(final_message, "usage", None)
    result: dict[str, int] = {}
    if usage is not None:
        for attr in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            val = getattr(usage, attr, None)
            if isinstance(val, int):
                # Normalize the two cache fields to shorter names.
                if attr == "cache_read_input_tokens":
                    result["cache_read_tokens"] = val
                elif attr == "cache_creation_input_tokens":
                    result["cache_creation_tokens"] = val
                else:
                    result[attr] = val
    if thinking_chars:
        result["thinking_tokens"] = thinking_chars // 4
    return result
