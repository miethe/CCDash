"""Tests for ccdash_cli.runtime.config."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ccdash_cli.runtime.config import ConfigStore, TargetConfig, resolve_target


class TestConfigStore:
    def test_default_config_path_xdg(self, tmp_path, monkeypatch):
        """XDG_CONFIG_HOME is respected."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert ConfigStore.default_config_path() == tmp_path / "ccdash" / "config.toml"

    def test_default_config_path_fallback(self, monkeypatch):
        """Without XDG_CONFIG_HOME the default falls back to ~/.config."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = ConfigStore.default_config_path()
        assert result == Path.home() / ".config" / "ccdash" / "config.toml"

    def test_load_missing_file(self, tmp_path):
        """Missing config file returns empty dict, no error."""
        store = ConfigStore(config_path=tmp_path / "nonexistent.toml")
        assert store.load() == {}

    def test_add_and_list_targets(self, tmp_path):
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("staging", "https://staging.example.com", token_ref="stg-tok", project="myproj")
        targets = store.list_targets()
        assert "staging" in targets
        assert targets["staging"]["url"] == "https://staging.example.com"
        assert targets["staging"]["token_ref"] == "stg-tok"
        assert targets["staging"]["project"] == "myproj"

    def test_add_target_without_optional_fields(self, tmp_path):
        """add_target with only name+url omits token_ref and project keys."""
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("minimal", "http://minimal.local")
        record = store.get_target("minimal")
        assert record is not None
        assert record["url"] == "http://minimal.local"
        assert "token_ref" not in record
        assert "project" not in record

    def test_add_target_overwrites_existing(self, tmp_path):
        """Adding a target with the same name replaces the old record."""
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("prod", "http://old.example.com")
        store.add_target("prod", "http://new.example.com", project="new-proj")
        record = store.get_target("prod")
        assert record is not None
        assert record["url"] == "http://new.example.com"
        assert record.get("project") == "new-proj"

    def test_get_target_unknown_returns_none(self, tmp_path):
        store = ConfigStore(config_path=tmp_path / "empty.toml")
        assert store.get_target("does-not-exist") is None

    def test_remove_target(self, tmp_path):
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("temp", "http://temp.local")
        assert store.remove_target("temp") is True
        assert store.get_target("temp") is None
        assert store.remove_target("temp") is False

    def test_remove_active_clears_default(self, tmp_path):
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("prod", "https://prod.example.com")
        store.set_active_target("prod")
        assert store.get_active_target_name() == "prod"
        store.remove_target("prod")
        assert store.get_active_target_name() == "local"

    def test_remove_non_active_preserves_active(self, tmp_path):
        """Removing an inactive target does not touch the active_target pointer."""
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("a", "http://a.local")
        store.add_target("b", "http://b.local")
        store.set_active_target("a")
        store.remove_target("b")
        assert store.get_active_target_name() == "a"

    def test_active_target_default(self, tmp_path):
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        assert store.get_active_target_name() == "local"

    def test_set_active_target(self, tmp_path):
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("staging", "https://staging.example.com")
        store.set_active_target("staging")
        assert store.get_active_target_name() == "staging"

    def test_config_persists_across_instances(self, tmp_path):
        """Data written by one ConfigStore instance is visible to a fresh one."""
        path = tmp_path / "config.toml"
        store1 = ConfigStore(config_path=path)
        store1.add_target("shared", "http://shared.local")
        store1.set_active_target("shared")

        store2 = ConfigStore(config_path=path)
        assert store2.get_target("shared") is not None
        assert store2.get_active_target_name() == "shared"

    def test_file_permissions(self, tmp_path):
        """Config file is created with restricted permissions."""
        path = tmp_path / "config.toml"
        store = ConfigStore(config_path=path)
        store.add_target("test", "http://test.local")
        if os.name != "nt":
            mode = path.stat().st_mode
            assert not (mode & stat.S_IROTH), "File should not be world-readable"

    def test_path_property(self, tmp_path):
        """The .path property returns the configured path."""
        expected = tmp_path / "sub" / "config.toml"
        store = ConfigStore(config_path=expected)
        assert store.path == expected


class TestResolveTarget:
    def test_implicit_local_default(self, tmp_path, monkeypatch):
        """No config, no env -> implicit local default."""
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "empty.toml")
        target = resolve_target(config_store=store)
        assert target.name == "local"
        assert target.url == "http://localhost:8000"
        assert target.is_implicit_local is True
        assert target.token is None

    def test_target_flag_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        store.add_target("staging", "https://staging.example.com")
        target = resolve_target(target_flag="staging", config_store=store)
        assert target.name == "staging"
        assert target.url == "https://staging.example.com"
        assert target.is_implicit_local is False

    def test_target_flag_takes_priority_over_env(self, tmp_path, monkeypatch):
        """--target flag wins over CCDASH_TARGET env var."""
        monkeypatch.setenv("CCDASH_TARGET", "env-target")
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        store.add_target("flag-target", "http://flag.local")
        store.add_target("env-target", "http://env.local")
        target = resolve_target(target_flag="flag-target", config_store=store)
        assert target.name == "flag-target"

    def test_env_target_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CCDASH_TARGET", "staging")
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        store.add_target("staging", "https://staging.example.com")
        target = resolve_target(config_store=store)
        assert target.name == "staging"

    def test_env_url_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.setenv("CCDASH_URL", "http://custom:9999")
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        target = resolve_target(config_store=store)
        assert target.url == "http://custom:9999"

    def test_env_token_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.setenv("CCDASH_TOKEN", "secret-tok")
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        target = resolve_target(config_store=store)
        assert target.token == "secret-tok"

    def test_env_project_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.setenv("CCDASH_PROJECT", "my-proj")
        store = ConfigStore(config_path=tmp_path / "config.toml")
        target = resolve_target(config_store=store)
        assert target.project == "my-proj"

    def test_url_trailing_slash_stripped(self, tmp_path, monkeypatch):
        """Resolved URL never has a trailing slash."""
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.setenv("CCDASH_URL", "http://custom:9999/")
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        target = resolve_target(config_store=store)
        assert not target.url.endswith("/")

    def test_explicit_local_target_not_implicit(self, tmp_path, monkeypatch):
        """A named 'local' entry in config is not treated as implicit."""
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "config.toml")
        store.add_target("local", "http://localhost:8000")
        store.set_active_target("local")
        target = resolve_target(config_store=store)
        # active_target is explicitly set in [defaults], so is_implicit_local is False
        assert target.name == "local"
        assert target.is_implicit_local is False

    def test_unknown_target_flag_exits(self, tmp_path, monkeypatch):
        """--target for unknown name raises SystemExit."""
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "empty.toml")
        with pytest.raises(SystemExit):
            resolve_target(target_flag="nonexistent", config_store=store)

    def test_resolve_returns_target_config(self, tmp_path, monkeypatch):
        """resolve_target always returns a TargetConfig instance."""
        monkeypatch.delenv("CCDASH_TARGET", raising=False)
        monkeypatch.delenv("CCDASH_URL", raising=False)
        monkeypatch.delenv("CCDASH_TOKEN", raising=False)
        monkeypatch.delenv("CCDASH_PROJECT", raising=False)
        store = ConfigStore(config_path=tmp_path / "empty.toml")
        result = resolve_target(config_store=store)
        assert isinstance(result, TargetConfig)
