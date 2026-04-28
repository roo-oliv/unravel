"""Tests for narration text highlighting."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from unravel.config import DiffDisplayConfig
from unravel.models import Hunk, Thread, ThreadStep, Walkthrough
from unravel.tui.state import WalkthroughState
from unravel.tui.widgets.page_content import (
    _ADD_BG,
    _DEL_BG,
    _render_full_diff,
    _render_hunk_diff,
    _render_thread_rows,
    _resolve_language,
    styled_text,
)


class TestStyledText:
    def test_plain_text_passthrough(self):
        t = styled_text("just plain narration")
        assert t.plain == "just plain narration"

    def test_inline_code_is_cyan(self):
        t = styled_text("Calls `to_dict` on the model")
        assert t.plain == "Calls to_dict on the model"
        styles = [str(span.style) for span in t.spans]
        assert any("cyan" in s and "bold" in s for s in styles)

    def test_bold_segment(self):
        t = styled_text("This is **important** stuff")
        assert t.plain == "This is important stuff"
        styles = [str(span.style) for span in t.spans]
        assert any(s == "bold" or s.endswith(" bold") for s in styles)

    def test_italic_segment(self):
        t = styled_text("Some *emphasis* here")
        assert t.plain == "Some emphasis here"
        styles = [str(span.style) for span in t.spans]
        assert any("italic" in s for s in styles)

    def test_base_style_applied_to_plain_runs(self):
        t = styled_text("plain `code` plain", base_style="bold")
        # base_style is attached as the segment style when present
        styles = [str(span.style) for span in t.spans]
        assert "bold" in styles  # for the surrounding plain text
        assert any("cyan" in s for s in styles)  # for the code

    def test_filename_with_dunder(self):
        t = styled_text("see `__init__.py` for setup")
        assert "__init__.py" in t.plain
        assert any("cyan" in str(s.style) for s in t.spans)

    def test_no_match_no_spans(self):
        t = styled_text("nothing fancy here")
        assert t.spans == []


class TestAutoDetect:
    def _styled_runs(self, content):
        """Return (text, style_str) tuples for code-styled spans."""
        t = styled_text(content)
        out = []
        for span in t.spans:
            style = str(span.style)
            if "cyan" in style:
                out.append(t.plain[span.start : span.end])
        return out

    def test_snake_case_function_name(self):
        runs = self._styled_runs("calls parse_diff to split hunks")
        assert "parse_diff" in runs

    def test_dunder(self):
        runs = self._styled_runs("the __init__ constructor")
        assert "__init__" in runs

    def test_function_call(self):
        runs = self._styled_runs("invokes analyze() on the provider")
        assert "analyze()" in runs

    def test_dotted_path(self):
        runs = self._styled_runs("reads walkthrough.threads from state")
        assert "walkthrough.threads" in runs

    def test_constant_name(self):
        runs = self._styled_runs("bumped MAX_JSON_RETRIES to 5")
        assert "MAX_JSON_RETRIES" in runs

    def test_filename(self):
        runs = self._styled_runs("update src/unravel/cli.py to add a flag")
        assert any(r.endswith("cli.py") for r in runs)

    def test_does_not_highlight_abbreviations(self):
        # i.e. and e.g. should be ignored (single-char dotted parts)
        runs = self._styled_runs("e.g. some text, i.e. another")
        assert runs == []

    def test_does_not_highlight_plain_words(self):
        runs = self._styled_runs("the function processes requests quickly")
        assert runs == []

    def test_explicit_backticks_still_work_alongside_autodetect(self):
        # Both `foo` (explicit) and bar_baz (auto) get highlighted
        runs = self._styled_runs("uses `foo` together with bar_baz")
        assert "foo" in runs
        assert "bar_baz" in runs


class TestResolveLanguage:
    def test_explicit_language_wins(self):
        h = Hunk(language="rust", file_path="foo.py")
        assert _resolve_language(h) == "rust"

    def test_extension_lookup(self):
        h = Hunk(file_path="src/foo.py")
        assert _resolve_language(h) == "python"

    def test_unknown_extension_falls_back_to_text(self):
        h = Hunk(file_path="unknown.xyz")
        assert _resolve_language(h) == "text"


class TestRenderHunkDiff:
    def _basic_hunk(self, content: str) -> Hunk:
        return Hunk(
            file_path="foo.py",
            old_start=10,
            old_count=2,
            new_start=20,
            new_count=3,
            content=content,
        )

    def test_binary_message(self):
        h = self._basic_hunk("[binary file]")
        result = _render_hunk_diff(h, DiffDisplayConfig())
        assert isinstance(result, Text)
        assert "binary" in result.plain

    def test_empty_message(self):
        h = self._basic_hunk("")
        result = _render_hunk_diff(h, DiffDisplayConfig())
        assert isinstance(result, Text)
        assert "no diff content" in result.plain

    def test_returns_panel_wrapping_table(self):
        h = self._basic_hunk(" context\n+added\n-removed\n")
        result = _render_hunk_diff(h, DiffDisplayConfig())
        assert isinstance(result, Panel)
        assert isinstance(result.renderable, Table)

    def test_row_count_matches_content_lines(self):
        h = self._basic_hunk(" ctx1\n+a\n+b\n-c\n ctx2\n")
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        assert isinstance(table, Table)
        assert table.row_count == 5

    def test_line_numbers_advance_correctly(self):
        # Context increments both, + increments new, - increments old.
        h = Hunk(
            file_path="foo.py",
            old_start=100,
            new_start=200,
            content=" c\n+a\n-d\n c\n",
        )
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        # Table doesn't expose rows directly; inspect per-column cell lists.
        old_cells = [str(c) for c in table.columns[0]._cells]
        new_cells = [str(c) for c in table.columns[1]._cells]
        # Context line 1: both shown (100, 200)
        assert old_cells[0] == "100"
        assert new_cells[0] == "200"
        # +a: only new shown (201), old blank
        assert old_cells[1] == ""
        assert new_cells[1] == "201"
        # -d: only old shown (101), new blank
        assert old_cells[2] == "101"
        assert new_cells[2] == ""
        # Context line 2: both shown (102, 202)
        assert old_cells[3] == "102"
        assert new_cells[3] == "202"

    def test_add_row_has_add_bg_tint(self):
        h = self._basic_hunk("+added\n")
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        # The sign cell carries the tint in its style string.
        sign_cells = list(table.columns[2]._cells)
        style_str = str(sign_cells[0].style)
        assert _ADD_BG in style_str

    def test_del_row_has_del_bg_tint(self):
        h = self._basic_hunk("-gone\n")
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        sign_cells = list(table.columns[2]._cells)
        style_str = str(sign_cells[0].style)
        assert _DEL_BG in style_str

    def test_context_row_has_no_tint(self):
        h = self._basic_hunk(" context\n")
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        sign_cells = list(table.columns[2]._cells)
        style_str = str(sign_cells[0].style)
        assert _ADD_BG not in style_str
        assert _DEL_BG not in style_str

    def test_show_line_numbers_off_hides_number_columns(self):
        h = self._basic_hunk(" ctx\n+added\n")
        cfg = DiffDisplayConfig(show_line_numbers=False)
        panel = _render_hunk_diff(h, cfg)
        table = panel.renderable
        # Only sign + code columns remain.
        assert len(table.columns) == 2

    def test_wrap_mode_scroll_disables_code_wrap(self):
        h = self._basic_hunk(" ctx\n")
        cfg = DiffDisplayConfig(wrap_mode="scroll")
        panel = _render_hunk_diff(h, cfg)
        table = panel.renderable
        code_col = table.columns[-1]
        assert code_col.no_wrap is True

    def test_wrap_mode_wrap_enables_code_wrap(self):
        h = self._basic_hunk(" ctx\n")
        cfg = DiffDisplayConfig(wrap_mode="wrap")
        panel = _render_hunk_diff(h, cfg)
        table = panel.renderable
        code_col = table.columns[-1]
        assert code_col.no_wrap is False

    def test_no_newline_annotation_does_not_advance_counters(self):
        h = Hunk(
            file_path="foo.py",
            old_start=1,
            new_start=1,
            content="+added\n\\ No newline at end of file\n+next\n",
        )
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        new_cells = [str(c) for c in table.columns[1]._cells]
        # First + gets new_no 1, marker row has blank, next + gets new_no 2
        assert new_cells[0] == "1"
        assert new_cells[1] == ""
        assert new_cells[2] == "2"

    def test_syntax_highlight_off_produces_plain_text_on_context_lines(self):
        # On context rows there's no row tint, so a plain Text should have no
        # spans when syntax highlighting is disabled.
        h = Hunk(file_path="foo.py", old_start=1, new_start=1, content=" def f():\n")
        cfg = DiffDisplayConfig(syntax_highlight=False)
        panel = _render_hunk_diff(h, cfg)
        table = panel.renderable
        code_cells = list(table.columns[-1]._cells)
        assert code_cells[0].spans == []

    def test_syntax_highlight_on_produces_token_spans(self):
        # With highlighting on, Python keywords get their own style spans.
        h = Hunk(file_path="foo.py", old_start=1, new_start=1, content=" def f():\n")
        panel = _render_hunk_diff(h, DiffDisplayConfig())
        table = panel.renderable
        code_cells = list(table.columns[-1]._cells)
        assert len(code_cells[0].spans) > 0


class TestRenderThreadRows:
    def _state_with(self, hunks: list[Hunk]) -> WalkthroughState:
        thread = Thread(
            id="t1",
            title="T1",
            summary="s",
            root_cause="r",
            steps=[ThreadStep(hunks=hunks, narration="n", order=1)],
        )
        wt = Walkthrough(
            threads=[thread],
            overview="ov",
            suggested_order=["t1"],
        )
        state = WalkthroughState(walkthrough=wt)
        state.page_index = 1
        return state

    def _texts(self, parts):
        return [p for p in parts if isinstance(p, Text)]

    def test_caption_row_appears_above_hunk(self):
        h = Hunk(
            id="H1",
            file_path="src/foo.py",
            new_start=10,
            new_count=5,
            additions=2,
            deletions=1,
            caption="New imports",
        )
        state = self._state_with([h])
        parts = _render_thread_rows(state, state.ordered_threads[0])
        texts = self._texts(parts)
        # Find the caption row immediately followed by the file row.
        plains = [t.plain for t in texts]
        caption_idx = next(
            i for i, p in enumerate(plains) if p.strip() == "New imports"
        )
        file_idx = next(
            i for i, p in enumerate(plains) if "src/foo.py" in p and "▶" in p
        )
        assert caption_idx == file_idx - 1

    def test_caption_row_omitted_when_empty(self):
        h = Hunk(
            id="H1",
            file_path="src/foo.py",
            new_start=10,
            new_count=5,
            additions=2,
            deletions=1,
            caption="",
        )
        state = self._state_with([h])
        parts = _render_thread_rows(state, state.ordered_threads[0])
        plains = [t.plain for t in self._texts(parts)]
        # No bare caption-style row should sit above the file row.
        file_idx = next(i for i, p in enumerate(plains) if "src/foo.py" in p)
        # The line directly above is either the step line, blank, or another row;
        # it must not be a stray caption-only string.
        above = plains[file_idx - 1]
        assert above.strip() == "" or "Step" in above or "▶" in above

    def test_diff_counter_segments_have_green_red_styles(self):
        h = Hunk(
            id="H1",
            file_path="src/foo.py",
            new_start=10,
            new_count=5,
            additions=4,
            deletions=30,
            caption="Imports update",
        )
        state = self._state_with([h])
        parts = _render_thread_rows(state, state.ordered_threads[0])
        file_text = next(
            t for t in self._texts(parts) if "src/foo.py" in t.plain
        )
        # The plain text contains both segments adjacent: "+4-30".
        assert "+4-30" in file_text.plain
        # Verify color spans cover those segments.
        styles = [str(span.style) for span in file_text.spans]
        assert any(s == "green" for s in styles)
        assert any(s == "red" for s in styles)

    def test_counter_omitted_when_zero(self):
        h = Hunk(
            id="H1",
            file_path="empty.bin",
            new_start=0,
            new_count=0,
            additions=0,
            deletions=0,
            caption="Binary file",
        )
        state = self._state_with([h])
        parts = _render_thread_rows(state, state.ordered_threads[0])
        file_text = next(
            t for t in self._texts(parts) if "empty.bin" in t.plain
        )
        assert "+0" not in file_text.plain
        assert "-0" not in file_text.plain

    def test_caption_rows_do_not_consume_focus_index(self):
        # Two hunks with captions — current_rows() must still return 2 rows
        # (one per hunk), not 4.
        h1 = Hunk(
            id="H1", file_path="a.py", new_start=1, new_count=2,
            additions=1, deletions=0, caption="Cap A",
        )
        h2 = Hunk(
            id="H2", file_path="b.py", new_start=1, new_count=2,
            additions=0, deletions=1, caption="Cap B",
        )
        state = self._state_with([h1, h2])
        rows = state.current_rows()
        assert len(rows) == 2


class TestRenderFullDiff:
    def _state_with(self, parsed: list[Hunk], captions: dict[str, str]) -> WalkthroughState:
        thread = Thread(
            id="t1",
            title="T1",
            summary="s",
            root_cause="r",
            steps=[
                ThreadStep(
                    hunks=[Hunk(id=h.id) for h in parsed],
                    narration="n",
                    order=1,
                )
            ],
        )
        wt = Walkthrough(
            threads=[thread],
            overview="ov",
            suggested_order=["t1"],
            hunk_captions=captions,
        )
        state = WalkthroughState(walkthrough=wt, all_hunks=parsed)
        # Move to the full-diff page (last page).
        state.page_index = state.page_count - 1
        return state

    def _texts_from_group(self, group):
        return [r for r in group.renderables if isinstance(r, Text)]

    def test_full_diff_shows_caption_above_row(self):
        h = Hunk(
            id="H1",
            file_path="src/foo.py",
            new_start=10,
            new_count=5,
            additions=2,
            deletions=1,
            content=" ctx\n+a\n-b\n",
        )
        state = self._state_with([h], {"H1": "New imports"})
        result = _render_full_diff(state)
        plains = [t.plain for t in self._texts_from_group(result)]
        cap_idx = next(i for i, p in enumerate(plains) if p.strip() == "New imports")
        row_idx = next(
            i
            for i, p in enumerate(plains)
            if "H1" in p and ("▶" in p or "▼" in p)
        )
        assert cap_idx == row_idx - 1

    def test_full_diff_shows_diff_counter(self):
        h = Hunk(
            id="H2",
            file_path="src/bar.py",
            new_start=20,
            new_count=3,
            additions=4,
            deletions=30,
            content=" ctx\n",
        )
        state = self._state_with([h], {"H2": "Constants update"})
        result = _render_full_diff(state)
        row_text = next(
            t
            for t in self._texts_from_group(result)
            if "H2" in t.plain and ("▶" in t.plain or "▼" in t.plain)
        )
        assert "+4-30" in row_text.plain
        styles = [str(span.style) for span in row_text.spans]
        assert any(s == "green" for s in styles)
        assert any(s == "red" for s in styles)

    def test_full_diff_omits_counter_when_zero(self):
        h = Hunk(
            id="H3",
            file_path="img.png",
            new_start=0,
            new_count=0,
            additions=0,
            deletions=0,
            content="[binary file]",
        )
        state = self._state_with([h], {"H3": "Binary asset"})
        result = _render_full_diff(state)
        row_text = next(
            t
            for t in self._texts_from_group(result)
            if "H3" in t.plain and ("▶" in t.plain or "▼" in t.plain)
        )
        assert "+0" not in row_text.plain
        assert "-0" not in row_text.plain
