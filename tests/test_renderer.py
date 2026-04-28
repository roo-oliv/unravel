"""Tests for markdown and GitHub comment rendering."""

from __future__ import annotations

import base64
import json

from unravel.models import Hunk, Walkthrough
from unravel.renderer import (
    COMMENT_MARKER_DATA_PREFIX,
    COMMENT_MARKER_END,
    COMMENT_MARKER_SHA_PREFIX,
    COMMENT_MARKER_START,
    COMMENT_MARKER_STATUS_PREFIX,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    UNRAVEL_INSTALL_URL,
    _format_hunk_ref,
    _github_diff_anchor,
    _hunk_line_range,
    _pr_cli_ref,
    render_github_comment,
    render_github_comment_failed,
    render_github_comment_placeholder,
    render_markdown,
)

FAKE_SHA = "a" * 40
OTHER_SHA = "b" * 40


def test_render_markdown_structure(sample_walkthrough: Walkthrough) -> None:
    md = render_markdown(sample_walkthrough)

    assert "2 threads across" in md
    assert "### Replace silent auth failures" in md
    assert "### Update middleware" in md
    assert "`auth-error-handling`" in md
    assert "**Root cause:**" in md
    assert "**Step 1:**" in md
    assert "**Suggested review order:**" in md
    assert "\u2192" in md  # arrow between suggested order items


def test_render_markdown_dependencies(sample_walkthrough: Walkthrough) -> None:
    md = render_markdown(sample_walkthrough)

    assert "*Depends on: auth-error-handling*" in md


def test_render_markdown_overview(sample_walkthrough: Walkthrough) -> None:
    md = render_markdown(sample_walkthrough)

    assert "auth error handling" in md


def test_render_github_comment_markers(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)

    assert comment.startswith(COMMENT_MARKER_START)
    assert COMMENT_MARKER_END in comment
    assert COMMENT_MARKER_DATA_PREFIX in comment


def test_render_github_comment_sha_and_status(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)

    assert f"{COMMENT_MARKER_SHA_PREFIX}{FAKE_SHA} -->" in comment
    assert f"{COMMENT_MARKER_STATUS_PREFIX}{STATUS_DONE} -->" in comment


def test_render_github_comment_cta(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(
        sample_walkthrough, head_sha=FAKE_SHA, pr_number=42, repo_nwo="acme/repo"
    )
    assert "Review locally with `unravel pr acme/repo#42`" in comment


def test_render_github_comment_cta_no_repo(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA, pr_number=7)
    assert "Review locally with `unravel pr 7`" in comment


def test_render_github_comment_disclaimer(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)
    assert f"[install and run unravel locally]({UNRAVEL_INSTALL_URL})" in comment


def test_render_github_comment_collapsible(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)

    assert "<details>" in comment
    assert "<summary>Click to expand walkthrough</summary>" in comment
    assert "</details>" in comment


def test_render_github_comment_header(sample_walkthrough: Walkthrough) -> None:
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)

    assert "### Changes unravelled in 2 threads across" in comment


def test_render_github_comment_roundtrip(sample_walkthrough: Walkthrough) -> None:
    """The base64 payload in the comment should decode back to the walkthrough."""
    comment = render_github_comment(sample_walkthrough, head_sha=FAKE_SHA)

    for line in comment.splitlines():
        stripped = line.strip()
        if stripped.startswith(COMMENT_MARKER_DATA_PREFIX):
            payload = stripped[len(COMMENT_MARKER_DATA_PREFIX):]
            payload = payload.removesuffix("-->").rstrip()
            decoded = base64.b64decode(payload).decode("utf-8")
            data = json.loads(decoded)
            restored = Walkthrough.from_dict(data)
            assert len(restored.threads) == len(sample_walkthrough.threads)
            assert restored.overview == sample_walkthrough.overview
            assert restored.suggested_order == sample_walkthrough.suggested_order
            for orig, rest in zip(
                sample_walkthrough.threads, restored.threads, strict=True
            ):
                assert orig.id == rest.id
                assert orig.title == rest.title
            return

    raise AssertionError("No data marker found in comment")  # pragma: no cover


def test_render_github_comment_placeholder_envelope() -> None:
    body = render_github_comment_placeholder(
        head_sha=FAKE_SHA, pr_number=12, repo_nwo="acme/repo"
    )
    assert body.startswith(COMMENT_MARKER_START)
    assert COMMENT_MARKER_END in body
    assert f"{COMMENT_MARKER_SHA_PREFIX}{FAKE_SHA} -->" in body
    assert f"{COMMENT_MARKER_STATUS_PREFIX}{STATUS_IN_PROGRESS} -->" in body
    assert COMMENT_MARKER_DATA_PREFIX not in body
    assert "unravel pr acme/repo#12" in body


