"""Tests for git operations."""

from __future__ import annotations

from unravel.git import infer_language, parse_diff


class TestInferLanguage:
    def test_python(self):
        assert infer_language("src/main.py") == "python"

    def test_typescript(self):
        assert infer_language("app/components/Button.tsx") == "tsx"

    def test_go(self):
        assert infer_language("cmd/server/main.go") == "go"

    def test_unknown_extension(self):
        assert infer_language("README") is None

    def test_case_insensitive_extension(self):
        assert infer_language("Makefile.PY") == "python"


class TestParseDiff:
    def test_parse_simple_fixture(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        assert len(hunks) == 3

        auth_hunks = [h for h in hunks if h.file_path == "src/auth.py"]
        assert len(auth_hunks) == 2
        assert auth_hunks[0].language == "python"

        middleware_hunks = [h for h in hunks if h.file_path == "src/middleware.py"]
        assert len(middleware_hunks) == 1
        assert middleware_hunks[0].language == "python"

    def test_hunk_line_numbers(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        first = hunks[0]
        assert first.file_path == "src/auth.py"
        assert first.old_start == 3
        assert first.new_start == 3

    def test_hunk_content_has_diff_markers(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        first = hunks[0]
        assert "+" in first.content or "-" in first.content

    def test_hunks_have_sequential_ids(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        assert [h.id for h in hunks] == [f"H{i + 1}" for i in range(len(hunks))]

    def test_hunks_count_additions_and_deletions(self, simple_diff: str):
        hunks = parse_diff(simple_diff)
        assert (hunks[0].additions, hunks[0].deletions) == (2, 0)
        assert (hunks[1].additions, hunks[1].deletions) == (3, 1)
        assert (hunks[2].additions, hunks[2].deletions) == (9, 4)

    def test_binary_diff(self):
        binary_diff = """\
diff --git a/image.png b/image.png
new file mode 100644
index 0000000..1234567
Binary files /dev/null and b/image.png differ
"""
        hunks = parse_diff(binary_diff)
        assert len(hunks) == 1
        assert hunks[0].content == "[binary file]"
        assert hunks[0].file_path == "image.png"

    def test_empty_diff(self):
        hunks = parse_diff("")
        assert hunks == []
