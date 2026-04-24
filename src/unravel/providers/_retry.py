"""Shared JSON-parse-with-retry loop for LLM providers."""

from __future__ import annotations

import json
from collections.abc import Callable

MAX_JSON_RETRIES = 2


def call_with_json_retry(
    send: Callable[[list[dict]], tuple[str, dict]],
    user_prompt: str,
    status: Callable[[str], None],
    *,
    max_retries: int = MAX_JSON_RETRIES,
) -> tuple[str, dict]:
    """Call ``send(messages)`` until its return value parses as JSON.

    ``send`` is a provider-specific transport that takes the accumulated
    conversation (a list of ``{"role": ..., "content": ...}`` dicts) and
    returns ``(text, usage)``. On JSON parse failure we append the bad
    response and a correction request, then call ``send`` again up to
    ``max_retries`` times. Usage counters are accumulated across attempts.
    """
    messages: list[dict] = [{"role": "user", "content": user_prompt}]
    cumulative: dict[str, int] = {}

    for attempt in range(1, max_retries + 1):
        text, usage = send(messages)
        _accumulate_usage(cumulative, usage)
        try:
            json.loads(text)
            return text, cumulative
        except json.JSONDecodeError as exc:
            if attempt >= max_retries:
                raise ValueError(
                    f"Failed to parse JSON response after "
                    f"{max_retries} attempts. Last error: {exc}"
                ) from exc
            status(f"JSON parse failed (attempt {attempt}), retrying...")
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your response was not valid JSON. "
                        f"Parse error: {exc}\n\n"
                        "Please respond with ONLY the valid JSON object."
                    ),
                }
            )

    raise RuntimeError("Unreachable")  # pragma: no cover


def _accumulate_usage(acc: dict, new: dict) -> None:
    for key, val in new.items():
        # Accept ints and floats (e.g. cost), reject bools (which subclass int).
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            acc[key] = acc.get(key, 0) + val
