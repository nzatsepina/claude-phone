"""Secrets live in the macOS login keychain under service 'claude-phone'. Elsewhere (Linux, WSL) there is
usually no keyring daemon running, so they live in ~/.claude-phone/secrets.json, readable only by you."""

from __future__ import annotations

import json
import os
import secrets as _secrets
import subprocess

from . import config

SERVICE = "claude-phone"
SECRETS_FILE = config.HOME / "secrets.json"


def _file() -> dict:
    try:
        return json.loads(SECRETS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def get(name: str) -> str | None:
    env = os.environ.get(f"CLAUDE_PHONE_{name.upper().replace('-', '_')}")
    if env:
        return env
    if not config.MAC:
        return _file().get(name)
    r = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def put(name: str, value: str) -> None:
    if not config.MAC:
        data = _file() | {name: value}
        SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SECRETS_FILE.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(SECRETS_FILE)
        return
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", value],
        check=True, capture_output=True,
    )


def get_or_create(name: str, nbytes: int = 12) -> str:
    v = get(name)
    if not v:
        v = _secrets.token_hex(nbytes)
        put(name, v)
    return v


def elevenlabs_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY") or get("elevenlabs")
