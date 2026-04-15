# syntax=docker/dockerfile:1.7

# --- build stage -----------------------------------------------------------
# Produce a wheel for unravel-review. The package uses hatch-vcs, which
# derives the version from git tags — but `.git` does not survive cleanly
# into the build context when the source tree is itself a git worktree.
# The VERSION build arg lets callers (CI, local dev) pin the version
# explicitly and bypass hatch-vcs's git scan.
#
#   docker build --build-arg VERSION=0.2.0 -t unravel:0.2.0 .
FROM python:3.12-slim AS builder

ARG VERSION=0.0.0.dev0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /src
COPY . /src

# The project uses hatch-vcs to derive version from git tags, but `.git`
# does not always survive into the build context (e.g. source trees that
# are themselves git worktrees). Pin the version in pyproject.toml to
# make the build self-contained and deterministic.
RUN python3 - <<PY
import pathlib, re
p = pathlib.Path("pyproject.toml")
src = p.read_text()
src = re.sub(r'^dynamic\s*=\s*\["version"\]\s*$',
             'version = "${VERSION}"', src, flags=re.M)
src = re.sub(r'\n\[tool\.hatch\.version[^\[]*', '\n', src)
p.write_text(src)
PY

RUN uv build --wheel --out-dir /dist

# --- runtime stage ---------------------------------------------------------
# Slim image containing only Python, git, and the installed package. Mount
# your working copy at /repo to analyse it.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# `git` is required at runtime — unravel shells out to it via
# `src/unravel/git.py`. `ca-certificates` for TLS to api.anthropic.com.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install the wheel produced by the build stage. Using pip here keeps the
# runtime image free of uv.
COPY --from=builder /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# Mounted repo lives here; matches the Usage docs.
WORKDIR /repo

# Let the container work on a host-owned bind mount without tripping git's
# dubious-ownership guard (container UID != host UID in most setups).
RUN git config --system --add safe.directory '*'

ENTRYPOINT ["unravel"]
CMD ["--help"]
