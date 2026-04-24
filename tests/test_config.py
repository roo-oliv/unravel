"""Tests for persistent config file loading + mutation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from unravel.config import (
    DiffDisplayConfig,
    _diff_config_from_dict,
    _dump_toml,
    config_path,
    get_setting,
    load_persistent_config,
    render_config_toml,
    save_persistent_config,
    update_setting,
)


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "unravel" / "config.toml"


class TestConfigPath:
    def test_honors_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "x"))
        assert config_path() == tmp_path / "x" / "unravel" / "config.toml"

    def test_falls_back_to_home(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert config_path() == Path.home() / ".config" / "unravel" / "config.toml"


class TestLoadPersistentConfig:
    def test_missing_file_returns_empty_dict(self, tmp_config: Path):
        assert load_persistent_config() == {}

    def test_roundtrip(self, tmp_config: Path):
        save_persistent_config({"diff": {"wrap_mode": "scroll"}})
        assert tmp_config.exists()
        assert load_persistent_config() == {"diff": {"wrap_mode": "scroll"}}

    def test_malformed_file_returns_empty(self, tmp_config: Path):
        tmp_config.parent.mkdir(parents=True, exist_ok=True)
        tmp_config.write_text("this is not valid toml = = =")
        assert load_persistent_config() == {}


class TestDiffConfigFromDict:
    def test_defaults_when_empty(self):
        cfg = _diff_config_from_dict({})
        assert cfg.wrap_mode == "wrap"
        assert cfg.syntax_highlight is True
        assert cfg.show_line_numbers is True
        assert cfg.theme == "monokai"

    def test_overrides_from_dict(self):
        cfg = _diff_config_from_dict(
            {"wrap_mode": "scroll", "syntax_highlight": False}
        )
        assert cfg.wrap_mode == "scroll"
        assert cfg.syntax_highlight is False

    def test_unknown_keys_ignored(self):
        cfg = _diff_config_from_dict({"bogus": "value", "wrap_mode": "scroll"})
        assert cfg.wrap_mode == "scroll"

    def test_invalid_wrap_mode_falls_back_to_defaults(self):
        cfg = _diff_config_from_dict({"wrap_mode": "bananas"})
        assert cfg.wrap_mode == "wrap"


class TestUpdateSetting:
    def test_set_string(self, tmp_config: Path):
        update_setting("diff.wrap_mode", "scroll")
        assert load_persistent_config()["diff"]["wrap_mode"] == "scroll"
        assert get_setting("diff.wrap_mode") == "scroll"

    def test_set_bool_true_variants(self, tmp_config: Path):
        for truthy in ("true", "1", "yes", "on", "True"):
            update_setting("diff.syntax_highlight", truthy)
            assert load_persistent_config()["diff"]["syntax_highlight"] is True

    def test_set_bool_false_variants(self, tmp_config: Path):
        for falsy in ("false", "0", "no", "off", "False"):
            update_setting("diff.syntax_highlight", falsy)
            assert load_persistent_config()["diff"]["syntax_highlight"] is False

    def test_rejects_unknown_section(self, tmp_config: Path):
        with pytest.raises(ValueError, match="Unknown section"):
            update_setting("bogus.key", "value")

    def test_rejects_unknown_key(self, tmp_config: Path):
        with pytest.raises(ValueError, match="Unknown setting"):
            update_setting("diff.bogus", "value")

    def test_rejects_unknown_top_level(self, tmp_config: Path):
        with pytest.raises(ValueError, match="Unknown top-level"):
            update_setting("nonsense", "value")

    def test_set_top_level_provider(self, tmp_config: Path):
        update_setting("provider", "claude-cli")
        assert load_persistent_config()["provider"] == "claude-cli"
        assert get_setting("provider") == "claude-cli"

    def test_rejects_invalid_provider(self, tmp_config: Path):
        with pytest.raises(ValueError, match="provider must be one of"):
            update_setting("provider", "bogus")

    def test_set_claude_cli_path(self, tmp_config: Path):
        update_setting("claude_cli.path", "/opt/claude")
        assert load_persistent_config()["claude_cli"]["path"] == "/opt/claude"

    def test_rejects_empty_claude_cli_path(self, tmp_config: Path):
        with pytest.raises(ValueError, match="claude_cli.path"):
            update_setting("claude_cli.path", "")

    def test_rejects_invalid_wrap_mode(self, tmp_config: Path):
        with pytest.raises(ValueError, match="wrap_mode"):
            update_setting("diff.wrap_mode", "bananas")

    def test_rejects_non_bool_for_bool_field(self, tmp_config: Path):
        with pytest.raises(ValueError, match="boolean"):
            update_setting("diff.syntax_highlight", "maybe")

    def test_preserves_other_settings(self, tmp_config: Path):
        update_setting("diff.wrap_mode", "scroll")
        update_setting("diff.theme", "dracula")
        data = load_persistent_config()
        assert data["diff"]["wrap_mode"] == "scroll"
        assert data["diff"]["theme"] == "dracula"


class TestRenderConfigToml:
    def test_surfaces_defaults_when_empty(self, tmp_config: Path):
        rendered = render_config_toml()
        assert "[diff]" in rendered
        assert 'wrap_mode = "wrap"' in rendered
        assert "syntax_highlight = true" in rendered


class TestDumpToml:
    def test_scalars_and_sections(self):
        out = _dump_toml({"top": 5, "diff": {"wrap_mode": "wrap", "b": True}})
        assert "top = 5" in out
        assert "[diff]" in out
        assert 'wrap_mode = "wrap"' in out
        assert "b = true" in out

    def test_escapes_strings(self):
        out = _dump_toml({"diff": {"theme": 'mono"kai'}})
        assert '"mono\\"kai"' in out


class TestLoadConfigIntegration:
    def test_load_config_picks_up_persistent_diff_cfg(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Avoid api-key resolution side effects by not triggering it here.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        update_setting("diff.wrap_mode", "scroll")
        from unravel.config import load_config

        cfg = load_config()
        assert isinstance(cfg.diff, DiffDisplayConfig)
        assert cfg.diff.wrap_mode == "scroll"

    def test_default_provider_is_auto(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("UNRAVEL_PROVIDER", raising=False)
        from unravel.config import load_config

        cfg = load_config()
        assert cfg.provider == "auto"

    def test_persistent_provider_respected(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("UNRAVEL_PROVIDER", raising=False)
        update_setting("provider", "claude-cli")
        from unravel.config import load_config

        cfg = load_config()
        assert cfg.provider == "claude-cli"

    def test_env_var_overrides_persistent_provider(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        update_setting("provider", "claude-cli")
        monkeypatch.setenv("UNRAVEL_PROVIDER", "anthropic")
        from unravel.config import load_config

        cfg = load_config()
        assert cfg.provider == "anthropic"

    def test_cli_override_beats_env_and_persistent(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        update_setting("provider", "claude-cli")
        monkeypatch.setenv("UNRAVEL_PROVIDER", "anthropic")
        from unravel.config import load_config

        cfg = load_config(provider="auto")
        assert cfg.provider == "auto"


def test_xdg_unset_resolves_via_home(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = config_path()
    assert str(path).endswith(os.path.join(".config", "unravel", "config.toml"))