def test_render_github_comment_failed() -> None:
    body = render_github_comment_failed(head_sha=FAKE_SHA)
    assert body.startswith(COMMENT_MARKER_START)
    assert f"{COMMENT_MARKER_STATUS_PREFIX}failed -->" in body
    assert "Unravel failed" in body


def test_render_markdown_single_thread() -> None:
    wt = Walkthrough.from_dict({
        "overview": "Single thread change.",
        "suggested_order": ["only-thread"],
        "threads": [
            {
                "id": "only-thread",
                "title": "The Only Thread",
                "summary": "Does one thing.",
                "root_cause": "Needed it.",
                "steps": [
                    {"order": 1, "narration": "Do the thing.", "hunks": ["H1"]},
                ],
            }
        ],
    })
    md = render_markdown(wt)

    assert "1 thread across" in md
    assert "The Only Thread" in md
    assert "`only-thread`" in md


# --- Line range and GitHub diff link tests ---


def test_hunk_line_range_new_side() -> None:
    hunk = Hunk(file_path="a.py", new_start=10, new_count=5)
    assert _hunk_line_range(hunk) == "L10\u201314"


def test_hunk_line_range_single_line() -> None:
    hunk = Hunk(file_path="a.py", new_start=42, new_count=1)
    assert _hunk_line_range(hunk) == "L42"


def test_hunk_line_range_old_fallback() -> None:
    hunk = Hunk(file_path="a.py", old_start=5, old_count=3, new_start=0, new_count=0)
    assert _hunk_line_range(hunk) == "L5\u20137"


def test_hunk_line_range_empty() -> None:
    hunk = Hunk(file_path="a.py")
    assert _hunk_line_range(hunk) == ""


def test_github_diff_anchor() -> None:
    hunk = Hunk(file_path="src/unravel/cli.py", new_start=480, new_count=13)
    anchor = _github_diff_anchor(hunk)
    assert anchor is not None
    assert anchor.startswith("diff-")
    assert anchor.endswith("R480-R492")


def test_github_diff_anchor_old_only() -> None:
    hunk = Hunk(file_path="deleted.py", old_start=1, old_count=10, new_start=0, new_count=0)
    anchor = _github_diff_anchor(hunk)
    assert anchor is not None
    assert "L1-L10" in anchor


def test_format_hunk_ref_no_link() -> None:
    hunk = Hunk(file_path="foo.py", new_start=10, new_count=5)
    ref = _format_hunk_ref(hunk, pr_files_url=None)
    assert ref == "- `foo.py:L10\u201314`"


def test_format_hunk_ref_with_link() -> None:
    hunk = Hunk(file_path="foo.py", new_start=10, new_count=5)
    ref = _format_hunk_ref(hunk, pr_files_url="https://github.com/owner/repo/pull/1/files")
    assert ref is not None
    assert "[`foo.py:L10\u201314`]" in ref
    assert "https://github.com/owner/repo/pull/1/files#diff-" in ref
    assert "R10-R14" in ref


def test_format_hunk_ref_no_file_path() -> None:
    hunk = Hunk()
    assert _format_hunk_ref(hunk, pr_files_url=None) is None


def test_render_markdown_with_pr_links(sample_walkthrough: Walkthrough, simple_diff: str) -> None:
    """When pr_files_url is set, hunk refs become clickable links."""
    from unravel.git import parse_diff
    from unravel.hydration import hydrate_walkthrough

    hunks = parse_diff(simple_diff)
    wt, _ = hydrate_walkthrough(sample_walkthrough, hunks)
    md = render_markdown(wt, pr_files_url="https://github.com/test/repo/pull/1/files")

    assert "https://github.com/test/repo/pull/1/files#diff-" in md
    assert ":L" in md  # line range in the label


# --- PR CLI ref tests ---


def test_pr_cli_ref_with_repo() -> None:
    assert _pr_cli_ref(42, "acme/repo") == "unravel pr acme/repo#42"


def test_pr_cli_ref_number_only() -> None:
    assert _pr_cli_ref(42, None) == "unravel pr 42"


def test_pr_cli_ref_no_number() -> None:
    assert _pr_cli_ref(None, None) == "unravel pr <number>"
