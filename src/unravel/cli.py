"""Unravel CLI — decompose PR diffs into causal threads."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console

from unravel import __version__, cache, remote_cache
from unravel.config import (
    config_path,
    get_setting,
    load_config,
    render_config_toml,
    update_setting,
)
from unravel.git import (
    UnravelGitError,
    build_pr_source_info,
    build_range_source_info,
    get_diff_from_pr,
    get_diff_from_range,
    get_pr_metadata,
    get_repo_nwo,
    parse_diff,
)
from unravel.hydration import hydrate_walkthrough
from unravel.narrator import validate_walkthrough
from unravel.providers import get_provider
from unravel.renderer import (
    render_github_comment,
    render_json,
    render_markdown,
    render_rich,
    render_tree,
)

app = typer.Typer(
    name="unravel",
    help="AI-powered CLI that decomposes PR diffs into causal threads.",
    no_args_is_help=True,
)
cache_app = typer.Typer(
    name="cache",
    help="Manage the local analysis cache.",
    no_args_is_help=True,
)
app.add_typer(cache_app, name="cache")
conf_app = typer.Typer(
    name="conf",
    help="View and edit persistent Unravel settings.",
    invoke_without_command=True,
)
app.add_typer(conf_app, name="conf")
console = Console(stderr=True)
stdout = Console()


def _version_callback(value: bool) -> None:
    if value:
        stdout.print(f"unravel {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-v", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Unravel — decompose diffs into causal threads for code review."""


@app.command()
def diff(
    range_spec: Annotated[
        str,
        typer.Argument(help="Git diff range (e.g. HEAD~3..HEAD, main..feature)"),
    ],
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="Model to use")
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", "-p", help="LLM provider")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output raw JSON")
    ] = False,
    tree_only: Annotated[
        bool, typer.Option("--tree-only", "-t", help="Compact tree view")
    ] = False,
    markdown_output: Annotated[
        bool, typer.Option("--markdown", help="Output GitHub-flavored markdown")
    ] = False,
    thinking_budget: Annotated[
        int | None,
        typer.Option("--thinking-budget", help="Thinking token budget"),
    ] = None,
    max_output_tokens: Annotated[
        int | None,
        typer.Option("--max-output-tokens", help="Max output tokens"),
    ] = None,
    staged: Annotated[
        bool, typer.Option("--staged", help="Include only staged changes")
    ] = False,
    no_tui: Annotated[
        bool, typer.Option("--no-tui", help="Disable interactive TUI")
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Ignore any cached analysis and re-run the LLM (still saves the new result).",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help="Skip reading and writing the local analysis cache for this run.",
        ),
    ] = False,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key", envvar="UNRAVEL_API_KEY"),
    ] = None,
) -> None:
    """Analyze a git diff range and decompose into causal threads."""
    _run(
        diff_source="range",
        range_spec=range_spec,
        staged=staged,
        model=model,
        provider=provider,
        json_output=json_output,
        tree_only=tree_only,
        markdown_output=markdown_output,
        no_tui=no_tui,
        thinking_budget=thinking_budget,
        max_output_tokens=max_output_tokens,
        fresh=fresh,
        no_cache=no_cache,
        api_key=api_key,
    )


def _parse_pr_ref(ref: str) -> tuple[int, str | None]:
    """Parse ``123``, ``#123``, or ``org/repo#123`` into (number, repo_or_none)."""
    if "#" in ref:
        repo_part, _, num_part = ref.partition("#")
        return int(num_part), repo_part or None
    return int(ref), None


