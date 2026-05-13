"""Main walkthrough screen — simplified paginated layout."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Static

from unravel.tui.gh_client import GhCliError, build_snapshot, post_issue_comment, submit_review
from unravel.tui.review_state import (
    PendingReviewComment,
    PrSnapshot,
    SubmitAction,
    Verdict,
)
from unravel.tui.review_storage import (
    discard_pending,
    load_pending,
    save_pending,
)
from unravel.tui.state import WalkthroughState
from unravel.tui.viewed_storage import load_viewed, save_viewed
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
        overflow-y: auto;
        overflow-x: hidden;
    }

    #page-scroll.scroll-mode {
        overflow-x: auto;
    }

    #page-content {
        width: 100%;
        height: auto;
    }

    #page-scroll.scroll-mode #page-content {
        width: auto;
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
        Binding("comma", "show_settings", "Settings", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("q", "quit_app", "Quit", show=False),
        Binding("v", "toggle_viewed", "Toggle viewed", show=False),
        # ---- Review (PRs only) ----
        Binding("n", "new_inline_comment", "New inline comment", show=False),
        Binding("a", "new_pr_comment", "New PR-level comment", show=False),
        Binding("R", "refresh_pr", "Refresh PR data", show=False),
        Binding("S", "submit_review", "Submit review", show=False),
    ]

    def __init__(self, state: WalkthroughState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Timeline(id="timeline")
        with ScrollableContainer(id="page-scroll"):
            yield Static(id="page-content")
        yield FooterBar(id="footer")

    def on_mount(self) -> None:
        self._apply_wrap_mode()
        self._restore_pending_review()
        self._restore_viewed()
        self._refresh_all()
        if self.state.pr_ctx is not None:
            self.run_worker(self._load_snapshot, thread=True, name="pr-snapshot")

    def _restore_viewed(self) -> None:
        """Re-hydrate viewed-hunk marks for the current source from disk."""
        restored = load_viewed(self.state.source_info, self.state.pr_ctx)
        if restored:
            self.state.viewed_content_hashes = restored

    def _persist_viewed(self) -> None:
        save_viewed(
            self.state.source_info,
            self.state.viewed_content_hashes,
            self.state.pr_ctx,
        )

    def _restore_pending_review(self) -> None:
        """Re-hydrate pending review from disk for the current PR, if any."""
        ctx = self.state.pr_ctx
        if ctx is None:
            return
        restored = load_pending(ctx)
        if restored and restored.comments:
            self.state.pending_review = restored
            count = len(restored.comments)
            plural = "s" if count != 1 else ""
            self.notify(
                f"Restored {count} pending comment{plural} from previous session.",
                severity="information",
            )

    def _persist_pending(self) -> None:
        """Write the in-memory pending review back to disk (idempotent)."""
        ctx = self.state.pr_ctx
        if ctx is None:
            return
        save_pending(ctx, self.state.pending_review)

    def _apply_wrap_mode(self) -> None:
        """Toggle the ``scroll-mode`` CSS class based on the current setting."""
        scroller = self.query_one("#page-scroll", ScrollableContainer)
        scroller.set_class(self.state.diff_cfg.wrap_mode == "scroll", "scroll-mode")

    def _refresh_all(self, scroll_home: bool = False) -> None:
        self.query_one(Timeline).update_state(self.state)
        self.query_one("#page-content", Static).update(render_page(self.state))
        self.query_one(FooterBar).update_state(self.state)
        if scroll_home:
            self.query_one(
                "#page-scroll", ScrollableContainer
            ).scroll_home(animate=False)

    # ---------- Existing navigation ----------

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

    def action_toggle_viewed(self) -> None:
        """v: mark/unmark the currently focused hunk as viewed.

        Marking auto-collapses the hunk if expanded (mirroring the GitHub
        "Viewed" affordance). Unmarking does not change expand state. The
        viewed set is keyed on stable ``content_hash`` so a re-run on a
        rebased PR keeps marks for unchanged hunks.
        """
        if self.state.is_overview:
            return
        hunk = self.state.current_hunk()
        if hunk is None or not hunk.content_hash:
            self.notify(
                "This hunk has no stable identity yet — re-run unravel to enable viewed tracking.",
                severity="warning",
            )
            return
        now_viewed = self.state.toggle_viewed(hunk.content_hash)
        if now_viewed and self.state.is_expanded(
            self.state.page_index, self.state.row_index
        ):
            self.state.toggle_expand()
        self._persist_viewed()
        self._refresh_all()

    def action_show_settings(self) -> None:
        from unravel.tui.screens.settings import SettingsScreen

        def on_close(_result: object | None) -> None:
            self._apply_wrap_mode()
            self._refresh_all()

        self.app.push_screen(SettingsScreen(self.state.diff_cfg), on_close)

    def action_show_help(self) -> None:
        from unravel.tui.screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_quit_app(self) -> None:
        if not self.state.pending_review.comments:
            self.app.exit()
            return
        from unravel.tui.screens.quit_confirm import QuitConfirmScreen

        def _on(decision: str | None) -> None:
            if decision is None:
                # Esc / Back — stay in the TUI; on-disk pending already in sync.
                return
            if decision == "save":
                # Per-mutation save means the file is already up-to-date; just
                # exit. Re-save defensively in case any unexpected drift.
                self._persist_pending()
                self.app.exit()
                return
            if decision == "discard":
                if self.state.pr_ctx is not None:
                    discard_pending(self.state.pr_ctx)
                self.state.pending_review.clear()
                self.app.exit()
                return
            if decision == "submit":
                self.action_submit_review()
                return

        self.app.push_screen(
            QuitConfirmScreen(len(self.state.pending_review.comments)),
            _on,
        )

    # ---------- Review actions ----------

    def action_refresh_pr(self) -> None:
        if not self._require_pr_ctx():
            return
        self.notify("Refreshing PR data…", severity="information")
        self.run_worker(self._load_snapshot, thread=True, name="pr-snapshot")

    def action_new_pr_comment(self) -> None:
        if not self._require_pr_ctx():
            return
        from unravel.tui.screens.composer import ComposerScreen

        def _on_body(body: str | None) -> None:
            if not body:
                return
            self.run_worker(
                lambda: self._post_pr_comment(body),
                thread=True,
                name="post-issue-comment",
            )

        self.app.push_screen(
            ComposerScreen(title="New PR-level comment"), _on_body
        )

    def action_new_inline_comment(self) -> None:
        if not self._require_pr_ctx():
            return
        if self.state.is_overview:
            self.notify("Open a thread first.", severity="warning")
            return
        if not self.state.is_expanded(self.state.page_index, self.state.row_index):
            self.notify("Expand the hunk first (Enter).", severity="warning")
            return
        hunk = self.state.current_hunk()
        if hunk is None or not hunk.content or hunk.content == "[binary file]":
            self.notify("This hunk has no addressable lines.", severity="warning")
            return

        from unravel.tui.screens.line_comment import LineRangeScreen

        def _on_result(comment: PendingReviewComment | None) -> None:
            if comment is None:
                return
            self.state.pending_review.comments.append(comment)
            self._persist_pending()
            self.notify(
                f"Added pending comment on {comment.path}:{comment.line}",
                severity="information",
            )
            self._refresh_all()

        self.app.push_screen(LineRangeScreen(hunk), _on_result)

    def action_submit_review(self) -> None:
        if not self._require_pr_ctx():
            return
        if self.state.pr_ctx and self.state.pr_ctx.head_sha is None:
            self.notify(
                "Missing head_sha in walkthrough metadata — cannot anchor review.",
                severity="error",
            )
            return

        from unravel.tui.screens.submit_review import SubmitReviewScreen

        snap = self.state.pr_snapshot
        # Approve / Request changes are nonsensical on closed/merged/draft PRs
        # (GitHub's UI hides them too). The plain "Comment" path still posts as
        # a review summary — same dialog, fewer buttons.
        hide_verdicts = bool(snap and snap.state in ("merged", "closed", "draft"))

        def _on_result(decision: tuple[SubmitAction, str] | None) -> None:
            if decision is None:
                return
            action, summary = decision
            if action == "DISCARD":
                self.state.pending_review.clear()
                if self.state.pr_ctx is not None:
                    discard_pending(self.state.pr_ctx)
                self.notify("Pending review discarded.", severity="information")
                self._refresh_all()
                return
            self.run_worker(
                lambda verdict=action: self._submit_review(verdict, summary),
                thread=True,
                name="submit-review",
            )

        assert self.state.pr_ctx is not None
        self.app.push_screen(
            SubmitReviewScreen(
                self.state.pending_review,
                self.state.pr_ctx,
                merged_or_closed=hide_verdicts,
            ),
            _on_result,
        )

    # ---------- Helpers / workers ----------

    def _require_pr_ctx(self) -> bool:
        if self.state.pr_ctx is None:
            self.notify(
                "PR context unavailable — open via `unravel pr` to enable review.",
                severity="warning",
            )
            return False
        return True

    def _load_snapshot(self) -> None:
        """Worker thread: fetch PR snapshot and apply it on the UI thread."""
        ctx = self.state.pr_ctx
        if ctx is None:
            return
        try:
            snap = build_snapshot(ctx.repo_nwo, ctx.pr_number)
        except GhCliError as exc:
            self.app.call_from_thread(self._on_snapshot_error, str(exc))
            return
        self.app.call_from_thread(self._on_snapshot_loaded, snap)

    def _on_snapshot_loaded(self, snap: PrSnapshot) -> None:
        self.state.pr_snapshot = snap
        self.state.pr_snapshot_error = None
        # If the walkthrough metadata didn't carry head_sha, backfill it.
        if self.state.pr_ctx and self.state.pr_ctx.head_sha is None and snap.head_sha:
            from dataclasses import replace

            self.state.pr_ctx = replace(self.state.pr_ctx, head_sha=snap.head_sha)
        self._refresh_all()

    def _on_snapshot_error(self, msg: str) -> None:
        self.state.pr_snapshot_error = msg
        self.notify(f"Could not load PR data: {msg}", severity="error")
        self._refresh_all()

    def _post_pr_comment(self, body: str) -> None:
        ctx = self.state.pr_ctx
        if ctx is None:
            return
        try:
            post_issue_comment(ctx.repo_nwo, ctx.pr_number, body)
        except GhCliError as exc:
            self.app.call_from_thread(
                self.notify, f"gh: {exc}", severity="error"
            )
            return
        self.app.call_from_thread(
            self.notify, "Comment posted.", severity="information"
        )
        # Re-fetch so the new comment shows up in the drawer.
        self.run_worker(self._load_snapshot, thread=True, name="pr-snapshot")

    def _submit_review(self, verdict: Verdict, summary: str) -> None:
        ctx = self.state.pr_ctx
        if ctx is None or ctx.head_sha is None:
            return
        from unravel.tui.review_state import build_review_payload

        self.state.pending_review.summary = summary
        payload = build_review_payload(
            self.state.pending_review, verdict, ctx.head_sha
        )
        try:
            submit_review(ctx.repo_nwo, ctx.pr_number, payload)
        except GhCliError as exc:
            self.app.call_from_thread(
                self.notify, f"Submit failed: {exc}", severity="error"
            )
            return
        self.app.call_from_thread(self._after_review_submitted)

    def _after_review_submitted(self) -> None:
        self.state.pending_review.clear()
        if self.state.pr_ctx is not None:
            discard_pending(self.state.pr_ctx)
        self.notify("Review submitted ✓", severity="information")
        self._refresh_all()
        self.run_worker(self._load_snapshot, thread=True, name="pr-snapshot")
