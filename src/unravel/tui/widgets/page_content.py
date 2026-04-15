"""Rich-based page content rendering for the walkthrough screen."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from unravel.config import DiffDisplayConfig
from unravel.models import EXTENSION_LANGUAGES, Hunk, Thread
from unravel.tui.state import WalkthroughState

# Background tints for added / removed diff lines. Dark hues that sit on top
# of Monokai-like themes without clashing with foreground syntax colors.
_ADD_BG = "#163a1e"
_DEL_BG = "#3a161a"

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
        Text("Press Right Arrow → to start.", style="dim italic")
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
                parts.append(_render_hunk_diff(hunk, state.diff_cfg))

            row_cursor += 1

        parts.append(Text(""))

    if not rows_list:
        parts.append(Text("    (no hunks in this thread)", style="dim"))

    return parts


def _resolve_language(hunk: Hunk) -> str:
    """Pick a lexer name for a hunk (explicit > extension lookup > 'text')."""
    if hunk.language:
        return hunk.language
    suffix = Path(hunk.file_path).suffix
    return EXTENSION_LANGUAGES.get(suffix, "text")


def _render_hunk_diff(hunk: Hunk, diff_cfg: DiffDisplayConfig) -> RenderableType:
    """Render a single hunk's diff content with optional language-aware highlights.

    The output is a Table with (old_no | new_no | sign | code) columns, where
    added/removed lines are tinted green/red across the entire row. Lines are
    either wrapped to the column width or allowed to extend off-screen (and
    revealed via horizontal scrolling) depending on ``diff_cfg.wrap_mode``.
    """
    if hunk.content == "[binary file]":
        return Text("      (binary file)", style="dim")
    if not hunk.content:
        return Text("      (no diff content available)", style="dim italic")

    language = _resolve_language(hunk)
    # A dummy Syntax instance is enough to borrow its Pygments lexer +
    # theme-aware token colorizer via .highlight(). We never render the
    # Syntax itself — only per-line Text objects.
    syntax = (
        Syntax("", language, theme=diff_cfg.theme, tab_size=4)
        if diff_cfg.syntax_highlight
        else None
    )

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=(diff_cfg.wrap_mode == "wrap"),
        show_edge=False,
        pad_edge=False,
    )
    if diff_cfg.show_line_numbers:
        table.add_column(
            "old", justify="right", no_wrap=True, style="dim", width=5
        )
        table.add_column(
            "new", justify="right", no_wrap=True, style="dim", width=5
        )
    table.add_column("sign", no_wrap=True, width=1)
    wrap_code = diff_cfg.wrap_mode == "wrap"
    table.add_column(
        "code",
        ratio=1 if wrap_code else None,
        no_wrap=not wrap_code,
        overflow="fold" if wrap_code else "ignore",
    )

    old_no = hunk.old_start
    new_no = hunk.new_start

    for raw in hunk.content.splitlines():
        if not raw:
            # Empty line — treat as a context line with no content.
            _add_diff_row(
                table,
                diff_cfg,
                tint=None,
                old=old_no,
                new=new_no,
                sign=" ",
                code_text=Text(""),
            )
            old_no += 1
            new_no += 1
            continue

        if raw.startswith("\\"):
            # `\ No newline at end of file` annotation
            span = Text(raw, style="dim italic")
            if diff_cfg.show_line_numbers:
                table.add_row("", "", "", span)
            else:
                table.add_row("", span)
            continue

        sign, body = raw[0], raw[1:]
        code_text = _highlight_line(syntax, body)

        if sign == "+":
            _add_diff_row(
                table,
                diff_cfg,
                tint=_ADD_BG,
                old=None,
                new=new_no,
                sign="+",
                code_text=code_text,
                sign_style="bold green",
            )
            new_no += 1
        elif sign == "-":
            _add_diff_row(
                table,
                diff_cfg,
                tint=_DEL_BG,
                old=old_no,
                new=None,
                sign="-",
                code_text=code_text,
                sign_style="bold red",
            )
            old_no += 1
        else:
            _add_diff_row(
                table,
                diff_cfg,
                tint=None,
                old=old_no,
                new=new_no,
                sign=" ",
                code_text=code_text,
            )
            old_no += 1
            new_no += 1

    return Panel(table, border_style="dim", padding=(0, 1))


def _highlight_line(syntax: Syntax | None, body: str) -> Text:
    """Return a Text for the given line body, optionally language-highlighted."""
    if syntax is None:
        return Text(body)
    highlighted = syntax.highlight(body)
    # Pygments re-adds a trailing newline; strip it so it doesn't cause an
    # extra blank row in the Table cell.
    if highlighted.plain.endswith("\n"):
        highlighted = highlighted[:-1]
    # Let the enclosing Table column decide wrap/no-wrap behavior per the
    # user's diff_cfg.wrap_mode. Syntax.highlight marks Text as no_wrap=True
    # by default, which would override our column settings.
    highlighted.no_wrap = False
    return highlighted


def _add_diff_row(
    table: Table,
    diff_cfg: DiffDisplayConfig,
    *,
    tint: str | None,
    old: int | None,
    new: int | None,
    sign: str,
    code_text: Text,
    sign_style: str = "dim",
) -> None:
    """Add a diff row, applying ``tint`` as a background across the whole row."""
    if tint is not None:
        bg_style = f"on {tint}"
        # Override background on the already-highlighted code while preserving
        # the per-token foreground colors produced by Syntax.highlight.
        code_text.stylize(bg_style)
        num_style = f"dim {bg_style}"
        sign_cell_style = f"{sign_style} {bg_style}"
    else:
        num_style = "dim"
        sign_cell_style = sign_style

    old_cell = "" if old is None else str(old)
    new_cell = "" if new is None else str(new)

    if diff_cfg.show_line_numbers:
        table.add_row(
            Text(old_cell, style=num_style),
            Text(new_cell, style=num_style),
            Text(sign, style=sign_cell_style),
            code_text,
        )
    else:
        table.add_row(
            Text(sign, style=sign_cell_style),
            code_text,
        )


def _render_full_diff(state: WalkthroughState) -> RenderableType:
    """Render the full-diff reference page grouped by file.

    Each hunk is a focusable row (like a thread page), so the reviewer can
    step through them with ↑/↓ and Enter to expand/collapse the diff.
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
    parts: list[RenderableType] = [
        Panel(header_text, border_style="cyan"),
        Text(""),
        Text(
            "Every hunk in the PR, regardless of thread assignment. "
            "↑↓ to focus, Enter to expand.",
            style="dim italic",
        ),
        Text(""),
    ]

    # Group by file but preserve the flat hunk index (matches state.all_hunks)
    # so row focus and expansion keys line up with the state machine.
    by_file: dict[str, list[tuple[int, Hunk]]] = {}
    for i, h in enumerate(state.all_hunks):
        by_file.setdefault(h.file_path, []).append((i, h))

    for file_path, entries in by_file.items():
        file_header = Text()
        file_header.append(file_path, style="bold")
        file_header.append(
            f"  ({len(entries)} hunk{'s' if len(entries) != 1 else ''})",
            style="dim",
        )
        parts.append(file_header)

        for flat_index, hunk in entries:
            is_focused = flat_index == state.row_index
            is_expanded = state.is_expanded(state.page_index, flat_index)

            row_line = Text()
            prefix = "▼ " if is_expanded else "▶ "
            row_line.append(
                f"  {prefix}",
                style="bold yellow" if is_focused else "dim",
            )
            id_style = (
                "bold reverse yellow" if is_focused else "bold cyan"
            )
            row_line.append(hunk.id, style=id_style)
            if hunk.content != "[binary file]":
                end = hunk.new_start + max(hunk.new_count - 1, 0)
                row_line.append(
                    f"  (lines {hunk.new_start}-{end})", style="dim"
                )
            if hunk.id not in covered:
                row_line.append("  [orphaned]", style="bold red")
            parts.append(row_line)

            if is_expanded:
                parts.append(_render_hunk_diff(hunk, state.diff_cfg))

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