@app.command()
def pr(
    pr_ref: Annotated[
        str,
        typer.Argument(
            help="PR number or org/repo#number (e.g. 42, #42, roo-oliv/unravel#42)",
            metavar="PR",
        ),
    ],
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="Model to use")
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", "-p", help="LLM provider")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output raw JSON")
    ] = False,
    tree_only: Annotated[
        bool, typer.Option("--tree-only", "-t", help="Compact tree view")
    ] = False,
    markdown_output: Annotated[
        bool, typer.Option("--markdown", help="Output GitHub-flavored markdown")
    ] = False,
    github_comment: Annotated[
        bool,
        typer.Option(
            "--github-comment",
            help="Output a full GitHub PR comment body (markdown + hidden JSON cache).",
        ),
    ] = False,
    thinking_budget: Annotated[
        int | None,
        typer.Option("--thinking-budget", help="Thinking token budget"),
    ] = None,
    max_output_tokens: Annotated[
        int | None,
        typer.Option("--max-output-tokens", help="Max output tokens"),
    ] = None,
    remote: Annotated[
        str, typer.Option("--remote", help="Git remote name")
    ] = "origin",
    no_tui: Annotated[
        bool, typer.Option("--no-tui", help="Disable interactive TUI")
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Ignore any cached analysis and re-run the LLM (still saves the new result).",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help="Skip reading and writing the local analysis cache for this run.",
        ),
    ] = False,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key", envvar="UNRAVEL_API_KEY"),
    ] = None,
) -> None:
    """Analyze a GitHub PR and decompose into causal threads."""
    try:
        number, repo = _parse_pr_ref(pr_ref)
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid PR reference: {pr_ref}")
        raise typer.Exit(1)
    _run(
        diff_source="pr",
        pr_number=number,
        repo=repo,
        remote=remote,
        model=model,
        provider=provider,
        json_output=json_output,
        tree_only=tree_only,
        markdown_output=markdown_output,
        github_comment=github_comment,
        no_tui=no_tui,
        thinking_budget=thinking_budget,
        max_output_tokens=max_output_tokens,
        fresh=fresh,
        no_cache=no_cache,
        api_key=api_key,
    )


@cache_app.command("clear")
def cache_clear() -> None:
    """Remove every cached walkthrough from ~/.cache/unravel."""
    count = cache.clear_all()
    if count == 0:
        stdout.print("No cached walkthroughs to remove.")
    else:
        stdout.print(
            f"Removed {count} cached walkthrough{'s' if count != 1 else ''}."
        )


@cache_app.command("list")
def cache_list() -> None:
    """List every cached walkthrough with its source and timestamp."""
    entries = cache.list_entries()
    if not entries:
        stdout.print("No cached walkthroughs.")
        stdout.print(f"[dim]Cache directory: {cache.cache_dir()}[/dim]")
        return
    for e in entries:
        ts = "unknown time"
        if e.cached_at > 0:
            ts = datetime.fromtimestamp(e.cached_at).isoformat(timespec="seconds")
        label = e.source_label or "(unlabeled)"
        stdout.print(
            f"[bold]{ts}[/bold]  {label}  "
            f"[dim]{e.provider}/{e.model}[/dim]"
        )
    stdout.print(f"[dim]Cache directory: {cache.cache_dir()}[/dim]")


@conf_app.callback()
def conf_root(ctx: typer.Context) -> None:
    """Show the current persistent config when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    # markup=False so TOML section headers like [diff] survive Rich rendering.
    stdout.print(render_config_toml().rstrip(), markup=False, highlight=False)
    stdout.print(f"[dim]Config file: {config_path()}[/dim]")


@conf_app.command("get")
def conf_get(
    key: Annotated[str, typer.Argument(help="Dotted key, e.g. diff.wrap_mode")],
) -> None:
    """Print a single setting's value."""
    try:
        value = get_setting(key)
    except ValueError as exc:
        console.print("[red]Error:[/red] " + str(exc).replace("[", r"\["))
        raise typer.Exit(1) from exc
    stdout.print(value)


