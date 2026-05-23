"""Credential resolution and on-disk session cache.

Credentials are looked up in this order:

1. Constructor args (``email`` / ``password``)
2. ``KALORKA_EMAIL`` / ``KALORKA_PASSWORD`` env vars
3. macOS Keychain entries ``kalorka-email`` / ``kalorka-password``
4. ``~/.config/kalorka/credentials`` (or ``$XDG_CONFIG_HOME/kalorka/...``),
   a two-line file: email on line 1, password on line 2. Permissions are
   enforced to 0600 - anything looser is refused.

The session cache lives in ``$KALORKA_STATE_DIR`` (default
``~/.local/state/kalorka``) as ``session.json``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from kalorka.exceptions import ConfigError


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


def state_dir() -> Path:
    """Return the directory used for cached session cookies."""
    override = os.environ.get("KALORKA_STATE_DIR")
    if override:
        path = Path(override).expanduser()
    else:
        base = os.environ.get("XDG_STATE_HOME") or "~/.local/state"
        path = Path(base).expanduser() / "kalorka"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "kalorka" / "credentials"


def load_credentials(
    *, email: str | None = None, password: str | None = None
) -> Credentials:
    """Resolve credentials, raising ``ConfigError`` if none can be found."""
    if email and password:
        return Credentials(email, password)

    env_email = os.environ.get("KALORKA_EMAIL")
    env_password = os.environ.get("KALORKA_PASSWORD")
    if env_email and env_password:
        return Credentials(env_email, env_password)

    if sys.platform == "darwin":
        keychain = _read_keychain()
        if keychain is not None:
            return keychain

    file_creds = _read_config_file(config_path())
    if file_creds is not None:
        return file_creds

    raise ConfigError(
        "No credentials found. Set KALORKA_EMAIL + KALORKA_PASSWORD, "
        "store them in macOS Keychain under 'kalorka-email' / "
        "'kalorka-password', or write them to "
        f"{config_path()} (line 1 = email, line 2 = password, mode 0600)."
    )


def _read_keychain() -> Credentials | None:
    """Pull both halves out of Keychain. Returns None if either is missing."""
    try:
        email = subprocess.check_output(
            ["security", "find-generic-password", "-s", "kalorka-email", "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        password = subprocess.check_output(
            ["security", "find-generic-password", "-s", "kalorka-password", "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not email or not password:
        return None
    return Credentials(email, password)


def _read_config_file(path: Path) -> Credentials | None:
    if not path.exists():
        return None
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise ConfigError(
            f"{path} has too-permissive mode {mode:o}; run `chmod 600 {path}`"
        )
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) < 2:
        raise ConfigError(f"{path} must have email on line 1 and password on line 2")
    return Credentials(lines[0], lines[1])


class SessionCache:
    """JSON-backed cookie store with a soft TTL."""

    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def load(self) -> dict[str, str] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        expires = data.get("expires")
        if not isinstance(expires, (int, float)) or expires < time.time():
            return None
        cookies = data.get("cookies")
        if not isinstance(cookies, dict):
            return None
        return {str(k): str(v) for k, v in cookies.items()}

    def save(self, cookies: dict[str, str]) -> None:
        payload = {"cookies": cookies, "expires": time.time() + self.ttl_seconds}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a tempfile then rename so a crash mid-write doesn't corrupt the cache.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
