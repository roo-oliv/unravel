"""Output rendering for walkthroughs."""

from __future__ import annotations

import base64
import hashlib
import json

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

from unravel.models import Hunk, Walkthrough

COMMENT_MARKER_START = "<!-- unravel-cache-v2-start -->"
COMMENT_MARKER_DATA_PREFIX = "<!-- unravel-cache-v2-data:"
COMMENT_MARKER_END = "<!-- unravel-cache-v2-end -->"
COMMENT_MARKER_SHA_PREFIX = "<!-- unravel-cache-v2-sha:"
COMMENT_MARKER_STATUS_PREFIX = "<!-- unravel-cache-v2-status:"
COMMENT_MARKER_SUFFIX = " -->"

STATUS_IN_PROGRESS = "in-progress"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def render_json(walkthrough: Walkthrough) -> str:
    return walkthrough.to_json(indent=2)


def render_rich(walkthrough: Walkthrough, console: Console) -> None:
    threads = walkthrough.threads
    file_count = len({
        h.file_path for t in threads for s in t.steps for h in s.hunks
    })

    header = Text()
    header.append(f"{len(threads)} thread{'s' if len(threads) != 1 else ''}", style="bold cyan")
    header.append(" across ")
    header.append(f"{file_count} file{'s' if file_count != 1 else ''}", style="bold cyan")
    console.print(Panel(header, title="[bold]Unravel[/bold]", border_style="cyan"))

    console.print()
    console.print(walkthrough.overview)
    console.print()

    if walkthrough.suggested_order:
        console.print("[bold]Suggested review order:[/bold]")
        for i, tid in enumerate(walkthrough.suggested_order, 1):
            console.print(f"  {i}. {tid}")
        console.print()

    for thread in threads:
        _render_thread(thread, walkthrough, console)


def _render_thread(thread, walkthrough: Walkthrough, console: Console) -> None:
    dep_text = ""
    if thread.dependencies:
        dep_text = f"\n[dim]Depends on: {', '.join(thread.dependencies)}[/dim]"

    panel_content = Text()
    panel_content.append(thread.summary)

    console.print(Panel(
        f"[bold]{thread.root_cause}[/bold]\n\n{thread.summary}{dep_text}",
        title=f"[bold magenta]{thread.title}[/bold magenta] [dim]({thread.id})[/dim]",
        border_style="magenta",
    ))

    for step in sorted(thread.steps, key=lambda s: s.order):
        console.print(f"  [bold]Step {step.order}:[/bold] {step.narration}")
        console.print()
        for hunk in step.hunks:
            console.print(f"    [dim]{hunk.file_path}[/dim]")
            if hunk.content and hunk.content != "[binary file]":
                syntax = Syntax(
                    hunk.content,
                    "diff",
                    theme="monokai",
                    line_numbers=False,
                    padding=1,
                )
                console.print(syntax)
        console.print()


def render_tree(walkthrough: Walkthrough, console: Console) -> None:
    tree = Tree("[bold cyan]Unravel[/bold cyan]")
    tree.add(f"[dim]{walkthrough.overview}[/dim]")

    for thread in walkthrough.threads:
        if thread.dependencies:
            deps = f" [dim](depends: {', '.join(thread.dependencies)})[/dim]"
        else:
            deps = ""
        label = f"[bold magenta]{thread.title}[/bold magenta] [dim]({thread.id})[/dim]{deps}"
        branch = tree.add(label)
        branch.add(f"[italic]{thread.root_cause}[/italic]")
        for step in sorted(thread.steps, key=lambda s: s.order):
            step_branch = branch.add(f"Step {step.order}: {step.narration}")
            for hunk in step.hunks:
                step_branch.add(f"[dim]{hunk.file_path}[/dim]")

    console.print(tree)


def _thread_file_count(walkthrough: Walkthrough) -> int:
    return len({
        h.file_path for t in walkthrough.threads for s in t.steps for h in s.hunks
    })


