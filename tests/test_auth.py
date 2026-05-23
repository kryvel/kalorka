from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from kalorka.auth import (
    Credentials,
    SessionCache,
    _read_config_file,
    load_credentials,
)
from kalorka.exceptions import ConfigError


class TestLoadCredentials:
    def test_uses_constructor_args(self) -> None:
        creds = load_credentials(email="user@example.com", password="pw")
        assert creds == Credentials("user@example.com", "pw")

    def test_uses_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALORKA_EMAIL", "env@example.com")
        monkeypatch.setenv("KALORKA_PASSWORD", "envpw")
        creds = load_credentials()
        assert creds == Credentials("env@example.com", "envpw")

    def test_raises_when_nothing_configured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("KALORKA_EMAIL", raising=False)
        monkeypatch.delenv("KALORKA_PASSWORD", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        with (
            patch("kalorka.auth._read_keychain", return_value=None),
            pytest.raises(ConfigError, match="No credentials"),
        ):
            load_credentials()


class TestConfigFile:
    def test_reads_valid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "creds"
        path.write_text("file@example.com\nfilepw\n")
        path.chmod(0o600)
        creds = _read_config_file(path)
        assert creds == Credentials("file@example.com", "filepw")

    def test_rejects_loose_permissions(self, tmp_path: Path) -> None:
        path = tmp_path / "creds"
        path.write_text("a@b.com\npw\n")
        path.chmod(0o644)
        with pytest.raises(ConfigError, match="too-permissive"):
            _read_config_file(path)

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _read_config_file(tmp_path / "missing") is None

    def test_rejects_short_file(self, tmp_path: Path) -> None:
        path = tmp_path / "creds"
        path.write_text("only_one_line\n")
        path.chmod(0o600)
        with pytest.raises(ConfigError, match="email on line 1"):
            _read_config_file(path)


class TestSessionCache:
    def test_round_trip(self, tmp_path: Path) -> None:
        cache = SessionCache(tmp_path / "session.json", ttl_seconds=3600)
        cache.save({"sid": "abc"})
        assert cache.load() == {"sid": "abc"}

    def test_returns_none_when_expired(self, tmp_path: Path) -> None:
        cache = SessionCache(tmp_path / "session.json", ttl_seconds=3600)
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"cookies": {"sid": "x"}, "expires": time.time() - 1}))
        assert cache.load() is None

    def test_returns_none_on_corrupted_file(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        path.write_text("not json")
        cache = SessionCache(path, ttl_seconds=3600)
        assert cache.load() is None

    def test_clear(self, tmp_path: Path) -> None:
        cache = SessionCache(tmp_path / "session.json", ttl_seconds=3600)
        cache.save({"sid": "abc"})
        cache.clear()
        assert cache.load() is None

    def test_save_uses_strict_permissions(self, tmp_path: Path) -> None:
        path = tmp_path / "session.json"
        cache = SessionCache(path, ttl_seconds=3600)
        cache.save({"sid": "abc"})
        assert path.stat().st_mode & 0o777 == 0o600
