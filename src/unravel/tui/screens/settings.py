"""In-TUI settings modal.

Users toggle display preferences with single-key shortcuts; changes are
written through to the persistent config file immediately so they survive
across sessions.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from unravel.config import DiffDisplayConfig, update_setting

# A small built-in rotation so `t` cycles through a sensible palette without
# needing the user to know every Pygments theme name.
_THEME_CYCLE = (
    "monokai",
    "dracula",
    "github-dark",
    "solarized-dark",
    "solarized-light",
    "one-dark",
    "native",
)


class SettingsScreen(ModalScreen[None]):
    """Modal for toggling DiffDisplayConfig fields at runtime."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-container {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }

    #settings-title {
        text-align: center;
        margin-bottom: 1;
    }

    #settings-body {
        height: auto;
    }

    #settings-dismiss {
        text-align: center;
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("w", "toggle_wrap", "Wrap mode", show=False),
        Binding("s", "toggle_syntax", "Syntax highlight", show=False),
        Binding("n", "toggle_numbers", "Line numbers", show=False),
        Binding("t", "cycle_theme", "Theme", show=False),
        Binding("comma,escape,enter,q", "dismiss_settings", "Close", show=False),
    ]

    def __init__(self, diff_cfg: DiffDisplayConfig) -> None:
        super().__init__()
        self.diff_cfg = diff_cfg

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Static("[bold]Settings[/bold]", id="settings-title")
            yield Static(self._body_text(), id="settings-body")
            yield Static(
                "[dim]Press , / Esc / Enter to close[/dim]",
                id="settings-dismiss",
            )

    def _body_text(self) -> str:
        cfg = self.diff_cfg
        syn = _onoff(cfg.syntax_highlight)
        nums = _onoff(cfg.show_line_numbers)
        lines = [
            "[bold cyan]Diff display[/bold cyan]",
            f"  [bold]w[/bold]  Wrap mode          [yellow]{cfg.wrap_mode}[/yellow]",
            f"  [bold]s[/bold]  Syntax highlight   [yellow]{syn}[/yellow]",
            f"  [bold]n[/bold]  Line numbers       [yellow]{nums}[/yellow]",
            f"  [bold]t[/bold]  Theme              [yellow]{cfg.theme}[/yellow]",
        ]
        return "\n".join(lines)

    def _refresh_body(self) -> None:
        self.query_one("#settings-body", Static).update(self._body_text())

    def _persist(self, key: str, value: object) -> None:
        """Write through to the persistent config file; swallow write errors."""
        try:
            update_setting(key, str(value).lower() if isinstance(value, bool) else str(value))
        except (OSError, ValueError):
            # Non-fatal: in-memory change still applies for this session.
            pass

    def action_toggle_wrap(self) -> None:
        self.diff_cfg.wrap_mode = (
            "scroll" if self.diff_cfg.wrap_mode == "wrap" else "wrap"
        )
        self._persist("diff.wrap_mode", self.diff_cfg.wrap_mode)
        self._refresh_body()

    def action_toggle_syntax(self) -> None:
        self.diff_cfg.syntax_highlight = not self.diff_cfg.syntax_highlight
        self._persist("diff.syntax_highlight", self.diff_cfg.syntax_highlight)
        self._refresh_body()

    def action_toggle_numbers(self) -> None:
        self.diff_cfg.show_line_numbers = not self.diff_cfg.show_line_numbers
        self._persist("diff.show_line_numbers", self.diff_cfg.show_line_numbers)
        self._refresh_body()

    def action_cycle_theme(self) -> None:
        try:
            i = _THEME_CYCLE.index(self.diff_cfg.theme)
        except ValueError:
            i = -1
        self.diff_cfg.theme = _THEME_CYCLE[(i + 1) % len(_THEME_CYCLE)]
        self._persist("diff.theme", self.diff_cfg.theme)
        self._refresh_body()

    def action_dismiss_settings(self) -> None:
        self.dismiss(None)


def _onoff(value: bool) -> str:
    return "on" if value else "off"
