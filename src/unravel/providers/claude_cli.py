"""Local Claude CLI provider — invokes the `claude` binary in print mode."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from collections.abc import Callable

from unravel.models import Hunk, Walkthrough
from unravel.prompts import build_analysis_prompt
from unravel.providers._retry import call_with_json_retry
from unravel.providers.base import BaseProvider

STATUS_THROTTLE_SECONDS = 0.25


class ClaudeCLIProvider(BaseProvider):
    def validate_config(self) -> None:
        path = shutil.which(self.config.claude_cli.path)
        if not path:
            raise ValueError(
                f"Claude CLI not found at {self.config.claude_cli.path!r}. "
                "Install Claude Code from https://claude.com/product/claude-code "
                "or pin the Anthropic API via `unravel conf set provider anthropic` "
                "(and set ANTHROPIC_API_KEY)."
            )
        if not self.config.resolved_model and not self.config.claude_cli.respect_user_model:
            raise ValueError("No model configured for Claude CLI provider.")

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

        status("Launching Claude CLI...")
        start = time.monotonic()

        def send(messages: list[dict]) -> tuple[str, dict]:
            prompt = _messages_to_prompt(messages)
            return self._invoke_cli(system_prompt, prompt, status)

        response_text, usage = call_with_json_retry(send, user_prompt, status)

        elapsed = time.monotonic() - start
        status(f"Analysis complete in {elapsed:.1f}s")

        walkthrough = Walkthrough.from_json(response_text, raw_diff=raw_diff)
        walkthrough.metadata["model"] = self.config.resolved_model
        walkthrough.metadata["provider"] = "claude-cli"
        walkthrough.metadata["elapsed_seconds"] = round(elapsed, 2)
        walkthrough.metadata["input_tokens"] = usage.get("input_tokens", 0)
        walkthrough.metadata["output_tokens"] = usage.get("output_tokens", 0)
        walkthrough.metadata["thinking_tokens"] = usage.get("thinking_tokens", 0)
        walkthrough.metadata["cache_read_tokens"] = usage.get("cache_read_tokens", 0)
        walkthrough.metadata["cache_creation_tokens"] = usage.get(
            "cache_creation_tokens", 0
        )
        if (cost := usage.get("total_cost_usd")) is not None:
            walkthrough.metadata["total_cost_usd"] = cost

        return walkthrough

    def _invoke_cli(
        self,
        system_prompt: str,
        user_prompt: str,
        status: Callable[[str], None],
    ) -> tuple[str, dict]:
        argv = self._build_argv(system_prompt)
        timeout = float(self.config.claude_cli.timeout_seconds)

        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"Claude CLI not found at {argv[0]!r}. Install Claude Code or "
                "set `[claude_cli] path` to the correct binary."
            ) from exc

        writer_error: list[BaseException] = []
        writer = threading.Thread(
            target=_write_stdin, args=(proc, user_prompt, writer_error), daemon=True
        )
        writer.start()

        result_text = ""
        usage: dict = {}
        stderr_tail: list[str] = []
        stage = "Connecting"
        last_update = 0.0
        stream_start = time.monotonic()
        assistant_chars = 0

        assert proc.stdout is not None  # for type checkers
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")
                if etype == "system" and event.get("subtype") == "init":
                    stage = "Waiting for Claude"
                elif etype == "assistant":
                    stage = "Writing response"
                    assistant_chars += _assistant_text_len(event)
                elif etype == "result":
                    result_text = str(event.get("result", ""))
                    usage = _extract_usage(event)

                now = time.monotonic()
                if now - last_update >= STATUS_THROTTLE_SECONDS:
                    elapsed = now - stream_start
                    status(_format_progress(stage, elapsed, assistant_chars))
                    last_update = now
        except Exception:
            proc.kill()
            raise

        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            raise ConnectionError(
                f"Claude CLI timed out after {timeout:.0f}s. "
                "Check your network connection and try again."
            ) from exc

        writer.join(timeout=5)
        if writer_error:
            raise writer_error[0]

        assert proc.stderr is not None
        stderr_output = proc.stderr.read() or ""
        if stderr_output:
            # Keep only the last chunk so we don't pollute the UI with debug noise.
            stderr_tail = stderr_output.strip().splitlines()[-5:]

        if rc != 0:
            tail = "\n".join(stderr_tail) if stderr_tail else "(no stderr captured)"
            raise ValueError(
                f"Claude CLI exited with code {rc}. Last stderr:\n{tail}"
            )

        if not result_text:
            tail = "\n".join(stderr_tail) if stderr_tail else "(no stderr captured)"
            raise ValueError(
                "Claude CLI produced no result. The process exited cleanly but "
                f"emitted no `result` event. Last stderr:\n{tail}"
            )

        return result_text, usage

    def _build_argv(self, system_prompt: str) -> list[str]:
        cfg = self.config.claude_cli
        argv: list[str] = [
            cfg.path,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--tools",
            "",
            "--system-prompt",
            system_prompt,
        ]
        if not cfg.respect_user_model and self.config.resolved_model:
            argv += ["--model", self.config.resolved_model]
        return argv


def _write_stdin(
    proc: subprocess.Popen, payload: str, errors: list[BaseException]
) -> None:
    try:
        assert proc.stdin is not None
        proc.stdin.write(payload)
        proc.stdin.close()
    except BaseException as exc:  # noqa: BLE001 — surfaced in main thread
        errors.append(exc)


def _messages_to_prompt(messages: list[dict]) -> str:
    """Flatten a retry-style message list into a single prompt for the CLI.

    The CLI's ``-p`` mode is stateless per invocation, so multi-turn retries
    are emulated by concatenating history inline.
    """
    if len(messages) == 1:
        return str(messages[0].get("content", ""))
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role", "user")).upper()
        parts.append(f"--- [{role}] ---\n\n{m.get('content', '')}")
    return "\n\n".join(parts)


def _assistant_text_len(event: dict) -> int:
    message = event.get("message") or {}
    content = message.get("content") or []
    total = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            total += len(str(block.get("text", "")))
    return total


def _extract_usage(result_event: dict) -> dict:
    usage_in = result_event.get("usage") or {}
    out: dict = {}
    mapping = {
        "input_tokens": "input_tokens",
        "output_tokens": "output_tokens",
        "cache_read_input_tokens": "cache_read_tokens",
        "cache_creation_input_tokens": "cache_creation_tokens",
    }
    for src, dst in mapping.items():
        val = usage_in.get(src)
        if isinstance(val, int):
            out[dst] = val
    cost = result_event.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        out["total_cost_usd"] = float(cost)
    return out


def _format_progress(stage: str, elapsed: float, assistant_chars: int) -> str:
    parts = [stage]
    if assistant_chars:
        parts.append(f"~{assistant_chars // 4} output tokens")
    parts.append(f"{elapsed:.0f}s")
    return " · ".join(parts)
