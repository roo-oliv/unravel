"""Tests for narration text highlighting."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from unravel.config import DiffDisplayConfig
from unravel.models import Hunk
from unravel.tui.widgets.page_content import (
    _ADD_BG,
    _DEL_BG,
    _render_hunk_diff,
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
