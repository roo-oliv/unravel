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
- **Either** the [Claude CLI](https://claude.com/product/claude-code) installed and authenticated, **or** an Anthropic API key
- [GitHub CLI](https://cli.github.com) (only for `unravel pr`)

## Configuration

By default Unravel runs in **auto** mode: it uses the local Claude CLI if `claude` is on your `PATH`, and falls back to the Anthropic API otherwise. No extra configuration needed if you already have `claude` installed.

For the API path, set your key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Backends

| Mode | When it's used | What it needs |
|------|----------------|---------------|
| `auto` (default) | Picks the first available backend | `claude` on PATH **or** `ANTHROPIC_API_KEY` |
| `claude-cli` | Always use the local Claude CLI | `claude` binary, authenticated |
| `claude-api` | Always hit the Claude API | `ANTHROPIC_API_KEY` |

Pin a specific backend any of these ways:

```bash
unravel conf set provider claude-api      # persistent
UNRAVEL_PROVIDER=claude-cli unravel ...   # one session
unravel diff HEAD~1 --provider claude-api # single invocation
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--model`, `-m` | Model to use (default: `claude-sonnet-4-6`) |
| `--provider`, `-p` | LLM provider: `auto`, `claude-cli`, or `claude-api` (default: `auto`) |
| `--json`, `-j` | Output raw JSON |
| `--tree-only`, `-t` | Compact tree view |
| `--thinking-budget` | Extended thinking token budget (default: 10000) |
| `--staged` | Analyze only staged changes (diff command only) |
| `--remote` | Git remote name (pr command only, default: `origin`) |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for the Claude API (not needed with `claude-cli` backend) |
| `OPENAI_API_KEY` | API key for OpenAI (future) |
| `UNRAVEL_PROVIDER` | Default provider: `auto`, `claude-cli`, or `claude-api` |
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

- **Claude CLI** (`claude-cli`) — uses your local, authenticated `claude` binary
- **Claude API** (`claude-api`) — direct HTTP via the Anthropic SDK, with extended thinking support

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
