"""Hydrate walkthrough hunks with diff content from parsed hunks."""

from __future__ import annotations

from unravel.models import Hunk, Walkthrough


def hydrate_walkthrough(
    walkthrough: Walkthrough, parsed_hunks: list[Hunk]
) -> tuple[Walkthrough, list[str]]:
    """Replace LLM hunk references with fully-populated parsed hunks.

    The LLM references hunks by stable IDs (e.g., ``H7``) assigned in the
    File Summary. This step looks each ID up in the parsed hunk list and
    substitutes the full Hunk (with content + language) into each step.

    Returns ``(walkthrough, warnings)``. Unknown IDs are logged as warnings
    and the placeholder is left in place.
    """
    warnings: list[str] = []
    by_id = {h.id: h for h in parsed_hunks if h.id}

    for thread in walkthrough.threads:
        for step in thread.steps:
            resolved: list[Hunk] = []
            for ref in step.hunks:
                hunk_id = ref.id
                if not hunk_id:
                    # Legacy dict-shaped reference; match by (path, new_start, new_count).
                    matched = _match_by_position(ref, parsed_hunks)
                    if matched is not None:
                        resolved.append(matched)
                    else:
                        warnings.append(
                            f"Legacy hunk reference could not be matched: "
                            f"{ref.file_path} "
                            f"(new_start={ref.new_start}, new_count={ref.new_count})"
                        )
                        resolved.append(ref)
                    continue
                source = by_id.get(hunk_id)
                if source is None:
                    warnings.append(
                        f"Unknown hunk ID '{hunk_id}' — not in parsed diff"
                    )
                    resolved.append(ref)
                    continue
                caption = walkthrough.hunk_captions.get(hunk_id, "")
                if not caption:
                    warnings.append(
                        f"No caption provided for hunk '{hunk_id}'"
                    )
                # Copy content/metadata into a fresh Hunk so thread edits don't
                # mutate the shared parsed instance.
                resolved.append(
                    Hunk(
                        id=source.id,
                        file_path=source.file_path,
                        old_start=source.old_start,
                        old_count=source.old_count,
                        new_start=source.new_start,
                        new_count=source.new_count,
                        content=source.content,
                        context_before=source.context_before,
                        context_after=source.context_after,
                        language=source.language,
                        additions=source.additions,
                        deletions=source.deletions,
                        caption=caption,
                    )
                )
            step.hunks = resolved

    return walkthrough, warnings


def _match_by_position(ref: Hunk, parsed_hunks: list[Hunk]) -> Hunk | None:
    """Fallback for legacy dict-shaped refs without an ID."""
    for h in parsed_hunks:
        if (
            h.file_path == ref.file_path
            and h.new_start == ref.new_start
            and h.new_count == ref.new_count
        ):
            return h
    return None


def orphaned_hunks(
    walkthrough: Walkthrough, parsed_hunks: list[Hunk]
) -> list[Hunk]:
    """Return parsed hunks whose IDs are not referenced by any thread step."""
    covered: set[str] = set()
    for thread in walkthrough.threads:
        for step in thread.steps:
            for h in step.hunks:
                if h.id:
                    covered.add(h.id)
    return [h for h in parsed_hunks if h.id and h.id not in covered]
