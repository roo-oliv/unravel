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
        if not state.is_overview:
            hints.append(" ←→ ", style="bold")
            hints.append("row   ")
            hints.append(" ↑↓ ", style="bold")
            hints.append("scroll   ")
        hints.append(" [Shift+]Tab ", style="bold")
        hints.append("thread   ")
        if not state.is_overview:
            hints.append(" Enter ", style="bold")
            hints.append("expand   ")
            hints.append(" e/c ", style="bold")
            hints.append("all expand/collapse   ")
        hints.append(" , ", style="bold")
        hints.append("settings   ")
        hints.append(" ? ", style="bold")
        hints.append("help   ")
        hints.append(" q ", style="bold")
        hints.append("quit")
        self.update(hints)
