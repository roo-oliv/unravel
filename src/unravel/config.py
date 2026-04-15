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
}

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
class UnravelConfig:
    provider: str = "anthropic"
    api_key: str | None = None
    model: str | None = None
    thinking_budget: int = 10_000
    max_output_tokens: int = 16_000
    diff: DiffDisplayConfig = field(default_factory=DiffDisplayConfig)

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


# ---------------------------------------------------------------------------
# Dotted-key helpers (for `unravel conf get/set`)
# ---------------------------------------------------------------------------


_SCHEMA: dict[str, dict[str, type]] = {
    "diff": {
        "wrap_mode": str,
        "syntax_highlight": bool,
        "show_line_numbers": bool,
        "theme": str,
    },
}


def _split_key(key: str) -> tuple[str, str]:
    if "." not in key:
        raise ValueError(
            f"Setting key must be of the form 'section.name' (got {key!r})"
        )
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


def _coerce_value(section: str, name: str, raw: str) -> Any:
    expected = _SCHEMA[section][name]
    if expected is bool:
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(
            f"Expected boolean for {section}.{name}, got {raw!r}"
        )
    if expected is int:
        return int(raw)
    return raw


def get_setting(key: str, path: Path | None = None) -> Any:
    section, name = _split_key(key)
    data = load_persistent_config(path)
    if section == "diff":
        cfg = _diff_config_from_dict(data.get(section, {}) or {})
        return getattr(cfg, name)
    return data.get(section, {}).get(name)


def update_setting(key: str, raw_value: str, path: Path | None = None) -> Any:
    """Update one dotted setting, validate, and persist. Returns the coerced value."""
    section, name = _split_key(key)
    value = _coerce_value(section, name, raw_value)
    data = load_persistent_config(path)
    merged = dict(data)
    sec = dict(merged.get(section, {}) or {})
    sec[name] = value
    merged[section] = sec

    # Validate via the dataclass where possible. Build directly instead of
    # going through _diff_config_from_dict, which swallows invalid values.
    if section == "diff":
        known = {f.name for f in fields(DiffDisplayConfig)}
        DiffDisplayConfig(**{k: v for k, v in sec.items() if k in known}).validate()

    save_persistent_config(merged, path)
    return value


def render_config_toml(path: Path | None = None) -> str:
    """Return the current on-disk config as a TOML string (with defaults filled in)."""
    data = load_persistent_config(path)
    # Surface defaults for unset sections so `unravel conf` shows the full picture.
    diff_section = data.get("diff", {}) or {}
    diff_cfg = _diff_config_from_dict(diff_section)
    merged = dict(data)
    merged["diff"] = asdict(diff_cfg)
    return _dump_toml(merged)


# ---------------------------------------------------------------------------
# load_config()
# ---------------------------------------------------------------------------


def load_config(**cli_overrides: str | int | None) -> UnravelConfig:
    persistent = load_persistent_config()

    provider = cli_overrides.get("provider") or os.environ.get("UNRAVEL_PROVIDER", "anthropic")
    model = cli_overrides.get("model") or os.environ.get("UNRAVEL_MODEL")
    api_key = cli_overrides.get("api_key") or None
    thinking_budget = cli_overrides.get("thinking_budget") or os.environ.get(
        "UNRAVEL_THINKING_BUDGET", 10_000
    )
    max_output_tokens = cli_overrides.get("max_output_tokens") or os.environ.get(
        "UNRAVEL_MAX_OUTPUT_TOKENS", 16_000
    )

    diff_cfg = _diff_config_from_dict(persistent.get("diff", {}) or {})

    return UnravelConfig(
        provider=str(provider),
        api_key=str(api_key) if api_key else None,
        model=str(model) if model else None,
        thinking_budget=int(thinking_budget),
        max_output_tokens=int(max_output_tokens),
        diff=diff_cfg,
    )
