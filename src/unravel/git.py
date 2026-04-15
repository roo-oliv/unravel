"""Git diff extraction and parsing."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import PurePosixPath

from unidiff import PatchSet

from unravel.models import EXTENSION_LANGUAGES, Hunk


class UnravelGitError(Exception):
    """Raised when a git operation fails."""


def _run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=check,
        )
    except FileNotFoundError as exc:
        raise UnravelGitError(f"Command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        raise UnravelGitError(f"{args[0]} failed: {stderr}") from exc


def get_diff_from_range(range_spec: str, *, staged: bool = False) -> str:
    args = ["git", "diff"]
    if staged:
        args.append("--staged")
    args.append(range_spec)
    result = _run_git(args)
    if not result.stdout.strip():
        raise UnravelGitError(f"No diff output for range: {range_spec}")
    return result.stdout


def get_diff_from_pr(pr_number: int, *, remote: str = "origin") -> str:
    if not shutil.which("gh"):
        raise UnravelGitError(
            "GitHub CLI (gh) is required for PR diffs. Install it from https://cli.github.com"
        )
    result = _run_git(["gh", "pr", "diff", str(pr_number), "--repo", _get_remote_url(remote)])
    if not result.stdout.strip():
        raise UnravelGitError(f"No diff output for PR #{pr_number}")
    return result.stdout


def get_pr_metadata(pr_number: int, *, remote: str = "origin") -> dict:
    if not shutil.which("gh"):
        raise UnravelGitError(
            "GitHub CLI (gh) is required for PR metadata. Install it from https://cli.github.com"
        )
    result = _run_git([
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--repo",
        _get_remote_url(remote),
        "--json",
        "title,author,headRefName,baseRefName,body",
    ])
    import json

    return json.loads(result.stdout)


def _get_remote_url(remote: str) -> str:
    result = _run_git(["git", "remote", "get-url", remote])
    return result.stdout.strip()


def infer_language(file_path: str) -> str | None:
    suffix = PurePosixPath(file_path).suffix.lower()
    return EXTENSION_LANGUAGES.get(suffix)


def parse_diff(raw_diff: str) -> list[Hunk]:
    patch = PatchSet(raw_diff)
    hunks: list[Hunk] = []
    for patched_file in patch:
        file_path = patched_file.path
        language = infer_language(file_path)
        if patched_file.is_binary_file:
            hunks.append(
                Hunk(
                    file_path=file_path,
                    old_start=0,
                    old_count=0,
                    new_start=0,
                    new_count=0,
                    content="[binary file]",
                    language=language,
                )
            )
            continue
        for hunk in patched_file:
            content_lines: list[str] = []
            for line in hunk:
                content_lines.append(str(line))
            hunks.append(
                Hunk(
                    file_path=file_path,
                    old_start=hunk.source_start,
                    old_count=hunk.source_length,
                    new_start=hunk.target_start,
                    new_count=hunk.target_length,
                    content="".join(content_lines),
                    language=language,
                )
            )
    for i, hunk in enumerate(hunks, 1):
        hunk.id = f"H{i}"
    return hunks