@conf_app.command("set")
def conf_set(
    key: Annotated[str, typer.Argument(help="Dotted key, e.g. diff.wrap_mode")],
    value: Annotated[str, typer.Argument(help="New value (string, bool, or int)")],
) -> None:
    """Update a setting and persist it to the config file."""
    try:
        coerced = update_setting(key, value)
    except ValueError as exc:
        console.print("[red]Error:[/red] " + str(exc).replace("[", r"\["))
        raise typer.Exit(1) from exc
    stdout.print(f"[dim]{key} =[/dim] {coerced!r}")
    stdout.print(f"[dim]Saved to {config_path()}[/dim]")


@conf_app.command("path")
def conf_path() -> None:
    """Print the absolute path to the config file."""
    stdout.print(str(config_path()))


@conf_app.command("edit")
def conf_edit() -> None:
    """Open the config file in $EDITOR (creates it with defaults if missing)."""
    target = config_path()
    if not target.exists():
        # Materialize the defaults so the user has something to edit.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_config_toml())
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    try:
        subprocess.run([editor, str(target)], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        console.print(f"[red]Could not launch editor '{editor}':[/red] {exc}")
        raise typer.Exit(1) from exc


def _format_age(cached_at: float) -> str:
    """Return a human-friendly "N units ago" string for a unix timestamp."""
    if cached_at <= 0:
        return "unknown time"
    delta = datetime.now().timestamp() - cached_at
    if delta < 60:
        return "just now"
    if delta < 3600:
        mins = int(delta // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if delta < 86400:
        hours = int(delta // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(delta // 86400)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _format_completion(metadata: dict) -> str:
    """Build the "Analysis complete" line with timing and token counts."""
    elapsed = metadata.get("elapsed_seconds", 0)
    provider = metadata.get("provider", "")
    model = metadata.get("model", "")
    head = f"Analysis complete in {elapsed}s"
    if provider and model:
        head += f" ({provider}/{model})"
    parts = [head]
    thinking = metadata.get("thinking_tokens", 0)
    output = metadata.get("output_tokens", 0)
    input_tokens = metadata.get("input_tokens", 0)
    cache_read = metadata.get("cache_read_tokens", 0)
    if thinking:
        parts.append(f"{thinking:,} thinking tokens")
    if output:
        parts.append(f"{output:,} output tokens")
    if input_tokens:
        label = f"{input_tokens:,} input tokens"
        if cache_read:
            label += f" ({cache_read:,} cached)"
        parts.append(label)
    return " · ".join(parts)


def _run(
    *,
    diff_source: str,
    range_spec: str | None = None,
    pr_number: int | None = None,
    repo: str | None = None,
    remote: str = "origin",
    staged: bool = False,
    model: str | None,
    provider: str | None,
    json_output: bool,
    tree_only: bool,
    markdown_output: bool = False,
    github_comment: bool = False,
    no_tui: bool = False,
    thinking_budget: int | None,
    max_output_tokens: int | None,
    fresh: bool = False,
    no_cache: bool = False,
    api_key: str | None,
) -> None:
    import sys

    try:
        config = load_config(
            provider=provider,
            model=model,
            api_key=api_key,
            thinking_budget=thinking_budget,
            max_output_tokens=max_output_tokens,
        )

        requested_provider = config.provider
        llm = get_provider(config)  # resolves "auto" → concrete provider
        llm.validate_config()

        if requested_provider == "auto":
            label = {
                "claude-cli": "local Claude CLI",
                "anthropic": "Anthropic API",
            }.get(config.provider, config.provider)
            console.print(f"[dim]Using {label}[/dim]")

        metadata: dict = {}
        source_label: str
        source_info = None
        if diff_source == "range":
            console.print(f"[dim]Getting diff for {range_spec}...[/dim]")
            raw_diff = get_diff_from_range(range_spec, staged=staged)
            source_label = f"range:{range_spec}"
            if staged:
                source_label += " (staged)"
            source_info = build_range_source_info(
                range_spec, staged=staged, remote=remote
            )
        else:
            console.print(f"[dim]Getting diff for PR #{pr_number}...[/dim]")
            raw_diff = get_diff_from_pr(pr_number, remote=remote, repo=repo)
            source_label = f"pr:#{pr_number}"
            try:
                metadata = get_pr_metadata(pr_number, remote=remote, repo=repo)
            except UnravelGitError:
                pass  # metadata is optional
            source_info = build_pr_source_info(
                pr_number, metadata or None, remote=remote, repo=repo
            )

        pr_files_url = None
        repo_nwo = None
        if diff_source == "pr" and pr_number:
            nwo = get_repo_nwo(remote, repo)
            if nwo:
                repo_nwo = nwo
                pr_files_url = f"https://github.com/{nwo}/pull/{pr_number}/files"

        hunks = parse_diff(raw_diff)
        file_count = len({h.file_path for h in hunks})
        console.print(
            f"[dim]Parsed {len(hunks)} hunks across {file_count} files[/dim]"
        )

        walkthrough = None
        if not no_cache and not fresh:
            entry = cache.load(
                raw_diff, config.provider, config.resolved_model
            )
            if entry is not None:
                walkthrough = entry.walkthrough
                age = _format_age(entry.cached_at)
                console.print(
                    f"[dim]Loaded cached analysis from {age} "
                    f"({entry.provider}/{entry.model})[/dim]"
                )

        if walkthrough is None and diff_source == "pr" and not no_cache and not fresh:
            console.print("[dim]Checking for remote cache...[/dim]")
            walkthrough = remote_cache.fetch_from_pr_comment(
                pr_number, raw_diff, remote=remote, repo=repo_nwo
            )
            if walkthrough is not None:
                console.print("[dim]Loaded analysis from PR comment cache[/dim]")
                cache.save(
                    raw_diff,
                    walkthrough.metadata.get("provider", config.provider),
                    walkthrough.metadata.get("model", config.resolved_model),
                    walkthrough,
                    source_label=source_label,
                )

        if walkthrough is None:
            with console.status(
                "[bold cyan]Starting analysis...", spinner="dots"
            ) as live:
                walkthrough = llm.analyze(
                    hunks,
                    raw_diff,
                    metadata,
                    on_status=lambda msg: live.update(f"[bold cyan]{msg}"),
                )
            console.print(
                f"[dim]{_format_completion(walkthrough.metadata)}[/dim]"
            )
            if not no_cache:
                cache.save(
                    raw_diff,
                    config.provider,
                    config.resolved_model,
                    walkthrough,
                    source_label=source_label,
                )

        walkthrough, hydration_warnings = hydrate_walkthrough(walkthrough, hunks)
        for w in hydration_warnings:
            console.print(f"[yellow]Hydration:[/yellow] {w}")

        warnings = validate_walkthrough(walkthrough, hunks)
        for w in warnings:
            console.print(f"[yellow]Warning:[/yellow] {w}")

        if github_comment:
            # Bypass Rich to avoid line-wrapping the long base64 payload.
            sys.stdout.write(
                render_github_comment(
                    walkthrough,
                    pr_files_url=pr_files_url,
                    pr_number=pr_number,
                    repo_nwo=repo_nwo,
                )
                + "\n"
            )
        elif json_output:
            stdout.print(render_json(walkthrough))
        elif markdown_output:
            stdout.print(render_markdown(walkthrough, pr_files_url=pr_files_url))
        elif tree_only:
            render_tree(walkthrough, stdout)
        elif no_tui or not sys.stdout.isatty():
            render_rich(walkthrough, stdout)
        else:
            from unravel.tui import UnravelApp

            app = UnravelApp(
                walkthrough=walkthrough,
                all_hunks=hunks,
                source_info=source_info,
                diff_cfg=config.diff,
            )
            app.run()

    except UnravelGitError as exc:
        console.print(f"[red]Git error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConnectionError as exc:
        console.print(f"[red]Network error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except KeyboardInterrupt as exc:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise typer.Exit(130) from exc
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(
            f"[red]Unexpected error:[/red] {type(exc).__name__}: {exc}"
        )
        raise typer.Exit(1) from exc