def _hunk_line_range(hunk: Hunk) -> str:
    """Return a human-readable line range like ``L480-492``, or empty string."""
    if hunk.new_start and hunk.new_count:
        end = hunk.new_start + hunk.new_count - 1
        if end == hunk.new_start:
            return f"L{hunk.new_start}"
        return f"L{hunk.new_start}\u2013{end}"
    if hunk.old_start and hunk.old_count:
        end = hunk.old_start + hunk.old_count - 1
        if end == hunk.old_start:
            return f"L{hunk.old_start}"
        return f"L{hunk.old_start}\u2013{end}"
    return ""


def _github_diff_anchor(hunk: Hunk) -> str | None:
    """Build the ``#diff-...`` fragment for a GitHub PR files URL."""
    file_hash = hashlib.sha256(hunk.file_path.encode()).hexdigest()
    if hunk.new_start and hunk.new_count:
        end = hunk.new_start + hunk.new_count - 1
        return f"diff-{file_hash}R{hunk.new_start}-R{end}"
    if hunk.old_start and hunk.old_count:
        end = hunk.old_start + hunk.old_count - 1
        return f"diff-{file_hash}L{hunk.old_start}-L{end}"
    return None


def _format_hunk_ref(hunk: Hunk, pr_files_url: str | None) -> str | None:
    """Format a hunk as a markdown list item with optional diff link."""
    if not hunk.file_path:
        return None
    label = hunk.file_path
    line_range = _hunk_line_range(hunk)
    if line_range:
        label += f":{line_range}"
    if pr_files_url:
        anchor = _github_diff_anchor(hunk)
        if anchor:
            return f"- [`{label}`]({pr_files_url}#{anchor})"
    return f"- `{label}`"


def render_markdown(
    walkthrough: Walkthrough,
    *,
    pr_files_url: str | None = None,
) -> str:
    """Render walkthrough as GitHub-flavored markdown.

    When *pr_files_url* is provided (e.g.
    ``https://github.com/owner/repo/pull/42/files``), each hunk reference
    becomes a direct link to the relevant diff range on GitHub.
    """
    threads = walkthrough.threads
    file_count = _thread_file_count(walkthrough)

    parts: list[str] = []

    t_word = "thread" if len(threads) == 1 else "threads"
    f_word = "file" if file_count == 1 else "files"
    parts.append(f"{len(threads)} {t_word} across {file_count} {f_word}")
    parts.append("")
    parts.append(walkthrough.overview)
    parts.append("")

    if walkthrough.suggested_order:
        order_str = " \u2192 ".join(f"`{tid}`" for tid in walkthrough.suggested_order)
        parts.append(f"**Suggested review order:** {order_str}")
        parts.append("")

    for thread in threads:
        parts.append("---")
        parts.append("")
        parts.append(f"### {thread.title} (`{thread.id}`)")
        parts.append("")
        parts.append(f"**Root cause:** {thread.root_cause}")
        parts.append("")
        parts.append(thread.summary)
        parts.append("")

        if thread.dependencies:
            deps = ", ".join(thread.dependencies)
            parts.append(f"*Depends on: {deps}*")
            parts.append("")

        for step in sorted(thread.steps, key=lambda s: s.order):
            parts.append(f"**Step {step.order}:** {step.narration}")
            for h in step.hunks:
                ref = _format_hunk_ref(h, pr_files_url)
                if ref:
                    parts.append(ref)
            parts.append("")

    return "\n".join(parts)


UNRAVEL_INSTALL_URL = "https://github.com/roo-oliv/unravel#installation"


def _pr_cli_ref(pr_number: int | None, repo_nwo: str | None) -> str:
    """Build the ``unravel pr ...`` invocation shown in the comment CTA."""
    if pr_number is None:
        return "unravel pr <number>"
    if repo_nwo:
        return f"unravel pr {repo_nwo}#{pr_number}"
    return f"unravel pr {pr_number}"


