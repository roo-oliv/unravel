"""Unravel TUI application."""

from __future__ import annotations

from textual.app import App

from unravel.config import DiffDisplayConfig
from unravel.models import Hunk, SourceInfo, Walkthrough
from unravel.tui.screens.walkthrough import WalkthroughScreen
from unravel.tui.state import WalkthroughState


class UnravelApp(App):
    """Interactive paginated walkthrough for Unravel."""

    TITLE = "unravel"

    DEFAULT_CSS = """
    Screen {
        background: $surface;
    }
    """

    def __init__(
        self,
        walkthrough: Walkthrough,
        all_hunks: list[Hunk] | None = None,
        source_info: SourceInfo | None = None,
        diff_cfg: DiffDisplayConfig | None = None,
    ) -> None:
        super().__init__()
        self.walkthrough = walkthrough
        self.state = WalkthroughState(
            walkthrough,
            all_hunks=list(all_hunks) if all_hunks else [],
            source_info=source_info,
            diff_cfg=diff_cfg or DiffDisplayConfig(),
        )

    def on_mount(self) -> None:
        self.push_screen(WalkthroughScreen(self.state))
