"""Main walkthrough screen — simplified paginated layout."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from unravel.tui.state import WalkthroughState
from unravel.tui.widgets.footer_bar import FooterBar
from unravel.tui.widgets.page_content import render_page
from unravel.tui.widgets.timeline import Timeline


class WalkthroughScreen(Screen):
    DEFAULT_CSS = """
    WalkthroughScreen {
        layout: vertical;
    }

    #page-scroll {
        height: 1fr;
        padding: 1 2;
    }

    #page-content {
        width: 100%;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("right,l", "next_row", "Next row", show=False),
        Binding("left,h", "prev_row", "Previous row", show=False),
        Binding("tab", "next_page", "Next thread", show=False, priority=True),
        Binding(
            "shift+tab", "prev_page", "Previous thread", show=False, priority=True
        ),
        Binding("enter,space", "toggle_expand", "Expand/collapse", show=False),
        Binding("e", "expand_all", "Expand all", show=False),
        Binding("c", "collapse_all", "Collapse all", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("q", "quit_app", "Quit", show=False),
    ]

    def __init__(self, state: WalkthroughState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Timeline(id="timeline")
        with VerticalScroll(id="page-scroll"):
            yield Static(id="page-content")
        yield FooterBar(id="footer")

    def on_mount(self) -> None:
        self._refresh_all()

    def _refresh_all(self, scroll_home: bool = False) -> None:
        self.query_one(Timeline).update_state(self.state)
        self.query_one("#page-content", Static).update(render_page(self.state))
        self.query_one(FooterBar).update_state(self.state)
        if scroll_home:
            self.query_one("#page-scroll", VerticalScroll).scroll_home(
                animate=False
            )

    def action_next_page(self) -> None:
        if self.state.next_page():
            self._refresh_all(scroll_home=True)

    def action_prev_page(self) -> None:
        if self.state.prev_page():
            self._refresh_all(scroll_home=True)

    def action_next_row(self) -> None:
        """→: focus the next row, or advance to the next page at the end."""
        if self.state.next_row():
            self._refresh_all()
            return
        self.action_next_page()

    def action_prev_row(self) -> None:
        """←: focus the previous row, or go to the previous page at the start."""
        if self.state.prev_row():
            self._refresh_all()
            return
        self.action_prev_page()

    def action_toggle_expand(self) -> None:
        if self.state.is_overview:
            # On overview, Enter goes to the first thread
            self.action_next_page()
            return
        if self.state.toggle_expand():
            self._refresh_all()

    def action_expand_all(self) -> None:
        if not self.state.is_overview:
            self.state.expand_all_on_page()
            self._refresh_all()

    def action_collapse_all(self) -> None:
        if not self.state.is_overview:
            self.state.collapse_all_on_page()
            self._refresh_all()

    def action_show_help(self) -> None:
        from unravel.tui.screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_quit_app(self) -> None:
        self.app.exit()