def _envelope_open(head_sha: str, status: str) -> list[str]:
    """Return the lines that open a v2 cache envelope (start + sha + status)."""
    return [
        COMMENT_MARKER_START,
        f"{COMMENT_MARKER_SHA_PREFIX}{head_sha}{COMMENT_MARKER_SUFFIX}",
        f"{COMMENT_MARKER_STATUS_PREFIX}{status}{COMMENT_MARKER_SUFFIX}",
    ]


def render_github_comment(
    walkthrough: Walkthrough,
    *,
    head_sha: str,
    pr_files_url: str | None = None,
    pr_number: int | None = None,
    repo_nwo: str | None = None,
) -> str:
    """Render the full GitHub PR comment body with visible summary and hidden cache.

    The comment has four parts:
    1. A header with thread/file counts
    2. A CTA suggesting the CLI for a better review experience
    3. A collapsible ``<details>`` block with the full markdown walkthrough
    4. A base64-encoded JSON payload hidden inside an HTML comment

    *head_sha* is the 40-char commit SHA the analysis was run against; it is
    embedded so ``unravel pr`` can reject the cache when the PR has moved on.
    """
    threads = walkthrough.threads
    file_count = _thread_file_count(walkthrough)

    t_word = "thread" if len(threads) == 1 else "threads"
    f_word = "file" if file_count == 1 else "files"

    cli_ref = _pr_cli_ref(pr_number, repo_nwo)

    md_body = render_markdown(walkthrough, pr_files_url=pr_files_url)
    json_payload = json.dumps(walkthrough.to_dict())
    encoded = base64.b64encode(json_payload.encode("utf-8")).decode("ascii")

    parts = [
        *_envelope_open(head_sha, STATUS_DONE),
        "",
        f"### Changes unravelled in {len(threads)} {t_word} across {file_count} {f_word}",
        "",
        f"Review locally with `{cli_ref}`",
        "",
        "<details>",
        "<summary>Click to expand walkthrough</summary>",
        "",
        (
            "For a better review experience, "
            f"[install and run unravel locally]({UNRAVEL_INSTALL_URL})"
        ),
        "",
        md_body,
        "</details>",
        "",
        f"{COMMENT_MARKER_DATA_PREFIX}{encoded}{COMMENT_MARKER_SUFFIX}",
        COMMENT_MARKER_END,
    ]

    return "\n".join(parts)


def render_github_comment_placeholder(
    *,
    head_sha: str,
    pr_number: int | None = None,
    repo_nwo: str | None = None,
) -> str:
    """Render an in-progress placeholder comment posted at action start.

    The body has the v2 envelope (start + sha + ``status:in-progress``) but no
    ``data`` marker — the analysis hasn't run yet. The CI step PATCHes this
    comment with the full walkthrough once analysis finishes.
    """
    cli_ref = _pr_cli_ref(pr_number, repo_nwo)
    short = head_sha[:7] if head_sha else ""
    parts = [
        *_envelope_open(head_sha, STATUS_IN_PROGRESS),
        "",
        f"### Unravel is analysing this PR{f' (commit `{short}`)' if short else ''}…",
        "",
        (
            "This comment will be updated when the walkthrough is ready. "
            f"You can also run `{cli_ref}` locally to skip the wait."
        ),
        "",
        COMMENT_MARKER_END,
    ]
    return "\n".join(parts)


def render_github_comment_failed(
    *,
    head_sha: str,
    reason: str | None = None,
) -> str:
    """Render a failure-state comment used when the action errors out."""
    parts = [
        *_envelope_open(head_sha, STATUS_FAILED),
        "",
        "### Unravel failed",
        "",
        reason
        or "The Unravel action errored out — check the workflow logs for details.",
        "",
        COMMENT_MARKER_END,
    ]
    return "\n".join(parts)
