"""Confirm what to do with pending review when the user tries to quit."""

from __future__ import annotations

from typing import Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

QuitDecision = Literal["save", "submit", "discard"]


class QuitConfirmScreen(ModalScreen[QuitDecision | None]):
    """Prompt before quitting when there are unsubmitted comments.

    Returns:
      - ``"save"``     — keep pending on disk and quit (default for ``q``).
      - ``"submit"``   — open the submit-review dialog.
      - ``"discard"``  — drop pending entirely and quit.
      - ``None``       — cancel: stay in the TUI.

    Defaulting to *save* means accidental ``q`` presses never lose work — a
    fresh ``unravel pr <num>`` restores the comments. Discarding is opt-in.
    """

    DEFAULT_CSS = """
    QuitConfirmScreen {
        align: center middle;
    }
    #quit-box {
        width: 64;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #quit-title { height: 1; }
    #quit-message { height: auto; padding: 1 0; }
    #quit-buttons { height: 3; align: center middle; }
    Button { margin: 0 1; min-width: 14; }
    #quit-hint { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("q", "save_and_quit", "Save & quit", show=False),
        Binding("s", "go_submit", "Submit", show=False),
        Binding("x", "discard_and_quit", "Discard & quit", show=False),
        Binding("escape", "cancel", "Back", show=False),
        Binding("left,up", "focus_prev", show=False),
        Binding("right,down", "focus_next", show=False),
    ]

    def __init__(self, pending_count: int) -> None:
        super().__init__()
        self._pending_count = pending_count

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-box"):
            yield Static(Text("Quit unravel?", style="bold"), id="quit-title")
            yield Static(self._message(), id="quit-message")
            with Horizontal(id="quit-buttons"):
                yield Button("Keep & quit", variant="primary", id="btn-save")
                yield Button("Submit", variant="success", id="btn-submit")
                yield Button("Discard & quit", variant="warning", id="btn-discard")
                yield Button("Back", variant="default", id="btn-back")
            yield Static(
                "q keep · s submit · x discard · Esc back  (or click / Tab+Enter)",
                id="quit-hint",
            )

    def on_mount(self) -> None:
        first = self.query_one("#btn-save", Button)
        first.focus()

    def _message(self) -> Text:
        plural = "s" if self._pending_count != 1 else ""
        t = Text()
        t.append(f"You have {self._pending_count} pending comment{plural}.", style="bold")
        t.append(
            "\n\nKeep them and they'll be restored next time you open this PR.",
            style="dim",
        )
        return t

    # ---- Actions ----

    def action_save_and_quit(self) -> None:
        self.dismiss("save")

    def action_go_submit(self) -> None:
        self.dismiss("submit")

    def action_discard_and_quit(self) -> None:
        self.dismiss("discard")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_prev(self) -> None:
        self.focus_previous()

    def action_focus_next(self) -> None:
        self.focus_next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping: dict[str, QuitDecision | None] = {
            "btn-save": "save",
            "btn-submit": "submit",
            "btn-discard": "discard",
            "btn-back": None,
        }
        self.dismiss(mapping.get(event.button.id or ""))
