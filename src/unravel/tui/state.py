"""Navigation state for the TUI walkthrough (page-based)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from unravel.models import Hunk, Thread, ThreadStep, Walkthrough

PageStatus = Literal["completed", "current", "unvisited"]


@dataclass
class Row:
    """A focusable row on a thread page — one hunk reference."""

    step_index: int
    hunk_index: int


@dataclass
class WalkthroughState:
    """Manages page-based navigation through a walkthrough.

    Pages are: [overview, thread_1, thread_2, ..., thread_N, full_diff?].
    Overview is page 0; thread i is page i (1-indexed). The full-diff page
    is the last page when ``all_hunks`` is provided — a ground-truth reference
    showing every parsed hunk, regardless of thread splitting.
    """

    walkthrough: Walkthrough
    all_hunks: list[Hunk] = field(default_factory=list)
    ordered_threads: list[Thread] = field(init=False)

    # Navigation
    page_index: int = 0
    row_index: int = 0

    # Tracking
    visited_pages: set[int] = field(default_factory=set)
    expanded_rows: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        order = self.walkthrough.suggested_order
        by_id = {t.id: t for t in self.walkthrough.threads}
        ordered = [by_id[tid] for tid in order if tid in by_id]
        remaining = [t for t in self.walkthrough.threads if t.id not in set(order)]
        self.ordered_threads = ordered + remaining
        self.visited_pages.add(0)  # overview is visited on start

    # ------- Pages -------

    @property
    def has_full_diff(self) -> bool:
        return bool(self.all_hunks)

    @property
    def page_count(self) -> int:
        extra = 1 if self.has_full_diff else 0
        return 1 + len(self.ordered_threads) + extra

    @property
    def thread_count(self) -> int:
        return len(self.ordered_threads)

    @property
    def is_overview(self) -> bool:
        return self.page_index == 0

    @property
    def is_full_diff(self) -> bool:
        return (
            self.has_full_diff
            and self.page_index == 1 + len(self.ordered_threads)
        )

    @property
    def current_thread(self) -> Thread | None:
        if self.is_overview or self.is_full_diff:
            return None
        return self.ordered_threads[self.page_index - 1]

    @property
    def current_thread_index(self) -> int | None:
        """Thread index (0-based) or None when on overview/full-diff page."""
        if self.is_overview or self.is_full_diff:
            return None
        return self.page_index - 1

    def page_status(self, page_index: int) -> PageStatus:
        if page_index == self.page_index:
            return "current"
        if page_index in self.visited_pages:
            return "completed"
        return "unvisited"

    # ------- Rows -------

    def current_rows(self) -> list[Row]:
        if self.is_overview or self.is_full_diff:
            return []
        thread = self.current_thread
        assert thread is not None
        rows: list[Row] = []
        sorted_steps = sorted(thread.steps, key=lambda s: s.order)
        for si, step in enumerate(sorted_steps):
            for hi in range(len(step.hunks)):
                rows.append(Row(step_index=si, hunk_index=hi))
        return rows

    def current_row(self) -> Row | None:
        rows = self.current_rows()
        if not rows or self.row_index >= len(rows):
            return None
        return rows[self.row_index]

    def current_hunk(self) -> Hunk | None:
        row = self.current_row()
        thread = self.current_thread
        if row is None or thread is None:
            return None
        sorted_steps = sorted(thread.steps, key=lambda s: s.order)
        step = sorted_steps[row.step_index]
        if row.hunk_index >= len(step.hunks):
            return None
        return step.hunks[row.hunk_index]

    def sorted_steps(self, thread: Thread) -> list[ThreadStep]:
        return sorted(thread.steps, key=lambda s: s.order)

    # ------- Navigation -------

    def next_page(self) -> bool:
        if self.page_index < self.page_count - 1:
            self.page_index += 1
            self.row_index = 0
            self.visited_pages.add(self.page_index)
            return True
        return False

    def prev_page(self) -> bool:
        if self.page_index > 0:
            self.page_index -= 1
            self.row_index = 0
            self.visited_pages.add(self.page_index)
            return True
        return False

    def next_row(self) -> bool:
        rows = self.current_rows()
        if self.row_index < len(rows) - 1:
            self.row_index += 1
            return True
        return False

    def prev_row(self) -> bool:
        if self.row_index > 0:
            self.row_index -= 1
            return True
        return False

    # ------- Expansion -------

    def toggle_expand(self) -> bool:
        """Toggle expansion of the current row. Returns True if a row was toggled."""
        if self.is_overview or self.is_full_diff:
            return False
        key = (self.page_index, self.row_index)
        if key in self.expanded_rows:
            self.expanded_rows.remove(key)
        else:
            self.expanded_rows.add(key)
        return True

    def is_expanded(self, page_index: int, row_index: int) -> bool:
        return (page_index, row_index) in self.expanded_rows

    def expand_all_on_page(self) -> None:
        for i in range(len(self.current_rows())):
            self.expanded_rows.add((self.page_index, i))

    def collapse_all_on_page(self) -> None:
        self.expanded_rows = {
            (pi, ri) for (pi, ri) in self.expanded_rows if pi != self.page_index
        }

    # ------- Progress -------

    @property
    def progress(self) -> tuple[int, int]:
        """Returns (current_thread_1based, total_threads), 0 on non-thread pages."""
        if self.is_overview or self.is_full_diff:
            return (0, self.thread_count)
        return (self.page_index, self.thread_count)
