# Unravel

AI-powered CLI that decomposes PR diffs into **causal threads** for human code reviewers.

Instead of reviewing a diff file-by-file, Unravel groups changes by *why* they were made — each thread tells a story from root cause to effect, so reviewers build understanding progressively.

## Installation

Pick whichever channel fits your setup — they all install the same package.

### uv (recommended)

```bash
uv tool install unravel-review
```

### pipx

```bash
pipx install unravel-review
```

### pip

```bash
pip install unravel-review
```

### Homebrew

```bash
brew tap roo-oliv/unravel
brew install unravel-review
```

`brew install unravel` works too — it's a tap-level alias.

### One-liner (auto-detects uv/pipx)

```bash
curl -fsSL https://raw.githubusercontent.com/roo-oliv/unravel/main/install.sh | bash
```

### Docker

```bash
docker run --rm -v "$(pwd):/repo" -e ANTHROPIC_API_KEY \
  ghcr.io/roo-oliv/unravel diff HEAD~1
```

## Quick Start

```bash
# Analyze the last commit
unravel diff HEAD~1..HEAD

# Analyze a range
unravel diff main..feature-branch

# Analyze a GitHub PR (requires gh CLI)
unravel pr 42

# JSON output for piping
unravel diff HEAD~1..HEAD --json | jq .

# Compact tree view
unravel diff HEAD~1..HEAD --tree-only
```

## Requirements

- Python 3.12+
- Git
- An API key for a supported LLM provider
- [GitHub CLI](https://cli.github.com) (only for `unravel pr`)

## Configuration

Set your API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--model`, `-m` | Model to use (default: `claude-sonnet-4-6`) |
| `--provider`, `-p` | LLM provider (default: `anthropic`) |
| `--json`, `-j` | Output raw JSON |
| `--tree-only`, `-t` | Compact tree view |
| `--thinking-budget` | Extended thinking token budget (default: 10000) |
| `--staged` | Analyze only staged changes (diff command only) |
| `--remote` | Git remote name (pr command only, default: `origin`) |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Anthropic/Claude |
| `OPENAI_API_KEY` | API key for OpenAI (future) |
| `UNRAVEL_PROVIDER` | Default provider |
| `UNRAVEL_MODEL` | Default model |
| `UNRAVEL_THINKING_BUDGET` | Default thinking budget |

## How It Works

1. **Extract** — Pulls the diff from git or GitHub
2. **Parse** — Breaks the diff into hunks using [unidiff](https://github.com/matiasb/python-unidiff)
3. **Analyze** — Sends hunks to an LLM with a specialized prompt that decomposes changes into causal threads
4. **Validate** — Checks all hunks are covered and thread dependencies are consistent
5. **Render** — Displays threads in rich terminal output, JSON, or tree view

## Multi-Provider Support

Unravel is designed to work with multiple LLM providers. Currently supported:

- **Anthropic** (Claude) — default, with extended thinking support

Planned: OpenAI, Gemini, and more. The provider abstraction is ready — contributions welcome.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full local setup, testing conventions, code style, and release process. TL;DR:

```bash
git clone https://github.com/roo-oliv/unravel.git
cd unravel
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

AGPL-3.0-or-later
