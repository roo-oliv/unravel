"""Bottom keybinding hints bar.

Two rows: the top row carries PR-review actions (S submit, a PR cmt, n inline,
v viewed, R refresh) and is only populated when a PR context is loaded; the
bottom row carries the always-relevant navigation/help shortcuts.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from unravel.tui.state import WalkthroughState


class FooterBar(Static):
    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 2;
        background: $surface-darken-2;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def update_state(self, state: WalkthroughState) -> None:
        self.update(Group(_pr_row(state), _general_row(state)))


def _pr_row(state: WalkthroughState) -> Text:
    row = Text()
    if state.pr_ctx is None:
        # Keep the row blank so the footer height stays stable across
        # PR / non-PR runs (Textual reserves the dock height up-front).
        return row

    pending = len(state.pending_review.comments)
    s_chip = "bold black on dark_orange" if pending else "bold"
    s_label = "dark_orange" if pending else ""
    row.append(" S ", style=s_chip)
    review_label = "review"
    if pending:
        plural = "s" if pending != 1 else ""
        review_label = f"review ({pending} pending comment{plural})"
    row.append(f" {review_label}   ", style=s_label)
    row.append(" a ", style="bold")
    row.append("PR cmt   ")
    row.append(" n ", style="bold")
    row.append("inline   ")
    if not state.is_overview:
        row.append(" v ", style="bold")
        row.append("viewed   ")
    row.append(" R ", style="bold")
    row.append("⟳")
    return row


def _general_row(state: WalkthroughState) -> Text:
    row = Text()
    if not state.is_overview:
        row.append(" ←→ ", style="bold")
        row.append("row   ")
    row.append(" [Shift+]Tab ", style="bold")
    row.append("thread   ")
    if not state.is_overview:
        row.append(" Enter ", style="bold")
        row.append("expand   ")
        row.append(" e/c ", style="bold")
        row.append("all   ")
    row.append(" , ", style="bold")
    row.append("settings   ")
    row.append(" ? ", style="bold")
    row.append("help   ")
    row.append(" q ", style="bold")
    row.append("quit")
    return row
