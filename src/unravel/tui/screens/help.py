"""Help screen overlay."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\
[bold cyan]Thread navigation[/bold cyan]
  [bold]Tab[/bold]             Next thread
  [bold]Shift+Tab[/bold]       Previous thread

[bold cyan]Scroll[/bold cyan]
  [bold]↑ ↓[/bold]             Scroll the page

[bold cyan]Row navigation[/bold cyan]
  [bold]→ / l[/bold]           Next row (file); wraps to next thread at the end
  [bold]← / h[/bold]           Previous row (file); wraps to previous thread at the start
  [bold]Enter / Space[/bold]   Expand/collapse diff for current row
  [bold]e[/bold]               Expand all rows on this thread
  [bold]c[/bold]               Collapse all rows on this thread

[bold cyan]General[/bold cyan]
  [bold],[/bold]               Settings (wrap mode, syntax highlight, …)
  [bold]?[/bold]               This help screen
  [bold]q[/bold]               Quit
"""


class HelpScreen(ModalScreen):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 2 3;
        border: round $primary;
        background: $surface;
    }

    #help-title {
        text-align: center;
        margin-bottom: 1;
    }

    #help-dismiss {
        text-align: center;
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("question_mark,escape,q", "dismiss_help", "Close help"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Static("[bold]Keybindings[/bold]", id="help-title")
            yield Static(HELP_TEXT)
            yield Static("[dim]Press ? or Esc to close[/dim]", id="help-dismiss")

    def action_dismiss_help(self) -> None:
        self.app.pop_screen()
