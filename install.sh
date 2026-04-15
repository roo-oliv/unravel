#!/usr/bin/env bash
# Unravel installer — AI-powered code-review walkthroughs.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/roo-oliv/unravel/main/install.sh | bash
#
# Env vars:
#   UNRAVEL_NO_MODIFY_PATH=1   Don't let uv's installer modify shell config on your behalf.
#   NO_COLOR=1                 Disable colored output.
#
set -euo pipefail

PKG="unravel-review"
BIN="unravel"
REPO="roo-oliv/unravel"

# --- terminal colors (only if stdout is a TTY and NO_COLOR is not set) -----
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]] && command -v tput >/dev/null 2>&1 \
   && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  C_RESET=$(tput sgr0);   C_BOLD=$(tput bold);     C_DIM=$(tput dim)
  C_RED=$(tput setaf 1);  C_GREEN=$(tput setaf 2); C_YELLOW=$(tput setaf 3)
  C_BLUE=$(tput setaf 4); C_MAGENTA=$(tput setaf 5)
else
  C_RESET=""; C_BOLD=""; C_DIM=""
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_MAGENTA=""
fi

info() { printf "%s→ %s%s\n" "$C_BLUE" "$1" "$C_RESET"; }
warn() { printf "%s! %s%s\n" "$C_YELLOW" "$1" "$C_RESET"; }
err()  { printf "%s✗ %s%s\n" "$C_RED" "$1" "$C_RESET" >&2; }
ok()   { printf "%s✓ %s%s\n" "$C_GREEN" "$1" "$C_RESET"; }

on_error() { err "Installation failed at line $1. See messages above."; }
trap 'on_error $LINENO' ERR

# --- banner ----------------------------------------------------------------
printf "%s%s" "$C_BOLD" "$C_MAGENTA"
cat <<'BANNER'
  _   _ _ __  _ __ __ ___   _____| |
 | | | | '_ \| '__/ _` \ \ / / _ \ |
 | |_| | | | | | | (_| |\ V /  __/ |
  \__,_|_| |_|_|  \__,_| \_/ \___|_|
BANNER
printf "%s\n" "$C_RESET"
printf "  %sai code-review walkthroughs for human reviewers%s\n\n" "$C_DIM" "$C_RESET"

# --- detect OS -------------------------------------------------------------
case "$(uname -s)" in
  Darwin) OS="macOS" ;;
  Linux)  OS="Linux" ;;
  *)      err "Unsupported OS: $(uname -s). unravel supports macOS and Linux."; exit 1 ;;
esac
info "Detected $OS"

# --- confirm helper that works under curl | bash ---------------------------
# stdin is consumed by the pipe, so read from /dev/tty instead.
confirm() {
  local prompt="$1" reply=""
  if [[ ! -r /dev/tty ]]; then
    warn "No interactive terminal available; assuming 'no'."
    return 1
  fi
  printf "%s [y/N] " "$prompt" > /dev/tty
  read -r reply < /dev/tty || return 1
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# --- pick an installer -----------------------------------------------------
INSTALLER=""

if command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"
  info "Found uv at $(command -v uv)"
elif command -v pipx >/dev/null 2>&1; then
  INSTALLER="pipx"
  info "Found pipx at $(command -v pipx)"
else
  warn "Neither uv nor pipx is installed."
  warn "unravel needs one of them to install into an isolated environment."
  echo
  if confirm "Install uv now? (https://docs.astral.sh/uv/)"; then
    info "Installing uv…"
    if [[ -n "${UNRAVEL_NO_MODIFY_PATH:-}" ]]; then
      UV_NO_MODIFY_PATH=1 curl -LsSf https://astral.sh/uv/install.sh | sh
    else
      curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    # uv's installer modifies shell config for future sessions; pick up the
    # new PATH in *this* session manually so the next step can find `uv`.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
      err "uv install appears to have failed. See https://docs.astral.sh/uv/getting-started/installation/"
      exit 1
    fi
    ok "uv installed"
    INSTALLER="uv"
  else
    err "Aborted. Install uv (https://docs.astral.sh/uv/) or pipx (https://pipx.pypa.io/) first, then re-run this script."
    exit 1
  fi
fi

# --- install unravel -------------------------------------------------------
info "Installing $PKG with $INSTALLER…"
case "$INSTALLER" in
  uv)   uv tool install "$PKG" ;;
  pipx) pipx install "$PKG" ;;
esac

# --- verify ----------------------------------------------------------------
# Installed binaries live in ~/.local/bin for both uv tool and pipx on a
# default setup. Add it to PATH for this verification step even if the
# user's shell rc hasn't been reloaded.
export PATH="$HOME/.local/bin:$PATH"

if ! command -v "$BIN" >/dev/null 2>&1; then
  warn "$BIN was installed but is not on PATH in this shell."
  warn "It's likely at: $HOME/.local/bin/$BIN"
  warn "Open a new terminal, or run: export PATH=\"\$HOME/.local/bin:\$PATH\""
  exit 1
fi

VERSION_LINE="$("$BIN" --version 2>&1 | tail -n1 || true)"
ok "Installed: ${C_BOLD}${VERSION_LINE}${C_RESET}"

# --- getting started -------------------------------------------------------
cat <<HINT

${C_BOLD}Get started:${C_RESET}
  ${C_DIM}# Set your Anthropic API key${C_RESET}
  export ANTHROPIC_API_KEY=sk-ant-...

  ${C_DIM}# Walk through the last commit on the current branch${C_RESET}
  $BIN diff HEAD~1

Installer: ${C_BOLD}$INSTALLER${C_RESET}   Docs: ${C_BLUE}https://github.com/${REPO}${C_RESET}
HINT
