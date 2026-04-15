"""Rich-based page content rendering for the walkthrough screen."""

from __future__ import annotations

import re

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from unravel.models import Hunk, Thread
from unravel.tui.state import WalkthroughState

CODE_STYLE = "bold cyan"

# Explicit markdown-ish syntax: `code`, **bold**, *italic*.
_INLINE_RE = re.compile(
    r"`([^`\n]+)`|\*\*([^*\n]+?)\*\*|(?<![*\w])\*([^*\n]+?)\*(?!\w)"
)

# Auto-detect code-like tokens that the LLM frequently mentions without
# backticks. Each alternative is intentionally conservative to avoid
# highlighting ordinary prose:
#   - name()                  -> function/method calls
#   - snake_case / __dunder__ -> identifiers with at least one underscore
#   - module.function         -> dotted paths (both sides 2+ chars to skip
#                                "i.e.", "e.g.")
#   - CONSTANT_NAMES          -> ALL_CAPS identifiers with an underscore
#   - file.ext                -> common source/config filenames
_FILE_EXTS = (
    "py|pyi|js|jsx|ts|tsx|go|rs|java|rb|c|h|cpp|hpp|cs|swift|kt|"
    "md|json|ya?ml|toml|ini|cfg|html|css|scss|sh|bash|zsh|sql"
)
_AUTO_CODE_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\(\)"
    r"|\b[a-z_][a-z0-9_]*_[a-z0-9_]+\b"
    r"|\b[A-Za-z_][A-Za-z0-9_]+\.[A-Za-z_][A-Za-z0-9_]+\b"
    r"|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"
    rf"|(?:[\w./-]*[A-Za-z0-9_])\.(?:{_FILE_EXTS})\b"
)


def styled_text(content: str, base_style: str = "") -> Text:
    """Render narration into a Rich Text with light syntax highlighting.

    Supports explicit markdown-ish syntax:
      `code`     -> bold cyan
      **bold**   -> bold
      *italic*   -> italic

    Plus auto-detection of unwrapped code-like tokens (snake_case,
    dotted.paths, CONSTANT_NAMES, function(), filenames). Plain words
    inherit ``base_style``.
    """
    text = Text()
    pos = 0
    for match in _INLINE_RE.finditer(content):
        if match.start() > pos:
            _append_with_autodetect(text, content[pos : match.start()], base_style)
        code, bold, italic = match.group(1), match.group(2), match.group(3)
        if code is not None:
            text.append(code, style=CODE_STYLE)
        elif bold is not None:
            text.append(bold, style=_combine(base_style, "bold"))
        else:
            text.append(italic, style=_combine(base_style, "italic"))
        pos = match.end()
    if pos < len(content):
        _append_with_autodetect(text, content[pos:], base_style)
    return text


def _append_with_autodetect(text: Text, segment: str, base_style: str) -> None:
    pos = 0
    for match in _AUTO_CODE_RE.finditer(segment):
        if match.start() > pos:
            text.append(segment[pos : match.start()], style=base_style)
        text.append(match.group(0), style=CODE_STYLE)
        pos = match.end()
    if pos < len(segment):
        text.append(segment[pos:], style=base_style)


def _combine(base: str, extra: str) -> str:
    if not base:
        return extra
    return f"{base} {extra}"


def render_page(state: WalkthroughState) -> RenderableType:
    """Build a Rich renderable for the current page."""
    if state.is_overview:
        return _render_overview(state)
    if state.is_full_diff:
        return _render_full_diff(state)
    return _render_thread(state)


def _render_overview(state: WalkthroughState) -> RenderableType:
    wt = state.walkthrough
    thread_count = len(wt.threads)
    file_count = len(
        {h.file_path for t in wt.threads for s in t.steps for h in s.hunks}
    )

    header_text = Text()
    header_text.append(
        f"{thread_count} thread{'s' if thread_count != 1 else ''}",
        style="bold cyan",
    )
    header_text.append(" across ")
    header_text.append(
        f"{file_count} file{'s' if file_count != 1 else ''}", style="bold cyan"
    )

    parts: list[RenderableType] = [
        Panel(header_text, title="[bold]unravel[/bold]", border_style="cyan"),
        Text(""),
        styled_text(wt.overview),
        Text(""),
        Text("Suggested review order:", style="bold"),
    ]
    for i, tid in enumerate(wt.suggested_order, 1):
        thread = next((t for t in wt.threads if t.id == tid), None)
        if thread:
            line = Text()
            line.append(f"  {i}. ", style="bold cyan")
            line.append(thread.title)
            line.append(f"  ({len(thread.steps)} steps)", style="dim")
            parts.append(line)

    parts.append(Text(""))
    parts.append(
        Text("Press → to start reviewing threads.", style="dim italic")
    )

    return Group(*parts)


