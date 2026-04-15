"""Horizontal dot timeline widget showing thread progress."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from unravel.tui.state import PageStatus, WalkthroughState

STATUS_CHAR: dict[PageStatus, str] = {
    "completed": "✓",
    "current": "●",
    "unvisited": "○",
}

STATUS_STYLE: dict[PageStatus, str] = {
    "completed": "green",
    "current": "bold yellow",
    "unvisited": "dim",
}


class Timeline(Static):
    DEFAULT_CSS = """
    Timeline {
        dock: top;
        height: 3;
        padding: 0 2;
        background: $surface-darken-1;
        content-align: center middle;
    }
    """

    def update_state(self, state: WalkthroughState) -> None:
        self.update(_render_timeline(state))


def _render_timeline(state: WalkthroughState) -> Group:
    """Build a 3-row Rich renderable: title | dots | thread count."""
    # Title line (only the current thread gets a title)
    title_line = Text(justify="center")
    if state.is_overview:
        title_line.append("Overview", style="bold cyan")
    elif state.is_full_diff:
        title_line.append("Full diff", style="bold cyan")
        title_line.append("  (reference)", style="dim")
    else:
        assert state.current_thread is not None
        title_line.append(state.current_thread.title, style="bold magenta")
        title_line.append(
            f"  ({state.page_index}/{state.thread_count})", style="dim"
        )

    # Dots line
    dots_line = _render_dots(state)

    # Status hint line
    status = Text(justify="center")
    if state.is_overview:
        status.append("press → to start", style="dim italic")
    elif state.is_full_diff:
        rows = state.current_rows()
        if rows:
            status.append(
                f"hunk {state.row_index + 1}/{len(rows)} — "
                "Tab/Shift+Tab focus, Enter to expand",
                style="dim italic",
            )
        else:
            status.append(
                "ground-truth view of every hunk", style="dim italic"
            )
    else:
        rows = state.current_rows()
        if rows:
            status.append(
                f"row {state.row_index + 1}/{len(rows)} — "
                "Tab/Shift+Tab focus, Enter to expand",
                style="dim italic",
            )

    return Group(title_line, dots_line, status)


def _render_dots(state: WalkthroughState) -> Text:
    """Render the horizontal dot indicator across the full width."""
    n = state.thread_count
    if n == 0:
        return Text("", justify="center")

    line = Text(justify="center")
    for i in range(1, n + 1):
        status = state.page_status(i)
        line.append(STATUS_CHAR[status], style=STATUS_STYLE[status])
        if i < n:
            # Colour the connector by the "earlier" side's state so completed
            # segments glow green up to the current dot.
            sep_status = (
                "completed"
                if state.page_status(i) == "completed"
                and state.page_status(i + 1) != "unvisited"
                else "unvisited"
            )
            line.append(" ─── ", style=STATUS_STYLE[sep_status])

    return line
