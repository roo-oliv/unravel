# homebrew-unravel

Homebrew tap for [unravel](https://github.com/roo-oliv/unravel) — an AI-powered CLI that decomposes PR diffs into causal threads for human code reviewers.

## Install

```bash
brew tap roo-oliv/unravel
brew install unravel
```

## Upgrade

```bash
brew update
brew upgrade unravel
```

## Uninstall

```bash
brew uninstall unravel
brew untap roo-oliv/unravel
```

## About this tap

This repository contains the Homebrew formula for `unravel-review` (PyPI) / `unravel` (CLI binary). The formula vendors all transitive Python dependencies as `resource` blocks so installs are reproducible and don't pull from PyPI at install time.

## Releasing

The formula is intended to be regenerated on each release of the main repo. Until the automation is in place (see the TODO block at the top of `Formula/unravel.rb`), the process is:

1. Publish a new release of `unravel-review` to PyPI.
2. In a scratch directory:
   ```bash
   uv venv --python 3.12 .poet && source .poet/bin/activate
   uv pip install 'setuptools<81' homebrew-pypi-poet unravel-review==<new-version>
   poet -f unravel-review > new-formula.rb
   ```
3. Copy the generated `url`/`sha256` and every `resource` block into `Formula/unravel.rb`, preserving the `desc`, `homepage`, `depends_on`, `install`, and `test` sections.
4. Commit and push. Users get the update on their next `brew update`.

## Audit

Before publishing a formula update, run:

```bash
brew install --build-from-source Formula/unravel.rb
brew test Formula/unravel.rb
brew audit --strict --online Formula/unravel.rb
```

## License

The formula itself is BSD-2-Clause (matching Homebrew convention). The `unravel` software it installs is AGPL-3.0-or-later.
