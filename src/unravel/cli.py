"""Unravel CLI — decompose PR diffs into causal threads."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from unravel import __version__
from unravel.config import load_config
from unravel.git import (
    UnravelGitError,
    get_diff_from_pr,
    get_diff_from_range,
    get_pr_metadata,
    parse_diff,
)
from unravel.hydration import hydrate_walkthrough
from unravel.narrator import validate_walkthrough
from unravel.providers import get_provider
from unravel.renderer import render_json, render_rich, render_tree

app = typer.Typer(
    name="unravel",
    help="AI-powered CLI that decomposes PR diffs into causal threads.",
    no_args_is_help=True,
)
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
        no_tui=no_tui,
        thinking_budget=thinking_budget,
        max_output_tokens=max_output_tokens,
        api_key=api_key,
    )


@app.command()
def pr(
    number: Annotated[int, typer.Argument(help="PR number")],
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
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key", envvar="UNRAVEL_API_KEY"),
    ] = None,
) -> None:
    """Analyze a GitHub PR and decompose into causal threads."""
    _run(
        diff_source="pr",
        pr_number=number,
        remote=remote,
        model=model,
        provider=provider,
        json_output=json_output,
        tree_only=tree_only,
        no_tui=no_tui,
        thinking_budget=thinking_budget,
        max_output_tokens=max_output_tokens,
        api_key=api_key,
    )


def _run(
    *,
    diff_source: str,
    range_spec: str | None = None,
    pr_number: int | None = None,
    remote: str = "origin",
    staged: bool = False,
    model: str | None,
    provider: str | None,
    json_output: bool,
    tree_only: bool,
    no_tui: bool = False,
    thinking_budget: int | None,
    max_output_tokens: int | None,
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

        llm = get_provider(config)
        llm.validate_config()

        metadata: dict = {}
        if diff_source == "range":
            console.print(f"[dim]Getting diff for {range_spec}...[/dim]")
            raw_diff = get_diff_from_range(range_spec, staged=staged)
        else:
            console.print(f"[dim]Getting diff for PR #{pr_number}...[/dim]")
            raw_diff = get_diff_from_pr(pr_number, remote=remote)
            try:
                metadata = get_pr_metadata(pr_number, remote=remote)
            except UnravelGitError:
                pass  # metadata is optional

        hunks = parse_diff(raw_diff)
        file_count = len({h.file_path for h in hunks})
        console.print(
            f"[dim]Parsed {len(hunks)} hunks across {file_count} files[/dim]"
        )

        with console.status(
            "[bold cyan]Starting analysis...", spinner="dots"
        ) as live:
            walkthrough = llm.analyze(
                hunks,
                raw_diff,
                metadata,
                on_status=lambda msg: live.update(f"[bold cyan]{msg}"),
            )
        elapsed = walkthrough.metadata.get("elapsed_seconds", 0)
        console.print(f"[dim]Analysis complete in {elapsed}s[/dim]")

        walkthrough, hydration_warnings = hydrate_walkthrough(walkthrough, hunks)
        for w in hydration_warnings:
            console.print(f"[yellow]Hydration:[/yellow] {w}")

        warnings = validate_walkthrough(walkthrough, hunks)
        for w in warnings:
            console.print(f"[yellow]Warning:[/yellow] {w}")

        if json_output:
            stdout.print(render_json(walkthrough))
        elif tree_only:
            render_tree(walkthrough, stdout)
        elif no_tui or not sys.stdout.isatty():
            render_rich(walkthrough, stdout)
        else:
            from unravel.tui import UnravelApp

            app = UnravelApp(walkthrough=walkthrough, all_hunks=hunks)
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
