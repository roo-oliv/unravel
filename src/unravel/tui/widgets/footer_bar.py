"""Bottom keybinding hints bar."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from unravel.tui.state import WalkthroughState


class FooterBar(Static):
    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $surface-darken-2;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def update_state(self, state: WalkthroughState) -> None:
        hints = Text()
        pending = len(state.pending_review.comments)
        if state.pr_ctx is not None:
            # S goes first and turns orange when there's unsubmitted work.
            s_chip = "bold black on dark_orange" if pending else "bold"
            s_label = "dark_orange" if pending else ""
            hints.append(" S ", style=s_chip)
            review_label = "review"
            if pending:
                plural = "s" if pending != 1 else ""
                review_label = f"review ({pending} pending comment{plural})"
            hints.append(f" {review_label}   ", style=s_label)
            hints.append(" a ", style="bold")
            hints.append("PR cmt   ")
            hints.append(" n ", style="bold")
            hints.append("inline   ")
            hints.append(" R ", style="bold")
            hints.append("⟳   ")
        if not state.is_overview:
            hints.append(" ←→ ", style="bold")
            hints.append("row   ")
        hints.append(" [Shift+]Tab ", style="bold")
        hints.append("thread   ")
        if not state.is_overview:
            hints.append(" Enter ", style="bold")
            hints.append("expand   ")
            hints.append(" e/c ", style="bold")
            hints.append("all   ")
        hints.append(" , ", style="bold")
        hints.append("settings   ")
        hints.append(" ? ", style="bold")
        hints.append("help   ")
        hints.append(" q ", style="bold")
        hints.append("quit")
        self.update(hints)