def _render_thread(state: WalkthroughState) -> RenderableType:
    thread = state.current_thread
    assert thread is not None

    panel_body = Text()
    panel_body.append(styled_text(thread.root_cause, base_style="bold"))
    panel_body.append("\n\n")
    panel_body.append(styled_text(thread.summary))
    if thread.dependencies:
        panel_body.append("\n\n")
        panel_body.append(
            f"Depends on: {', '.join(thread.dependencies)}", style="dim"
        )

    header = Panel(
        panel_body,
        title=(
            f"[bold magenta]{thread.title}[/bold magenta] "
            f"[dim]({thread.id})[/dim]"
        ),
        border_style="magenta",
    )

    parts: list[RenderableType] = [header, Text("")]
    parts.extend(_render_thread_rows(state, thread))

    return Group(*parts)


def _render_thread_rows(
    state: WalkthroughState, thread: Thread
) -> list[RenderableType]:
    """Render each step with its focusable file rows and expanded diffs."""
    rows_list = state.current_rows()
    row_cursor = 0
    parts: list[RenderableType] = []
    sorted_steps = sorted(thread.steps, key=lambda s: s.order)

    for si, step in enumerate(sorted_steps):
        step_line = Text()
        step_line.append(f"  Step {step.order}: ", style="bold green")
        step_line.append(styled_text(step.narration))
        parts.append(step_line)
        parts.append(Text(""))

        for hi, hunk in enumerate(step.hunks):
            is_focused = row_cursor == state.row_index
            is_expanded = state.is_expanded(state.page_index, row_cursor)

            file_line = Text()
            prefix = "▼ " if is_expanded else "▶ "
            file_line.append(
                f"    {prefix}",
                style="bold yellow" if is_focused else "dim",
            )

            path_style = "bold" if is_focused else ""
            if is_focused:
                file_line.append(
                    f"{hunk.file_path}",
                    style=f"{path_style} reverse yellow".strip(),
                )
            else:
                file_line.append(hunk.file_path, style=path_style)

            if hunk.new_count > 0:
                file_line.append(
                    f"  (lines {hunk.new_start}-"
                    f"{hunk.new_start + hunk.new_count})",
                    style="dim",
                )
            parts.append(file_line)

            if is_expanded:
                parts.append(_render_hunk_diff(hunk))

            row_cursor += 1

        parts.append(Text(""))

    if not rows_list:
        parts.append(Text("    (no hunks in this thread)", style="dim"))

    return parts


def _render_hunk_diff(hunk) -> RenderableType:
    """Render a single hunk's diff content."""
    if hunk.content == "[binary file]":
        return Text("      (binary file)", style="dim")
    if not hunk.content:
        return Text(
            "      (no diff content available)", style="dim italic"
        )
    return Panel(
        Syntax(
            hunk.content,
            "diff",
            theme="monokai",
            line_numbers=False,
            padding=(0, 1),
        ),
        border_style="dim",
        padding=(0, 1),
    )


def _render_full_diff(state: WalkthroughState) -> RenderableType:
    """Render the full-diff reference page grouped by file.

    This page shows every parsed hunk regardless of thread assignment so the
    reviewer always has a ground-truth view of the entire change set.
    """
    header_text = Text()
    file_count = len({h.file_path for h in state.all_hunks})
    hunk_count = len(state.all_hunks)
    header_text.append("Full diff reference", style="bold cyan")
    header_text.append("\n")
    header_text.append(
        f"{hunk_count} hunk{'s' if hunk_count != 1 else ''} "
        f"across {file_count} file{'s' if file_count != 1 else ''}",
        style="dim",
    )

    covered = _covered_hunk_ids(state)
    by_file: dict[str, list[Hunk]] = {}
    for h in state.all_hunks:
        by_file.setdefault(h.file_path, []).append(h)

    parts: list[RenderableType] = [
        Panel(header_text, border_style="cyan"),
        Text(""),
        Text(
            "Every hunk in the PR, regardless of thread assignment. "
            "Use this as a ground-truth reference.",
            style="dim italic",
        ),
        Text(""),
    ]

    for file_path, file_hunks in by_file.items():
        file_line = Text()
        file_line.append(file_path, style="bold yellow")
        file_line.append(
            f"  ({len(file_hunks)} hunk{'s' if len(file_hunks) != 1 else ''})",
            style="dim",
        )
        parts.append(file_line)
        parts.append(Text(""))

        for h in file_hunks:
            id_line = Text()
            id_line.append(f"  {h.id}", style="bold cyan")
            if h.content != "[binary file]":
                end = h.new_start + max(h.new_count - 1, 0)
                id_line.append(f"  (lines {h.new_start}-{end})", style="dim")
            if h.id not in covered:
                id_line.append("  [orphaned]", style="bold red")
            parts.append(id_line)
            parts.append(_render_hunk_diff(h))
            parts.append(Text(""))

    return Group(*parts)


def _covered_hunk_ids(state: WalkthroughState) -> set[str]:
    covered: set[str] = set()
    for thread in state.walkthrough.threads:
        for step in thread.steps:
            for h in step.hunks:
                if h.id:
                    covered.add(h.id)
    return covered
