"""Tests for TUI state machine."""

from __future__ import annotations

from unravel.models import Hunk, Thread, ThreadStep, Walkthrough
from unravel.tui.state import WalkthroughState


def _make_walkthrough(
    n_threads: int = 3, steps_per_thread: int = 2, hunks_per_step: int = 1
) -> Walkthrough:
    threads = []
    for ti in range(n_threads):
        tid = f"thread-{ti}"
        steps = [
            ThreadStep(
                hunks=[
                    Hunk(
                        file_path=f"file{ti}_{si}_{hi}.py",
                        new_start=1,
                        new_count=5,
                    )
                    for hi in range(hunks_per_step)
                ],
                narration=f"Step {si} of thread {ti}",
                order=si + 1,
            )
            for si in range(steps_per_thread)
        ]
        threads.append(
            Thread(id=tid, title=f"Thread {ti}", summary="s", root_cause="r", steps=steps)
        )
    return Walkthrough(
        threads=threads,
        overview="test overview",
        suggested_order=[f"thread-{i}" for i in range(n_threads)],
    )


class TestOrderedThreads:
    def test_follows_suggested_order(self):
        wt = _make_walkthrough(3)
        wt.suggested_order = ["thread-2", "thread-0", "thread-1"]
        state = WalkthroughState(wt)
        assert [t.id for t in state.ordered_threads] == [
            "thread-2",
            "thread-0",
            "thread-1",
        ]

    def test_missing_from_order_appended(self):
        wt = _make_walkthrough(3)
        wt.suggested_order = ["thread-1"]
        state = WalkthroughState(wt)
        assert state.ordered_threads[0].id == "thread-1"
        assert len(state.ordered_threads) == 3


class TestPages:
    def test_starts_on_overview(self):
        state = WalkthroughState(_make_walkthrough())
        assert state.is_overview
        assert state.page_index == 0
        assert state.current_thread is None

    def test_page_count(self):
        state = WalkthroughState(_make_walkthrough(3))
        assert state.page_count == 4  # overview + 3 threads

    def test_next_page_from_overview(self):
        state = WalkthroughState(_make_walkthrough())
        assert state.next_page()
        assert state.page_index == 1
        assert not state.is_overview
        assert state.current_thread is not None
        assert state.current_thread.id == "thread-0"

    def test_next_page_at_end(self):
        state = WalkthroughState(_make_walkthrough(2))
        state.next_page()
        state.next_page()
        assert not state.next_page()

    def test_prev_page_at_start(self):
        state = WalkthroughState(_make_walkthrough())
        assert not state.prev_page()

    def test_visited_tracking(self):
        state = WalkthroughState(_make_walkthrough())
        assert 0 in state.visited_pages
        state.next_page()
        assert 1 in state.visited_pages
        state.next_page()
        assert {0, 1, 2} <= state.visited_pages


class TestRows:
    def test_overview_has_no_rows(self):
        state = WalkthroughState(_make_walkthrough())
        assert state.current_rows() == []

    def test_thread_rows_per_hunk(self):
        state = WalkthroughState(_make_walkthrough(2, 2, 3))
        state.next_page()
        rows = state.current_rows()
        assert len(rows) == 6  # 2 steps * 3 hunks

    def test_row_navigation(self):
        state = WalkthroughState(_make_walkthrough(1, 2, 2))
        state.next_page()
        assert state.row_index == 0
        assert state.next_row()
        assert state.row_index == 1
        assert state.next_row()
        assert state.row_index == 2
        assert state.next_row()
        assert state.row_index == 3
        assert not state.next_row()  # at end

    def test_prev_row(self):
        state = WalkthroughState(_make_walkthrough(1, 2, 1))
        state.next_page()
        state.next_row()
        assert state.prev_row()
        assert state.row_index == 0
        assert not state.prev_row()

    def test_row_resets_on_page_change(self):
        state = WalkthroughState(_make_walkthrough(2, 2, 2))
        state.next_page()
        state.next_row()
        state.next_row()
        state.next_page()
        assert state.row_index == 0


class TestExpansion:
    def test_toggle_expand(self):
        state = WalkthroughState(_make_walkthrough())
        state.next_page()
        assert not state.is_expanded(1, 0)
        assert state.toggle_expand()
        assert state.is_expanded(1, 0)
        assert state.toggle_expand()
        assert not state.is_expanded(1, 0)

    def test_toggle_on_overview_noop(self):
        state = WalkthroughState(_make_walkthrough())
        assert not state.toggle_expand()

    def test_expand_all(self):
        state = WalkthroughState(_make_walkthrough(1, 2, 2))
        state.next_page()
        state.expand_all_on_page()
        for i in range(4):
            assert state.is_expanded(1, i)

    def test_collapse_all(self):
        state = WalkthroughState(_make_walkthrough(1, 2, 2))
        state.next_page()
        state.expand_all_on_page()
        state.collapse_all_on_page()
        for i in range(4):
            assert not state.is_expanded(1, i)


class TestStatus:
    def test_page_status_current(self):
        state = WalkthroughState(_make_walkthrough(3))
        assert state.page_status(0) == "current"
        state.next_page()
        assert state.page_status(0) == "completed"
        assert state.page_status(1) == "current"
        assert state.page_status(2) == "unvisited"

    def test_progress(self):
        state = WalkthroughState(_make_walkthrough(3))
        assert state.progress == (0, 3)
        state.next_page()
        assert state.progress == (1, 3)


class TestCurrentHunk:
    def test_current_hunk_on_overview(self):
        state = WalkthroughState(_make_walkthrough())
        assert state.current_hunk() is None

    def test_current_hunk_on_thread(self):
        state = WalkthroughState(_make_walkthrough(1, 1, 1))
        state.next_page()
        hunk = state.current_hunk()
        assert hunk is not None
        assert hunk.file_path == "file0_0_0.py"


class TestFullDiffPage:
    def test_no_full_diff_when_hunks_empty(self):
        state = WalkthroughState(_make_walkthrough(2))
        assert state.page_count == 3  # overview + 2 threads
        assert not state.has_full_diff

    def test_full_diff_appended_when_hunks_provided(self):
        all_hunks = [Hunk(id="H1", file_path="a.py", new_start=1, new_count=3)]
        state = WalkthroughState(_make_walkthrough(2), all_hunks=all_hunks)
        assert state.page_count == 4  # overview + 2 threads + full diff
        assert state.has_full_diff

    def test_full_diff_is_last_page(self):
        all_hunks = [Hunk(id="H1", file_path="a.py", new_start=1, new_count=3)]
        state = WalkthroughState(_make_walkthrough(1), all_hunks=all_hunks)
        state.next_page()  # thread
        state.next_page()  # full diff
        assert state.is_full_diff
        assert state.current_thread is None
        assert state.current_rows() == []
        assert not state.next_page()

    def test_full_diff_disables_toggle_expand(self):
        all_hunks = [Hunk(id="H1", file_path="a.py", new_start=1, new_count=3)]
        state = WalkthroughState(_make_walkthrough(1), all_hunks=all_hunks)
        state.next_page()
        state.next_page()  # on full diff
        assert not state.toggle_expand()
