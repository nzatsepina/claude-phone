"""Paths and settings. Settings come from ~/.claude-phone/config.toml (see config.example.toml)."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("CLAUDE_PHONE_HOME", Path.home() / ".claude-phone"))
REPO = Path(__file__).resolve().parent.parent
# macOS: iTerm2, `say`, the keychain, launchd. Anything else (Linux, Windows via WSL): tmux, Piper, a secrets file, systemd.
MAC = sys.platform == "darwin"

ASTERISK_PREFIX = HOME / "asterisk"
ASTERISK_BIN = ASTERISK_PREFIX / "sbin" / "asterisk"
ASTERISK_ETC = HOME / "etc" / "asterisk"
# macOS unix socket paths are capped at 104 chars, so the run dir must be short.
ASTERISK_RUN = Path("/tmp/cphone")
DB_PATH = HOME / "registry.db"
SOUNDS = HOME / "sounds"
RECORDINGS = HOME / "recordings"
MODELS = HOME / "models"
VOICES = HOME / "voices"  # Piper voice models
LOGS = HOME / "logs"
LOG_FILE = LOGS / "phone.log"
CONFIG_FILE = HOME / "config.toml"


@dataclass
class Settings:
    # Who the phone is for. Spoken and typed as this name; the MCP tools become call_<name> and notify_<name>.
    owner_name: str = "the user"
    # Empty: this computer's address on its default route, and that /24. Pin both once it has a DHCP reservation.
    lan_ip: str = ""
    lan_cidr: str = ""
    desk_ext: str = "200"
    softphone_ext: str = "201"
    # Which endpoint call_<owner> rings. Switch to softphone_ext while testing on Linphone.
    ring_ext: str = "200"
    voicemail_ext: str = "500"
    allhands_ext: str = "9"
    operator_ext: str = "0"
    operator_provider: str = "say" if MAC else "piper"
    operator_voice: str = "Shelley (English (UK))" if MAC else "en_GB-cori-medium"
    first_session_ext: int = 301  # not 1xx: UK 101 is the police, 111 the NHS
    last_session_ext: int = 399
    ari_port: int = 8088
    daemon_port: int = 8765
    whisper_port: int = 8910
    whisper_model: str = "ggml-large-v3-turbo-q5_0.bin"  # vs base.en on 23 real clips: same or better, 0.3 s each
    ring_seconds: int = 25
    record_seconds: int = 60
    callerid_max: int = 17  # T31P shows 17 chars before scrolling (tested 2026-10-09)
    tts_provider: str = "say" if MAC else "piper"
    say_voice: str = "Daniel"
    piper_voice: str = "en_GB-alan-medium"  # https://rhasspy.github.io/piper-samples/
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model: str = "eleven_turbo_v2_5"
    # repo name -> {"provider": ..., "voice": ...}
    repo_voices: dict = field(default_factory=dict)
    # Phonebook for the T31P's Directory: the one listener on the LAN, limited to lan_cidr.
    phonebook_port: int = 8766
    # repo name -> T31P ringtone 1-8. Unlisted repos get a stable pick from their name.
    repo_ringtones: dict = field(default_factory=dict)
    # Push to the ntfy app when a call is missed. The topic is a secret (`phone push`).
    ntfy_server: str = "https://ntfy.sh"
    push_text: bool = True  # include the question/announcement; False sends only who called

    @property
    def owner(self) -> str:
        """owner_name for the start of a sentence."""
        return self.owner_name[:1].upper() + self.owner_name[1:]

    @property
    def owner_slug(self) -> str:
        """'Sam Lee' -> 'sam_lee', 'the user' -> 'user': the suffix of the MCP tool names."""
        name = re.sub(r"^the\s+", "", self.owner_name.strip().lower())
        return re.sub(r"[^a-z0-9]+", "_", name).strip("_") or "user"

    @property
    def ari_url(self) -> str:
        return f"http://127.0.0.1:{self.ari_port}/ari"

    @property
    def daemon_url(self) -> str:
        return f"http://127.0.0.1:{self.daemon_port}"

    @property
    def whisper_url(self) -> str:
        return f"http://127.0.0.1:{self.whisper_port}"


def load() -> Settings:
    s = Settings()
    if CONFIG_FILE.exists():
        data = tomllib.loads(CONFIG_FILE.read_text())
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
    if not s.lan_ip:
        s.lan_ip = detect_lan_ip() or ""
    if s.lan_ip and not s.lan_cidr:
        s.lan_cidr = s.lan_ip.rsplit(".", 1)[0] + ".0/24"
    return s


def bound_ip() -> str | None:
    """The address the generated Asterisk config listens on, which stays put when a detected lan_ip moves."""
    conf = ASTERISK_ETC / "pjsip.conf"
    m = re.search(r"^bind=([\d.]+):", conf.read_text(), re.M) if conf.exists() else None
    return m.group(1) if m else None


def detect_lan_ip() -> str | None:
    """IPv4 address of the interface on this computer's default route."""
    try:
        if not MAC:  # Connecting a UDP socket sends nothing but picks the default route's source address.
            # Under WSL, mirrored networking makes that Windows' LAN address.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
                sk.connect(("192.0.2.1", 9))
                ip = sk.getsockname()[0]
            return ip if ip != "0.0.0.0" else None
        route = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
        iface = next(line.split(":", 1)[1].strip() for line in route.splitlines() if "interface:" in line)
        ip = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True, timeout=5).stdout.strip()
        return ip or None
    except (StopIteration, OSError, subprocess.SubprocessError):
        return None


def current_lan_ips() -> set[str]:
    """IPv4 addresses on this computer, to spot the Wi-Fi address drifting away from lan_ip."""
    if not MAC:  # The kernel's local routes: each "|-- <ip>" followed by "/32 host LOCAL" is one of ours.
        lines = Path("/proc/net/fib_trie").read_text().splitlines()
        ips = {lines[i - 1].split()[-1] for i, line in enumerate(lines) if "/32 host LOCAL" in line}
        return {ip for ip in ips if not ip.startswith("127.")}
    out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    return {line.split()[1] for line in out.splitlines() if line.strip().startswith("inet ") and "127.0.0.1" not in line}


def ip_warning() -> str | None:
    s = load()
    ip = bound_ip() or s.lan_ip
    if not ip:
        return "This computer has no network address, so the desk phone can't be reached."
    if ip in current_lan_ips():
        return None
    return (f"This computer doesn't have {ip}, so the desk phone can't be reached: calls go to voicemail "
            f"and missed-call pushes. Away from home, that's expected. If the home address changed for good, set "
            f"lan_ip in {CONFIG_FILE}, run `phone restart asterisk`, and update the SIP server on the phones.")


def ensure_dirs() -> None:
    for d in (HOME, ASTERISK_ETC, SOUNDS, RECORDINGS, MODELS, VOICES, LOGS):
        d.mkdir(parents=True, exist_ok=True)
