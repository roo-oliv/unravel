"""Configuration loading for Unravel."""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "claude-cli": "claude-sonnet-4-6",
}

KNOWN_PROVIDERS: tuple[str, ...] = ("auto", "anthropic", "claude-cli")

WrapMode = str  # "wrap" | "scroll"
_VALID_WRAP_MODES = ("wrap", "scroll")


@dataclass
class DiffDisplayConfig:
    """User-tweakable preferences for how diffs render in the TUI."""

    wrap_mode: WrapMode = "wrap"
    syntax_highlight: bool = True
    show_line_numbers: bool = True
    theme: str = "monokai"

    def validate(self) -> None:
        if self.wrap_mode not in _VALID_WRAP_MODES:
            raise ValueError(
                f"diff.wrap_mode must be one of {_VALID_WRAP_MODES}, "
                f"got {self.wrap_mode!r}"
            )
        if not isinstance(self.syntax_highlight, bool):
            raise ValueError("diff.syntax_highlight must be a boolean")
        if not isinstance(self.show_line_numbers, bool):
            raise ValueError("diff.show_line_numbers must be a boolean")
        if not isinstance(self.theme, str) or not self.theme:
            raise ValueError("diff.theme must be a non-empty string")


@dataclass
class ClaudeCLIConfig:
    """Settings for invoking the local Claude CLI backend."""

    path: str = "claude"
    respect_user_model: bool = False
    timeout_seconds: int = 600

    def validate(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("claude_cli.path must be a non-empty string")
        if not isinstance(self.respect_user_model, bool):
            raise ValueError("claude_cli.respect_user_model must be a boolean")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError("claude_cli.timeout_seconds must be a positive integer")


@dataclass
class UnravelConfig:
    provider: str = "auto"
    api_key: str | None = None
    model: str | None = None
    thinking_budget: int = 10_000
    max_output_tokens: int = 16_000
    diff: DiffDisplayConfig = field(default_factory=DiffDisplayConfig)
    claude_cli: ClaudeCLIConfig = field(default_factory=ClaudeCLIConfig)

    @property
    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return PROVIDER_DEFAULT_MODELS.get(self.provider, "")

    @property
    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        env_var = PROVIDER_ENV_KEYS.get(self.provider)
        if env_var:
            key = os.environ.get(env_var, "")
            if key:
                return key
        raise ValueError(
            f"No API key found for provider '{self.provider}'. "
            f"Set {PROVIDER_ENV_KEYS.get(self.provider, 'the appropriate env var')} "
            f"or pass --api-key."
        )


# ---------------------------------------------------------------------------
# Persistent config file (TOML under XDG config home)
# ---------------------------------------------------------------------------


def config_path() -> Path:
    """Resolve the path to the persistent config file.

    Honors $XDG_CONFIG_HOME and falls back to ``~/.config/unravel/config.toml``.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "unravel" / "config.toml"


def load_persistent_config(path: Path | None = None) -> dict[str, Any]:
    """Read the config file as a nested dict. Returns ``{}`` if missing/unreadable."""
    target = path or config_path()
    if not target.exists():
        return {}
    try:
        with target.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def save_persistent_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Write the config dict to disk as TOML. Creates parent dirs if needed."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_dump_toml(data))


def _dump_toml(data: dict[str, Any]) -> str:
    """Minimal TOML writer for our flat section-based schema.

    Handles top-level scalars and one level of sections (tables). Sufficient for
    our current config and avoids an extra dependency.
    """
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for k, v in scalars.items():
        lines.append(f"{k} = {_format_value(v)}")
    for section, body in tables.items():
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        for k, v in body.items():
            lines.append(f"{k} = {_format_value(v)}")
    return "\n".join(lines) + "\n"


def _format_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"Cannot serialize {type(v).__name__} to TOML")


def _diff_config_from_dict(section: dict[str, Any]) -> DiffDisplayConfig:
    """Build a DiffDisplayConfig from a loaded [diff] dict, defaulting unknown keys."""
    known = {f.name for f in fields(DiffDisplayConfig)}
    kwargs = {k: v for k, v in section.items() if k in known}
    cfg = DiffDisplayConfig(**kwargs)
    try:
        cfg.validate()
    except ValueError:
        # Bad on-disk values — fall back silently to defaults rather than crash.
        return DiffDisplayConfig()
    return cfg


def _claude_cli_config_from_dict(section: dict[str, Any]) -> ClaudeCLIConfig:
    """Build a ClaudeCLIConfig from a loaded [claude_cli] dict, defaulting unknown keys."""
    known = {f.name for f in fields(ClaudeCLIConfig)}
    kwargs = {k: v for k, v in section.items() if k in known}
    cfg = ClaudeCLIConfig(**kwargs)
    try:
        cfg.validate()
    except ValueError:
        return ClaudeCLIConfig()
    return cfg


# ---------------------------------------------------------------------------
# Dotted-key helpers (for `unravel conf get/set`)
# ---------------------------------------------------------------------------


_TOP_LEVEL_SCHEMA: dict[str, type] = {"provider": str}

_SCHEMA: dict[str, dict[str, type]] = {
    "diff": {
        "wrap_mode": str,
        "syntax_highlight": bool,
        "show_line_numbers": bool,
        "theme": str,
    },
    "claude_cli": {
        "path": str,
        "respect_user_model": bool,
        "timeout_seconds": int,
    },
}


def _split_key(key: str) -> tuple[str | None, str]:
    """Split ``key`` into ``(section, name)`` where ``section`` is ``None`` for top-level keys."""
    if "." not in key:
        if key not in _TOP_LEVEL_SCHEMA:
            raise ValueError(
                f"Unknown top-level setting '{key}'. Either use a dotted "
                f"'section.name' key or one of: "
                f"{', '.join(sorted(_TOP_LEVEL_SCHEMA))}"
            )
        return None, key
    section, name = key.split(".", 1)
    if section not in _SCHEMA:
        raise ValueError(
            f"Unknown section '{section}'. Known sections: "
            f"{', '.join(sorted(_SCHEMA))}"
        )
    if name not in _SCHEMA[section]:
        raise ValueError(
            f"Unknown setting '{name}' in [{section}]. Known settings: "
            f"{', '.join(sorted(_SCHEMA[section]))}"
        )
    return section, name


def _coerce_value(section: str | None, name: str, raw: str) -> Any:
    expected = _TOP_LEVEL_SCHEMA[name] if section is None else _SCHEMA[section][name]
    if expected is bool:
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(
            f"Expected boolean for {_fmt_key(section, name)}, got {raw!r}"
        )
    if expected is int:
        return int(raw)
    return raw


def _fmt_key(section: str | None, name: str) -> str:
    return name if section is None else f"{section}.{name}"


def _validate_top_level(name: str, value: Any) -> None:
    if name == "provider":
        if value not in KNOWN_PROVIDERS:
            raise ValueError(
                f"provider must be one of {', '.join(KNOWN_PROVIDERS)}, got {value!r}"
            )


def get_setting(key: str, path: Path | None = None) -> Any:
    section, name = _split_key(key)
    data = load_persistent_config(path)
    if section is None:
        return data.get(name, _top_level_default(name))
    if section == "diff":
        cfg = _diff_config_from_dict(data.get(section, {}) or {})
        return getattr(cfg, name)
    if section == "claude_cli":
        cfg = _claude_cli_config_from_dict(data.get(section, {}) or {})
        return getattr(cfg, name)
    return data.get(section, {}).get(name)


def _top_level_default(name: str) -> Any:
    # Read the default straight off UnravelConfig so there's one source of truth.
    defaults = UnravelConfig()
    return getattr(defaults, name, None)


def update_setting(key: str, raw_value: str, path: Path | None = None) -> Any:
    """Update one dotted setting, validate, and persist. Returns the coerced value."""
    section, name = _split_key(key)
    value = _coerce_value(section, name, raw_value)
    data = load_persistent_config(path)
    merged = dict(data)

    if section is None:
        _validate_top_level(name, value)
        merged[name] = value
    else:
        sec = dict(merged.get(section, {}) or {})
        sec[name] = value
        merged[section] = sec

        # Validate via the dataclass where possible. Build directly instead of
        # going through the *_from_dict helpers, which swallow invalid values.
        if section == "diff":
            known = {f.name for f in fields(DiffDisplayConfig)}
            DiffDisplayConfig(**{k: v for k, v in sec.items() if k in known}).validate()
        elif section == "claude_cli":
            known = {f.name for f in fields(ClaudeCLIConfig)}
            ClaudeCLIConfig(**{k: v for k, v in sec.items() if k in known}).validate()

    save_persistent_config(merged, path)
    return value


def render_config_toml(path: Path | None = None) -> str:
    """Return the current on-disk config as a TOML string (with defaults filled in)."""
    data = load_persistent_config(path)
    # Surface defaults for unset sections so `unravel conf` shows the full picture.
    merged = dict(data)
    merged.setdefault("provider", UnravelConfig().provider)
    merged["diff"] = asdict(_diff_config_from_dict(data.get("diff", {}) or {}))
    merged["claude_cli"] = asdict(
        _claude_cli_config_from_dict(data.get("claude_cli", {}) or {})
    )
    return _dump_toml(merged)


# ---------------------------------------------------------------------------
# load_config()
# ---------------------------------------------------------------------------


def load_config(**cli_overrides: str | int | None) -> UnravelConfig:
    persistent = load_persistent_config()

    default_provider = str(persistent.get("provider") or "auto")
    provider = (
        cli_overrides.get("provider")
        or os.environ.get("UNRAVEL_PROVIDER")
        or default_provider
    )
    model = cli_overrides.get("model") or os.environ.get("UNRAVEL_MODEL")
    api_key = cli_overrides.get("api_key") or None
    thinking_budget = cli_overrides.get("thinking_budget") or os.environ.get(
        "UNRAVEL_THINKING_BUDGET", 10_000
    )
    max_output_tokens = cli_overrides.get("max_output_tokens") or os.environ.get(
        "UNRAVEL_MAX_OUTPUT_TOKENS", 16_000
    )

    diff_cfg = _diff_config_from_dict(persistent.get("diff", {}) or {})
    claude_cli_cfg = _claude_cli_config_from_dict(persistent.get("claude_cli", {}) or {})

    return UnravelConfig(
        provider=str(provider),
        api_key=str(api_key) if api_key else None,
        model=str(model) if model else None,
        thinking_budget=int(thinking_budget),
        max_output_tokens=int(max_output_tokens),
        diff=diff_cfg,
        claude_cli=claude_cli_cfg,
    )
