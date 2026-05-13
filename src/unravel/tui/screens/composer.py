"""Centered modal with a markdown TextArea: returns the body text on submit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea


class ComposerScreen(ModalScreen[str | None]):
    """Modal text composer.

    Dismisses with the typed body on Ctrl+Enter, or ``None`` on Esc.
    The caller decides what to do with the body (post via gh, append to
    pending review, set review summary, etc.).
    """

    DEFAULT_CSS = """
    ComposerScreen {
        align: center middle;
    }
    #composer-box {
        width: 80%;
        max-width: 100;
        height: 20;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #composer-title {
        height: 1;
        color: $text;
    }
    #composer-area {
        height: 14;
        border: round $primary-darken-2;
    }
    #composer-hint {
        height: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+j", "submit", "Submit", show=False),  # ctrl+enter fallback
    ]

    def __init__(
        self,
        title: str = "Comment",
        initial: str = "",
        placeholder: str = "Write your comment in markdown…",
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="composer-box"):
            yield Static(self._title, id="composer-title")
            ta = TextArea.code_editor(
                self._initial,
                language="markdown",
                id="composer-area",
                show_line_numbers=False,
            )
            ta.tab_behavior = "focus"
            yield ta
            yield Static(
                "Ctrl+Enter submit · Esc cancel",
                id="composer-hint",
            )

    def on_mount(self) -> None:
        area = self.query_one("#composer-area", TextArea)
        area.focus()

    def on_key(self, event) -> None:
        # ``ctrl+enter`` doesn't reach Bindings reliably through TextArea on
        # every terminal — intercept here so submit always works.
        if event.key == "ctrl+enter":
            event.stop()
            self.action_submit()

    def action_submit(self) -> None:
        area = self.query_one("#composer-area", TextArea)
        body = area.text.strip()
        if not body:
            self.app.bell()
            return
        self.dismiss(body)

    def action_cancel(self) -> None:
        self.dismiss(None)
