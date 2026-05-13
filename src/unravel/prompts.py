"""Shared prompt templates for all LLM providers."""

from __future__ import annotations

import json

from unravel.models import WALKTHROUGH_JSON_SCHEMA, Hunk, Walkthrough

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

## Hunk captions

Provide a top-level `hunk_captions` object mapping every hunk ID to a short \
one-liner (2-5 words) describing **what** the hunk contains at a glance — \
not why. Examples: "New imports", "Imports update", "Removed imports", \
"New createFooBar function", "getFooBar signature update", \
"bar sorting order update", "New constants", "Constants update", \
"New X enum item", "Removed dead code". Coverage is mandatory: every hunk ID \
in the File Summary must appear as a key in `hunk_captions`. The caption \
describes the hunk content itself, so it does not change based on which \
step references the hunk.

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
10. **Incremental re-analysis**: If a Previous Walkthrough is provided, the user \
    already reviewed an earlier version of this PR. Preserve thread IDs, titles, \
    and narration for threads whose hunks are unchanged — this keeps the reader's \
    "viewed" marks meaningful. Reorganise threads only where the new diff genuinely \
    demands it; you may merge, split, create, or delete threads as needed. Every \
    hunk in the current File summary must still be covered.

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
    previous_walkthrough: Walkthrough | None = None,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for diff analysis.

    ``previous_walkthrough`` (when present) is the most recent walkthrough for
    the same source whose underlying diff differs from the current one. It is
    injected into the user prompt with a hunk-identity carryover summary so the
    model can preserve thread structure for unchanged hunks.
    """
    schema_text = json.dumps(WALKTHROUGH_JSON_SCHEMA, indent=2)
    system = f"{SYSTEM_PROMPT}\n## JSON Schema\n\n```json\n{schema_text}\n```"

    file_summary = _build_file_summary(hunks)
    meta_section = _build_metadata_section(metadata)
    prior_section = _build_previous_walkthrough_section(previous_walkthrough, hunks)

    user = f"""\
{meta_section}## File summary

{file_summary}

{prior_section}## Full diff

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


def _build_previous_walkthrough_section(
    previous: Walkthrough | None, current_hunks: list[Hunk]
) -> str:
    """Render the prior walkthrough plus a hunk-identity carryover summary.

    Returns the empty string when no prior walkthrough is provided (so the
    rest of the prompt template is unaffected).
    """
    if previous is None:
        return ""

    prior_hashes: dict[str, str] = {}
    for thread in previous.threads:
        for step in thread.steps:
            for hunk in step.hunks:
                if hunk.content_hash and hunk.id and hunk.id not in prior_hashes:
                    prior_hashes[hunk.id] = hunk.content_hash
    prior_hash_set = set(prior_hashes.values())
    prior_by_hash = {h: hid for hid, h in prior_hashes.items()}

    current_hashes = {h.content_hash: h.id for h in current_hunks if h.content_hash}

    unchanged: list[str] = []
    new_hunks: list[str] = []
    for hunk in current_hunks:
        if hunk.content_hash and hunk.content_hash in prior_hash_set:
            prior_id = prior_by_hash[hunk.content_hash]
            label = (
                f"{hunk.id} (was {prior_id})" if prior_id != hunk.id else hunk.id
            )
            unchanged.append(label)
        else:
            new_hunks.append(hunk.id)

    removed = [
        prior_id
        for prior_id, prior_hash in prior_hashes.items()
        if prior_hash not in current_hashes
    ]

    prior_json = previous.to_json(indent=2)
    lines = [
        "## Previous walkthrough (re-running on a changed source)",
        "",
        "The user already reviewed an earlier version of this PR. Below is the",
        "prior walkthrough plus a hunk-identity carryover map. Preserve thread",
        "IDs, titles, and narration for unchanged hunks. Reorganise where the",
        "new diff genuinely requires it. You may merge, split, create, or delete",
        "threads.",
        "",
        "### Hunk identity carryover",
        f"- Unchanged hunks (preserve thread membership): "
        f"{', '.join(unchanged) if unchanged else '(none)'}",
        f"- New hunks (assign to threads): "
        f"{', '.join(new_hunks) if new_hunks else '(none)'}",
        f"- Removed (no longer present in current diff): "
        f"{', '.join(removed) if removed else '(none)'}",
        "",
        "### Previous walkthrough (JSON)",
        "",
        "```json",
        prior_json,
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


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
