"""Shared prompt templates for all LLM providers."""

from __future__ import annotations

import json

from unravel.models import WALKTHROUGH_JSON_SCHEMA, Hunk

SYSTEM_PROMPT = """\
You are an expert code reviewer who decomposes diffs into **causal threads** — \
logical chains of changes that share a single root cause or purpose.

Your job is to help a human reviewer understand a pull request by breaking it \
into threads they can review one at a time, in an order that builds understanding \
progressively.

## What is a causal thread?

A thread groups hunks (diff fragments) that belong together because they serve \
the same purpose or stem from the same root cause. Threads are NOT file-based — \
a single thread often spans multiple files, and a single file may contribute hunks \
to multiple threads.

## Hunk references

The user message includes a **File summary** that assigns every hunk a stable ID \
(H1, H2, H3, ...). When listing the hunks in a step, reference them by these IDs \
exactly as given — do NOT invent line numbers or new IDs. Each step's `hunks` \
field is an array of these string IDs.

## Guiding principles

1. **Coverage is mandatory**: Every hunk ID listed in the File Summary MUST appear \
   in at least one step across all threads. Do not drop any hunk. If a hunk doesn't \
   fit a narrative, place it in the most relevant thread or create a small \
   "miscellaneous" thread for it.
2. **Root-cause grouping**: Group by *why* the change was made, not *where* it lives.
3. **Cause-to-effect ordering**: Within a thread, order steps so the reader sees \
   the cause before its effects. Typically: data model → logic → API → UI → tests.
4. **Fewer, larger threads**: Prefer cohesive threads over many trivial ones. \
   A thread with 1-2 hunks is a smell — consider merging with a related thread.
5. **Hunk reuse is allowed**: If a hunk is relevant to understanding two threads, \
   include its ID in both. The reviewer benefits from seeing it in context.
6. **Narrate the "why"**: Your narration should explain *why* each change was made, \
   not just *what* changed. The diff already shows the what.
7. **Suggested order**: Put foundational/structural threads first, then those that \
   build on them. If thread B depends on thread A, A comes first.
8. **Thread IDs**: Use short kebab-case slugs (e.g., "add-retry-logic", "fix-null-check").
9. **Dependencies**: If reviewing thread B requires understanding thread A first, \
   list A in B's dependencies.

## Tone

Write as a knowledgeable colleague explaining the PR to another developer. \
Be concise but thorough. Avoid filler phrases.

## Output format

Respond with ONLY valid JSON matching the schema below. No markdown fences, \
no commentary outside the JSON object.
"""


def build_analysis_prompt(
    raw_diff: str,
    hunks: list[Hunk],
    metadata: dict,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for diff analysis."""
    schema_text = json.dumps(WALKTHROUGH_JSON_SCHEMA, indent=2)
    system = f"{SYSTEM_PROMPT}\n## JSON Schema\n\n```json\n{schema_text}\n```"

    file_summary = _build_file_summary(hunks)
    meta_section = _build_metadata_section(metadata)

    user = f"""\
{meta_section}## File summary

{file_summary}

## Full diff

```diff
{raw_diff}
```

Decompose this diff into causal threads. Return ONLY the JSON object."""

    return system, user


def _build_file_summary(hunks: list[Hunk]) -> str:
    """Build a file summary that lists every hunk with its stable ID.

    Each hunk shows `Hx: lines A-B (N lines)` so the LLM can reference hunks
    by ID instead of reproducing line numbers (which it tends to drift on).
    """
    by_file: dict[str, list[Hunk]] = {}
    for h in hunks:
        by_file.setdefault(h.file_path, []).append(h)

    blocks: list[str] = []
    for path, file_hunks in by_file.items():
        lines = [f"- `{path}`"]
        for h in file_hunks:
            if h.content == "[binary file]":
                lines.append(f"  - **{h.id}**: binary file")
            else:
                end = h.new_start + max(h.new_count - 1, 0)
                lines.append(
                    f"  - **{h.id}**: lines {h.new_start}-{end} "
                    f"({h.new_count} line{'s' if h.new_count != 1 else ''})"
                )
        blocks.append("\n".join(lines))

    fs = "s" if len(by_file) != 1 else ""
    hs = "s" if len(hunks) != 1 else ""
    total = f"{len(by_file)} file{fs}, {len(hunks)} hunk{hs}"
    return f"{total}\n\n" + "\n\n".join(blocks)


def _build_metadata_section(metadata: dict) -> str:
    if not metadata:
        return ""
    parts = []
    if title := metadata.get("title"):
        parts.append(f"**PR title**: {title}")
    if author := metadata.get("author"):
        name = author.get("login", str(author)) if isinstance(author, dict) else str(author)
        parts.append(f"**Author**: {name}")
    if body := metadata.get("body"):
        parts.append(f"**Description**:\n{body}")
    if not parts:
        return ""
    return "## PR context\n\n" + "\n".join(parts) + "\n\n"
