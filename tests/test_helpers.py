import math
import struct
import wave

from claude_phone import stt, tts
from claude_phone.daemon import SPINNER, browser_xml, caller_id
from claude_phone.config import Settings
from claude_phone.registry import Session


def test_caller_id_fits_17():
    assert caller_id("claude-phone/master", 17) == "claude-phone/mas~"
    assert caller_id("lemon-stand/feat/ags-2", 17) == "lemon-stand/ags-2"
    assert caller_id("site-be-v2", 17) == "site-be-v2"
    for label in ("a-very-long-repository-name/feature/branch", "x" * 40):
        assert len(caller_id(label, 17)) <= 17


def test_spoken_label():
    assert tts.spoken_label("lemon-stand/feat/ags-2") == "lemon stand, feat ags 2"
    assert tts.spoken_label("site-be-v2") == "site be v2"


def test_browser_xml_lists_sessions_and_escapes():
    s = Session(session_id="x", ext=301, repo="a&b", branch="main", worktree=None, cwd=None, iterm_id=None,
                status="idle", started_at=0, updated_at=0)
    xml = browser_xml([s], Settings())
    assert "<Prompt>301 a&amp;b/main</Prompt><URI>301</URI>" in xml
    assert "<Title>Claude (1 live)</Title>" in xml


def test_spinner_detects_running_turn():
    assert SPINNER.search("· Generating… (51s · ↓ 4.3k tokens · thought for 1s)")
    assert SPINNER.search("✻ Pondering… (1m 3s · esc to interrupt)")
    assert not SPINNER.search("❯ \n  ⏵⏵ auto mode on")


def _wav(path, seconds, amp):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * 300 * i / 16000)))
                               for i in range(int(16000 * seconds))))


def test_speech_gate(tmp_path):
    _wav(tmp_path / "quiet.wav", 1, 50)
    _wav(tmp_path / "voice.wav", 1, 800)  # quiet handset speech: RMS ~565
    assert stt.speech_seconds(tmp_path / "quiet.wav") == 0
    assert stt.speech_seconds(tmp_path / "voice.wav") > 0.9


def test_noise_transcripts_discarded():
    for t in ("Thank you.", "[BLANK_AUDIO]", "(silence)", "you", "..."):
        assert stt._NOISE.match(t)
    assert not stt._NOISE.match("Yes, ship it.")


def test_owner_name_sets_tool_suffix_and_sentence_case():
    assert Settings().owner_slug == "user" and Settings().owner == "The user"
    s = Settings(owner_name="Sam Lee")
    assert s.owner_slug == "sam_lee" and s.owner == "Sam Lee"


def test_lan_cidr_follows_detected_ip(monkeypatch):
    from claude_phone import config
    monkeypatch.setattr(config, "detect_lan_ip", lambda: "10.1.2.33")
    s = config.load()
    assert (s.lan_ip, s.lan_cidr) == ("10.1.2.33", "10.1.2.0/24")


def test_changing_the_default_voice_renders_new_speech(monkeypatch):
    from claude_phone import config
    rendered = []
    monkeypatch.setattr(tts.PROVIDERS["say"], "render", lambda text, voice, out: (rendered.append(voice), out.write_bytes(b"")))
    monkeypatch.setattr(config, "load", lambda: Settings(tts_provider="say", say_voice="Daniel"))
    a = tts.render("Hello there.")
    monkeypatch.setattr(config, "load", lambda: Settings(tts_provider="say", say_voice="Fiona"))
    b = tts.render("Hello there.")
    assert a != b and rendered == ["Daniel", "Fiona"]


def test_tmux_pane_ids():
    from claude_phone import inject
    tid = inject.tmux_id("/tmp/tmux-1000/default,4211,0", "%3")
    assert tid == "tmux:/tmp/tmux-1000/default:%3"
    assert inject._split(tid) == ("/tmp/tmux-1000/default", "%3")
    assert inject.tmux_id(None, "%3") is None and inject.tmux_id("/tmp/s,1,0", None) is None


def test_terminal_id_prefers_tmux_over_iterm(monkeypatch):
    from claude_phone import hooks
    monkeypatch.setenv("ITERM_SESSION_ID", "w0t1p0:ABC-123")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    assert hooks.terminal_id() == "ABC-123"
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,4211,0")
    monkeypatch.setenv("TMUX_PANE", "%7")
    assert hooks.terminal_id() == "tmux:/tmp/tmux-1000/default:%7"


def test_secrets_file_off_mac(monkeypatch):
    import os
    from claude_phone import config, keychain
    monkeypatch.setattr(config, "MAC", False)
    keychain.SECRETS_FILE.unlink(missing_ok=True)
    sip = keychain.get_or_create("sip")
    assert keychain.get_or_create("sip") == sip
    keychain.put("ntfy", "topic")
    assert (keychain.get("sip"), keychain.get("ntfy")) == (sip, "topic")
    assert os.stat(keychain.SECRETS_FILE).st_mode & 0o077 == 0
