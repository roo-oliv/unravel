"""Git diff extraction and parsing."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import PurePosixPath

from unidiff import PatchSet

from unravel.models import EXTENSION_LANGUAGES, Hunk, SourceInfo

# GitHub's commits-list UI truncates subjects at 72 chars (industry-standard
# hard limit for commit subject lines).
COMMIT_SUBJECT_MAX = 72


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


def _resolve_repo(repo: str | None, remote: str) -> str:
    """Return the repo identifier for ``gh --repo``.

    If *repo* is given (e.g. ``owner/repo``), use it directly.
    Otherwise fall back to the URL of the named git remote.
    """
    if repo:
        return repo
    return _get_remote_url(remote)


def get_diff_from_pr(
    pr_number: int, *, remote: str = "origin", repo: str | None = None
) -> str:
    if not shutil.which("gh"):
        raise UnravelGitError(
            "GitHub CLI (gh) is required for PR diffs. Install it from https://cli.github.com"
        )
    result = _run_git([
        "gh", "pr", "diff", str(pr_number), "--repo", _resolve_repo(repo, remote),
    ])
    if not result.stdout.strip():
        raise UnravelGitError(f"No diff output for PR #{pr_number}")
    return result.stdout


def get_pr_metadata(
    pr_number: int, *, remote: str = "origin", repo: str | None = None
) -> dict:
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
        _resolve_repo(repo, remote),
        "--json",
        "title,author,headRefName,baseRefName,body",
    ])
    import json

    return json.loads(result.stdout)


def _get_remote_url(remote: str) -> str:
    result = _run_git(["git", "remote", "get-url", remote])
    return result.stdout.strip()


_REMOTE_NWO_RE = re.compile(
    r"(?:[/:])([^/:]+)/([^/:]+?)(?:\.git)?/?$"
)


def get_repo_nwo(remote: str = "origin", repo: str | None = None) -> str | None:
    """Return the ``owner/repo`` for *repo* or *remote*.

    If *repo* is already in ``owner/repo`` form, return it directly.
    Otherwise resolve the named git remote.
    """
    if repo:
        # Already owner/repo form (e.g. "roo-oliv/unravel")
        if "/" in repo and not repo.startswith(("http", "git@")):
            return repo
        # It's a URL; parse it.
        match = _REMOTE_NWO_RE.search(repo)
        return f"{match.group(1)}/{match.group(2)}" if match else None
    try:
        url = _get_remote_url(remote)
    except UnravelGitError:
        return None
    match = _REMOTE_NWO_RE.search(url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _rev_list_count(range_spec: str) -> int | None:
    """Count commits in ``range_spec`` (e.g. ``A..B``). Returns ``None`` on error."""
    try:
        result = _run_git(["git", "rev-list", "--count", range_spec])
    except UnravelGitError:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _commit_subject(ref: str, max_len: int = COMMIT_SUBJECT_MAX) -> str | None:
    """Return the subject line of ``ref``, truncated to ``max_len`` with ellipsis."""
    try:
        result = _run_git(["git", "log", "-1", "--format=%s", ref])
    except UnravelGitError:
        return None
    subject = result.stdout.strip()
    if not subject:
        return None
    if len(subject) > max_len:
        return subject[: max_len - 1].rstrip() + "…"
    return subject


def _short_sha(ref: str) -> str | None:
    try:
        result = _run_git(["git", "rev-parse", "--short", ref])
    except UnravelGitError:
        return None
    sha = result.stdout.strip()
    return sha or None


def _is_known_branch(name: str) -> bool:
    """Return True if ``name`` resolves to a local or remote-tracking branch."""
    for ref_prefix in ("refs/heads/", "refs/remotes/"):
        try:
            result = _run_git(
                ["git", "show-ref", "--verify", "--quiet", f"{ref_prefix}{name}"],
                check=False,
            )
        except UnravelGitError:
            continue
        if result.returncode == 0:
            return True
    # Also try `<remote>/<name>` shorthand, e.g. "origin/feature".
    if "/" in name:
        try:
            result = _run_git(
                ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{name}"],
                check=False,
            )
        except UnravelGitError:
            return False
        return result.returncode == 0
    return False


def _split_range(range_spec: str) -> tuple[str, str] | None:
    """Split ``A..B`` or ``A...B`` into ``(A, B)``; return ``None`` otherwise."""
    if "..." in range_spec:
        left, _, right = range_spec.partition("...")
        return left, right
    if ".." in range_spec:
        left, _, right = range_spec.partition("..")
        return left, right
    return None


def _commit_phrase(count: int) -> str:
    return f"{count} commit{'s' if count != 1 else ''}"


def build_pr_source_info(
    pr_number: int,
    metadata: dict | None,
    *,
    remote: str = "origin",
    repo: str | None = None,
) -> SourceInfo:
    """Build a SourceInfo for a PR source (number + optional title)."""
    title = None
    if metadata:
        raw_title = metadata.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title.strip()
            if len(title) > COMMIT_SUBJECT_MAX:
                title = title[: COMMIT_SUBJECT_MAX - 1].rstrip() + "…"
    return SourceInfo(
        kind="pr",
        label=f"#{pr_number}",
        repo=get_repo_nwo(remote, repo),
        detail=title,
    )


def build_range_source_info(
    range_spec: str,
    *,
    staged: bool = False,
    remote: str = "origin",
) -> SourceInfo:
    """Inspect ``range_spec`` and classify it as commit / range / branch / staged."""
    repo = get_repo_nwo(remote)
    if staged:
        return SourceInfo(
            kind="staged",
            label="staged changes",
            repo=repo,
            detail=range_spec or None,
        )

    parts = _split_range(range_spec)
    if parts is not None:
        _, right = parts
        count = _rev_list_count(range_spec)
        if count == 1:
            sha = _short_sha(range_spec) or _short_sha(right)
            subject = _commit_subject(range_spec)
            return SourceInfo(
                kind="commit",
                label=sha or range_spec,
                repo=repo,
                detail=subject,
            )
        if count is not None and count > 1 and right and _is_known_branch(right):
            return SourceInfo(
                kind="branch",
                label=right,
                repo=repo,
                detail=_commit_phrase(count),
            )
        if count is not None:
            return SourceInfo(
                kind="range",
                label=range_spec,
                repo=repo,
                detail=_commit_phrase(count),
            )
        return SourceInfo(kind="range", label=range_spec, repo=repo)

    # Single ref (no `..`): branch name, tag, or commit-ish.
    if _is_known_branch(range_spec):
        return SourceInfo(kind="branch", label=range_spec, repo=repo)
    subject = _commit_subject(range_spec)
    sha = _short_sha(range_spec)
    if subject and sha:
        return SourceInfo(kind="commit", label=sha, repo=repo, detail=subject)
    return SourceInfo(kind="range", label=range_spec, repo=repo)


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
            additions = 0
            deletions = 0
            for line in hunk:
                content_lines.append(str(line))
                if line.is_added:
                    additions += 1
                elif line.is_removed:
                    deletions += 1
            hunks.append(
                Hunk(
                    file_path=file_path,
                    old_start=hunk.source_start,
                    old_count=hunk.source_length,
                    new_start=hunk.target_start,
                    new_count=hunk.target_length,
                    content="".join(content_lines),
                    language=language,
                    additions=additions,
                    deletions=deletions,
                )
            )
    for i, hunk in enumerate(hunks, 1):
        hunk.id = f"H{i}"
    return hunks
