# Contributing to unravel

Thanks for wanting to help! This guide covers the local setup, how the project is laid out, the testing and style conventions, and how releases ship.

## Development setup

Unravel uses [**uv**](https://docs.astral.sh/uv/) for environment and dependency management. Install uv first if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repo root:

```bash
# Resolve + install the project and its dev extras into .venv/
uv sync --extra dev

# Run the CLI against your own checkout
uv run unravel --version
uv run unravel diff HEAD~1

# Run the tests
uv run pytest

# Lint
uv run ruff check .
```

`uv run <cmd>` auto-creates and syncs the virtualenv on first use; subsequent calls are a no-op unless `pyproject.toml` changes.

## Project structure

```
src/unravel/
├── __init__.py          # exposes __version__ via importlib.metadata
├── cli.py               # Typer app — entry points for `unravel diff` and `unravel pr`
├── models.py            # Pydantic models for threads, walkthroughs, rows
├── git.py               # git subprocess wrapper (diff / blame / show)
├── hydration.py         # merges raw diffs with LLM-produced thread metadata
├── narrator.py          # prompt building + LLM orchestration
├── prompts.py           # prompt templates
├── providers/           # pluggable LLM backends (anthropic today)
├── renderer.py          # Rich-based stdout rendering (v1)
├── tui/                 # Textual TUI (v2 interactive walkthrough)
├── cache.py             # on-disk cache for LLM responses
└── config.py            # config discovery + settings model
tests/                   # pytest suite; see conftest.py for shared fixtures
```

A good starting read is `cli.py` (how commands are wired), then `narrator.py` (the core orchestration), then `tui/app.py` (interactive UI).

## Testing

- Tests live in `tests/`, use `pytest`, and should not make real LLM calls.
- Shared fixtures are in `tests/conftest.py`: `simple_diff`, `sample_response_text`, `sample_response_dict`, `sample_walkthrough`.
- Fixture data lives in `tests/fixtures/`.
- When adding a test that needs LLM output, prefer loading a fixture over mocking the SDK — it keeps tests decoupled from Anthropic's API shape.
- Async tests use `pytest-asyncio` (already a dev dep); mark with `@pytest.mark.asyncio`.

Run the whole suite with `uv run pytest`. Run a single test with `uv run pytest tests/test_narrator.py::test_thread_extraction -q`.

## Code style

- **Formatter**: ruff is the only formatter. `uv run ruff format .` before committing.
- **Linter**: `uv run ruff check .` must pass. The configured rule set is `E,F,I,N,W,UP`.
- **Line length**: 100.
- **Type hints**: required on all new public functions and dataclass fields. Use `from __future__ import annotations` at the top of new modules (already the pattern in the codebase).
- **Docstrings**: Google style for public APIs — a short one-line summary, then `Args:`, `Returns:`, `Raises:` as needed.
- **Imports**: let ruff handle ordering (rule `I`). Avoid relative imports outside the same subpackage.

CI runs `ruff check` and `pytest` on Python 3.12 and 3.13 — see `.github/workflows/ci.yml`.

## Release process

Releases are driven from GitHub Releases and publish to PyPI via Trusted Publishers (no tokens needed). The package version is derived automatically from the release tag via `hatch-vcs` — **do not** bump anything in `pyproject.toml`.

1. Make sure `main` is green on CI.
2. Decide the new version, e.g. `0.3.0`.
3. Draft a GitHub Release:
   ```bash
   gh release create v0.3.0 --target main --title "v0.3.0" --generate-notes
   ```
   - Tag must begin with `v` and match `vX.Y.Z` or `vX.Y.ZrcN` / `vX.Y.ZbN` / `vX.Y.ZaN`.
   - To release a pre-release build to TestPyPI only, add `--prerelease`. The `release.yml` workflow routes on this flag — pre-releases go to https://test.pypi.org, stable releases go to https://pypi.org.
4. Publish the release. The `release` workflow builds the wheel + sdist, uploads them via OIDC, and attaches them to the GitHub Release page. The `docker` workflow builds and pushes multi-arch images to `ghcr.io/roo-oliv/unravel`.
5. Verify:
   ```bash
   pip install --upgrade unravel-review
   unravel --version   # should print the new version
   ```

### Homebrew formula

The Homebrew tap lives at [roo-oliv/homebrew-unravel](https://github.com/roo-oliv/homebrew-unravel). The `update-homebrew-tap` job in `.github/workflows/release.yml` regenerates the formula (via `homebrew-pypi-poet`) and pushes it to the tap repo automatically after each non-prerelease PyPI upload.

That job requires a one-time setup:

1. Create a fine-grained GitHub Personal Access Token with **Contents: Read and write** scoped to the `roo-oliv/homebrew-unravel` repository only.
2. In this repo's settings → Secrets and variables → Actions → New repository secret, add it as `HOMEBREW_TAP_TOKEN`.

Without that secret the `update-homebrew-tap` job is a no-op (emits a warning in the Actions log) — releases still ship, but Homebrew users will be one version behind until you regenerate by hand.

If you ever need to regenerate manually, follow the procedure in [`homebrew-tap/README.md`](homebrew-tap/README.md).

### If something goes wrong

- **Publish failed**: check the `release` run in Actions. The most common causes are PyPI Trusted Publisher config drift or a tag that doesn't match the expected pattern.
- **Wrong version shipped**: don't delete the release tag — yank the PyPI release instead (`pip install unravel-review==X.Y.Z` will still be possible but hidden from `pip install unravel-review`). Then publish a fix as `X.Y.Z+1`.

## Pull requests

- Small, focused PRs merge faster. One logical change per PR.
- Include tests for new behavior; CI gates on them.
- Update `README.md` or docstrings if you change user-facing behavior.
- By default, branches are squash-merged into `main` with the PR title as the commit subject — make the title the change log you'd want to read.

Thanks again!
