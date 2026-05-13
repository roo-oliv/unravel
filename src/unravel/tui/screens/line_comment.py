"""Pick a line (or range) inside a hunk to anchor a new inline comment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from unravel.models import Hunk
from unravel.tui.review_state import PendingReviewComment, Side
from unravel.tui.screens.composer import ComposerScreen


@dataclass
class _Line:
    """One row in the hunk renderer (file-relative, not diff-relative)."""

    sign: Literal[" ", "+", "-"]
    side: Side
    line_no: int  # the file line number on that side (new_no for RIGHT, old_no for LEFT)
    text: str


def _walk_hunk_lines(hunk: Hunk) -> list[_Line]:
    """Translate raw hunk content into addressable lines."""
    lines: list[_Line] = []
    old_no = hunk.old_start
    new_no = hunk.new_start
    if not hunk.content or hunk.content == "[binary file]":
        return lines
    for raw in hunk.content.splitlines():
        if not raw:
            lines.append(_Line(" ", "RIGHT", new_no, ""))
            old_no += 1
            new_no += 1
            continue
        if raw.startswith("\\"):
            continue  # "\ No newline at end of file" — not addressable
        sign, body = raw[0], raw[1:]
        if sign == "+":
            lines.append(_Line("+", "RIGHT", new_no, body))
            new_no += 1
        elif sign == "-":
            lines.append(_Line("-", "LEFT", old_no, body))
            old_no += 1
        else:
            lines.append(_Line(" ", "RIGHT", new_no, body))
            old_no += 1
            new_no += 1
    return lines


class LineRangeScreen(ModalScreen[PendingReviewComment | None]):
    """Show the hunk lines and let the user pick a single line or a range.

    Bindings:

    - ``j`` / ``down``, ``k`` / ``up`` — move cursor
    - ``v``                            — toggle range anchor (start_line)
    - ``enter``                        — confirm selection → open composer
    - ``escape``                       — cancel
    """

    DEFAULT_CSS = """
    LineRangeScreen {
        align: center middle;
    }
    #linepick-box {
        width: 90%;
        max-width: 120;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #linepick-title {
        height: 1;
    }
    #linepick-hint {
        height: 1;
        color: $text-muted;
    }
    #linepick-scroll {
        height: 1fr;
        border: round $primary-darken-2;
    }
    """

    BINDINGS = [
        Binding("j,down", "next_line", "Next line", show=False),
        Binding("k,up", "prev_line", "Previous line", show=False),
        Binding("v", "toggle_anchor", "Toggle range anchor", show=False),
        Binding("enter", "confirm", "Confirm selection", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, hunk: Hunk) -> None:
        super().__init__()
        self._hunk = hunk
        self._lines = _walk_hunk_lines(hunk)
        self._cursor = 0
        self._anchor: int | None = None  # index into self._lines for range start

    def compose(self) -> ComposeResult:
        with Vertical(id="linepick-box"):
            yield Static(self._title_text(), id="linepick-title")
            with ScrollableContainer(id="linepick-scroll"):
                yield Static(id="linepick-body")
            yield Static(self._hint_text(), id="linepick-hint")

    def on_mount(self) -> None:
        if not self._lines:
            self.app.bell()
            self.dismiss(None)
            return
        self._refresh()

    def _title_text(self) -> Text:
        t = Text()
        t.append("Pick a line for your comment  ", style="bold")
        t.append(self._hunk.file_path, style="bold yellow")
        return t

    def _hint_text(self) -> str:
        return "j/k move · v toggle range · Enter confirm · Esc cancel"

    def _refresh(self) -> None:
        body = self.query_one("#linepick-body", Static)
        body.update(self._render_lines())

    def _render_lines(self) -> Panel:
        if not self._lines:
            return Panel(Text("(no addressable lines)", style="dim italic"))

        rows: list[Text] = []
        lo, hi = self._range_bounds()
        for i, ln in enumerate(self._lines):
            t = Text(no_wrap=True)
            in_range = lo <= i <= hi
            is_cursor = i == self._cursor

            num_style = "dim"
            if in_range:
                num_style = "yellow"
            t.append(f"{ln.line_no:>5} ", style=num_style)
            sign_style = {
                "+": "bold green",
                "-": "bold red",
                " ": "dim",
            }[ln.sign]
            t.append(f"{ln.sign} ", style=sign_style)
            t.append(ln.text or "")

            if is_cursor:
                t.stylize("reverse")
            elif in_range and self._anchor is not None:
                t.stylize("on grey15")
            rows.append(t)

        return Panel(Group(*rows), border_style="dim")

    def _range_bounds(self) -> tuple[int, int]:
        if self._anchor is None:
            return (self._cursor, self._cursor)
        return (min(self._anchor, self._cursor), max(self._anchor, self._cursor))

    def action_next_line(self) -> None:
        if self._cursor < len(self._lines) - 1:
            self._cursor += 1
            self._refresh()

    def action_prev_line(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self._refresh()

    def action_toggle_anchor(self) -> None:
        if self._anchor is None:
            self._anchor = self._cursor
        else:
            self._anchor = None
        self._refresh()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        if not self._lines:
            self.dismiss(None)
            return
        lo, hi = self._range_bounds()
        start = self._lines[lo]
        end = self._lines[hi]

        # GitHub requires both endpoints to be on the same side for ranges.
        if start.side != end.side:
            self.notify(
                "Range must stay on one side (only LEFT or only RIGHT).",
                severity="warning",
            )
            return

        path = self._hunk.file_path
        side = end.side
        line = end.line_no
        start_line: int | None = None
        start_side: Side | None = None
        if start.line_no != end.line_no:
            start_line = start.line_no
            start_side = start.side

        def _after_compose(body: str | None) -> None:
            if not body:
                # Composer cancelled — return to walkthrough without a comment.
                self.dismiss(None)
                return
            comment = PendingReviewComment(
                path=path,
                line=line,
                side=side,
                body=body,
                start_line=start_line,
                start_side=start_side,
            )
            self.dismiss(comment)

        loc = f"{path}:{start_line}-{line}" if start_line else f"{path}:{line}"
        self.app.push_screen(
            ComposerScreen(title=f"New inline comment — {loc}"),
            _after_compose,
        )
