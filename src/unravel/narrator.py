"""Post-processing validation for walkthroughs."""

from __future__ import annotations

from unravel.models import Hunk, Walkthrough


def validate_walkthrough(walkthrough: Walkthrough, hunks: list[Hunk]) -> list[str]:
    """Validate a walkthrough against the original hunks.

    Returns a list of warning strings. Empty list means all checks passed.
    """
    warnings: list[str] = []

    warnings.extend(_check_hunk_coverage(walkthrough, hunks))
    warnings.extend(_check_dependency_refs(walkthrough))
    warnings.extend(_check_suggested_order(walkthrough))

    return warnings


def _check_hunk_coverage(walkthrough: Walkthrough, hunks: list[Hunk]) -> list[str]:
    """Check that every parsed hunk ID is referenced by at least one thread."""
    warnings: list[str] = []
    covered: set[str] = set()
    for thread in walkthrough.threads:
        for step in thread.steps:
            for h in step.hunks:
                if h.id:
                    covered.add(h.id)

    for h in hunks:
        if not h.id:
            continue
        if h.id not in covered:
            end = h.new_start + max(h.new_count - 1, 0)
            warnings.append(
                f"Orphaned hunk {h.id}: {h.file_path} "
                f"(lines {h.new_start}-{end})"
            )
    return warnings


def _check_dependency_refs(walkthrough: Walkthrough) -> list[str]:
    """Check that all dependency references point to existing thread IDs."""
    warnings: list[str] = []
    thread_ids = {t.id for t in walkthrough.threads}
    for thread in walkthrough.threads:
        for dep in thread.dependencies:
            if dep not in thread_ids:
                warnings.append(
                    f"Thread '{thread.id}' depends on unknown thread '{dep}'"
                )
    return warnings


def _check_suggested_order(walkthrough: Walkthrough) -> list[str]:
    """Check that suggested_order references valid thread IDs."""
    warnings: list[str] = []
    thread_ids = {t.id for t in walkthrough.threads}
    for tid in walkthrough.suggested_order:
        if tid not in thread_ids:
            warnings.append(f"Suggested order references unknown thread '{tid}'")
    missing = thread_ids - set(walkthrough.suggested_order)
    for tid in sorted(missing):
        warnings.append(f"Thread '{tid}' missing from suggested_order")
    return warnings
