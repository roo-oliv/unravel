"""Final review submission: list pending comments + summary + verdict."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

from unravel.tui.review_state import (
    PendingReview,
    PrContext,
    SubmitAction,
    Verdict,
    build_review_payload,
)


class SubmitReviewScreen(ModalScreen[tuple[SubmitAction, str] | None]):
    """Show pending review and dismiss with (action, summary).

    The dialog is button-driven: Tab/Shift-Tab cycles focus, Enter activates
    the focused button, mouse clicks work too. There are no letter shortcuts
    on purpose — the TextArea swallows them, so keystroke binds would just
    silently no-op.

    Actions:

    - ``APPROVE`` / ``COMMENT`` / ``REQUEST_CHANGES`` — submit to GitHub.
    - ``DISCARD`` — drop pending review without submitting (no confirmation;
      the user already chose to open the dialog and explicitly clicked
      Discard, so a second prompt would be friction).
    """

    DEFAULT_CSS = """
    SubmitReviewScreen {
        align: center middle;
    }
    #submit-box {
        width: 90%;
        max-width: 110;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #submit-title { height: 1; }
    #submit-comments-panel {
        height: 1fr;
        border: round $primary-darken-2;
        padding: 0 1;
    }
    #submit-summary {
        height: 8;
        border: round $primary-darken-2;
    }
    #submit-buttons {
        height: 3;
        align: center middle;
    }
    Button { margin: 0 1; min-width: 16; }
    #submit-hint {
        height: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("left,up", "focus_prev", "Previous option", show=False),
        Binding("right,down", "focus_next", "Next option", show=False),
    ]

    def __init__(
        self,
        pending: PendingReview,
        pr_ctx: PrContext,
        merged_or_closed: bool = False,
    ) -> None:
        super().__init__()
        self._pending = pending
        self._pr_ctx = pr_ctx
        self._merged_or_closed = merged_or_closed

    def compose(self) -> ComposeResult:
        with Vertical(id="submit-box"):
            yield Static(self._title_text(), id="submit-title")
            yield Static(self._render_comments(), id="submit-comments-panel")
            yield TextArea(self._pending.summary, id="submit-summary")
            with Horizontal(id="submit-buttons"):
                if not self._merged_or_closed:
                    yield Button("Approve", variant="success", id="btn-approve")
                yield Button("Comment", variant="default", id="btn-comment")
                if not self._merged_or_closed:
                    yield Button(
                        "Request changes", variant="error", id="btn-request"
                    )
                if self._pending.comments:
                    yield Button("Discard", variant="warning", id="btn-discard")
            yield Static(
                "[Shift+]Tab to switch selection · Enter or Mouse click to "
                "confirm · Esc to cancel",
                id="submit-hint",
            )

    def on_mount(self) -> None:
        # Focus the first (left-most) button rather than the TextArea so
        # the user can Tab through the action options immediately. They can
        # still Shift+Tab to reach the summary box to type before submitting.
        first_btn = self.query("Button").first()
        if first_btn is not None:
            first_btn.focus()

    def _title_text(self) -> Text:
        t = Text()
        t.append("Submit review  ", style="bold")
        t.append(self._pr_ctx.repo_nwo, style="dim")
        t.append(f"  #{self._pr_ctx.pr_number}", style="bold cyan")
        return t

    def _render_comments(self) -> Panel:
        if not self._pending.comments:
            return Panel(
                Text("(no inline comments — review summary only)", style="dim italic"),
                border_style="dim",
                title="Inline comments",
            )

        rows: list[Text] = []
        for i, c in enumerate(self._pending.comments, 1):
            row = Text()
            row.append(f"  {i}. ", style="bold")
            row.append(c.path, style="yellow")
            if c.start_line and c.start_line != c.line:
                row.append(f":{c.start_line}-{c.line}", style="yellow")
            else:
                row.append(f":{c.line}", style="yellow")
            row.append(f"  [{c.side}]", style="dim")
            row.append("\n     ")
            first_line = c.body.strip().splitlines()[0] if c.body.strip() else "(empty)"
            row.append(first_line[:80], style="italic")
            rows.append(row)
        return Panel(
            Group(*rows), border_style="dim", title="Inline comments"
        )

    # ---- Actions ----

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping: dict[str, SubmitAction] = {
            "btn-approve": "APPROVE",
            "btn-comment": "COMMENT",
            "btn-request": "REQUEST_CHANGES",
            "btn-discard": "DISCARD",
        }
        action = mapping.get(event.button.id or "")
        if action is None:
            return
        if action == "DISCARD":
            self.dismiss(("DISCARD", ""))
            return
        summary = self.query_one("#submit-summary", TextArea).text
        # GitHub's REST API rejects REQUEST_CHANGES / COMMENT when both the
        # body and inline-comments list are empty (APPROVE alone is fine).
        if (
            action in ("REQUEST_CHANGES", "COMMENT")
            and not summary.strip()
            and not self._pending.comments
        ):
            self.notify("Add a summary or inline comment first.", severity="warning")
            return
        self.dismiss((action, summary))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_prev(self) -> None:
        self.focus_previous()

    def action_focus_next(self) -> None:
        self.focus_next()


def build_payload_for_submit(
    pending: PendingReview, verdict: Verdict, summary: str, head_sha: str
) -> dict:
    """Convenience: stamp the (possibly edited) summary onto the payload."""
    pending.summary = summary
    return build_review_payload(pending, verdict, head_sha)
