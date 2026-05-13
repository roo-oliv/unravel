"""Render the PR conversation feed (description + reviews + comments).

Pure-rendering module — no widget. The overview page calls
``render_pr_feed(state)`` and embeds the resulting renderables directly
below the suggested-review-order list, so the conversation lives where
the user lands first and there's no separate UI surface to manage.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from unravel.tui.review_state import (
    IssueComment,
    PrSnapshot,
    ReviewComment,
    ReviewSummary,
)
from unravel.tui.state import WalkthroughState

_REVIEW_STATE_STYLES: dict[str, tuple[str, str]] = {
    "APPROVED": ("✓ approved", "bold green"),
    "CHANGES_REQUESTED": ("✗ requested changes", "bold red"),
    "COMMENTED": ("✎ commented", "bold cyan"),
    "DISMISSED": ("∅ dismissed", "dim"),
    "PENDING": ("… pending", "dim italic"),
}


def render_pr_feed(state: WalkthroughState) -> list[RenderableType]:
    """Return the PR conversation as a list of Rich renderables, or empty when
    there's nothing to show (no PR context)."""
    if state.pr_ctx is None:
        return []

    parts: list[RenderableType] = [Text(""), Rule(style="dim")]
    title = Text("PR conversation", style="bold")
    parts.append(title)
    parts.append(Text(""))

    if state.pr_snapshot is None:
        if state.pr_snapshot_error:
            parts.append(Text(f"Failed to load: {state.pr_snapshot_error}", style="red"))
        else:
            parts.append(Text("Loading…", style="dim italic"))
        return parts

    snap = state.pr_snapshot

    parts.append(_render_pr_header(snap))
    parts.append(Text(""))

    feed = _interleave_feed(snap)
    if not feed:
        parts.append(Text("(no comments yet)", style="dim italic"))
    else:
        for item in feed:
            parts.append(item)
            parts.append(Text(""))

    return parts


def _render_pr_header(snap: PrSnapshot) -> Panel:
    title_line = Text()
    title_line.append(snap.title, style="bold")
    title_line.append(f"  by {snap.author}", style="dim")

    body = snap.body.strip() or "(no description)"
    from rich.console import Group

    inner = Group(
        title_line,
        Text(""),
        Text(body, style="dim"),
    )
    return Panel(inner, border_style="dim", padding=(0, 1))


def _interleave_feed(snap: PrSnapshot) -> list[RenderableType]:
    """Order issue comments + reviews + their inline threads by timestamp."""
    feed: list[tuple[str, object]] = []

    for c in snap.issue_comments:
        feed.append((c.created_at, ("issue", c)))

    review_lookup = {r.id: r for r in snap.review_summaries}
    inline_by_review: dict[int, list[ReviewComment]] = {}
    orphan_inline: list[ReviewComment] = []
    for rc in snap.review_comments:
        if rc.review_id and rc.review_id in review_lookup:
            inline_by_review.setdefault(rc.review_id, []).append(rc)
        else:
            orphan_inline.append(rc)

    for r in snap.review_summaries:
        feed.append(
            (r.submitted_at or "", ("review", (r, inline_by_review.get(r.id, []))))
        )

    for rc in orphan_inline:
        feed.append((rc.created_at, ("orphan_inline", rc)))

    feed.sort(key=lambda x: x[0] or "")

    rendered: list[RenderableType] = []
    for _, item in feed:
        kind = item[0]
        if kind == "issue":
            rendered.append(_render_issue_comment(item[1]))
        elif kind == "review":
            review, threads = item[1]
            rendered.append(_render_review(review, threads))
        else:  # orphan_inline
            rendered.append(_render_orphan_inline(item[1]))
    return rendered


def _render_issue_comment(c: IssueComment) -> Panel:
    from rich.console import Group

    header = Text()
    header.append(f"@{c.author}", style="bold cyan")
    if c.created_at:
        header.append(f"  {c.created_at[:10]}", style="dim")
    body = c.body.strip() or "(empty)"
    return Panel(
        Group(header, Text(""), Text(body)),
        border_style="cyan",
        padding=(0, 1),
    )


def _render_review(review: ReviewSummary, inline: list[ReviewComment]) -> Panel:
    from rich.console import Group

    header = Text()
    header.append(f"@{review.author}  ", style="bold")
    label, style = _REVIEW_STATE_STYLES.get(
        review.state, (review.state.lower(), "bold")
    )
    header.append(label, style=style)
    if review.submitted_at:
        header.append(f"  {review.submitted_at[:10]}", style="dim")

    parts: list[RenderableType] = [header]
    body = review.body.strip()
    if body:
        parts.append(Text(""))
        parts.append(Text(body))

    if inline:
        parts.append(Text(""))
        parts.append(Text(f"  {len(inline)} inline comment(s):", style="dim italic"))
        for ic in inline[:5]:
            parts.append(_render_inline_thread(ic, indent="    "))
        if len(inline) > 5:
            parts.append(
                Text(f"    … {len(inline) - 5} more in diff view", style="dim italic")
            )

    border = {
        "APPROVED": "green",
        "CHANGES_REQUESTED": "red",
        "COMMENTED": "cyan",
    }.get(review.state, "dim")
    return Panel(Group(*parts), border_style=border, padding=(0, 1))


def _render_orphan_inline(rc: ReviewComment) -> Panel:
    return Panel(
        _render_inline_thread(rc, indent=""),
        border_style="dim",
        padding=(0, 1),
    )


def _render_inline_thread(rc: ReviewComment, *, indent: str) -> Text:
    out = Text()
    out.append(f"{indent}{rc.path}", style="bold yellow")
    if rc.line is not None:
        if rc.start_line and rc.start_line != rc.line:
            out.append(f":{rc.start_line}-{rc.line}", style="yellow")
        else:
            out.append(f":{rc.line}", style="yellow")
    if rc.is_outdated:
        out.append("  (outdated)", style="dim italic")
    out.append("\n")
    out.append(f"{indent}@{rc.author}", style="cyan")
    out.append("  ")
    out.append(rc.body.strip() or "(empty)")
    return out
