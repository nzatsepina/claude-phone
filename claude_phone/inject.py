"""Type text into a terminal session: an iTerm2 session via AppleScript (works with the tab unfocused and
another app in front), or a tmux pane via send-keys (Linux and WSL; works with the pane detached).
Only ever types into sessions from the registry; every attempt is logged.

A session's terminal id is iTerm2's unique id (a UUID), or "tmux:<socket>:<pane>" for tmux."""

from __future__ import annotations

import subprocess
import time

from . import config, log, registry

TMUX_PREFIX = "tmux:"

# Text then a separate CR: Claude Code's input treats a pasted trailing newline as part of the text.
_SCRIPT = r'''
on run argv
  set sid to item 1 of argv
  set mode to item 2 of argv
  -- Never launch iTerm2 just to look for a session.
  if application "iTerm2" is not running then
    if mode is "list" then return ""
    return "notfound"
  end if
  tell application "iTerm2"
    if mode is "list" then
      set ids to {}
      repeat with w in windows
        repeat with t in tabs of w
          repeat with s in sessions of t
            set end of ids to (unique id of s)
          end repeat
        end repeat
      end repeat
      set AppleScript's text item delimiters to linefeed
      return ids as text
    end if
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if unique id of s is sid then
            if mode is "read" then return contents of s
            tell s to write text (item 3 of argv) newline no
            delay 0.3
            tell s to write text (ASCII character 13) newline no
            return "sent"
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return "notfound"
end run
'''


def _osa(*args: str, timeout: float = 10) -> str:
    r = subprocess.run(["osascript", "-e", _SCRIPT, *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.rstrip("\n")


# --- tmux ---

def tmux_id(tmux_env: str | None, pane: str | None) -> str | None:
    """$TMUX is '<socket>,<server pid>,<session>' and $TMUX_PANE '%3'; together they name the pane from outside tmux."""
    if not tmux_env or not pane:
        return None
    return f"{TMUX_PREFIX}{tmux_env.rsplit(',', 2)[0]}:{pane}"


def _split(term_id: str) -> tuple[str, str]:
    socket, _, pane = term_id.removeprefix(TMUX_PREFIX).rpartition(":")
    return socket, pane


# tmux's answers when its server isn't running: every pane on that socket is gone.
_NO_SERVER = ("no server running", "error connecting to", "no such file or directory")


def _tmux(socket: str, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-S", socket, *args], capture_output=True, text=True, timeout=timeout)


def _tmux_panes(socket: str) -> set[str]:
    r = _tmux(socket, "list-panes", "-a", "-F", "#{pane_id}")
    if r.returncode != 0:
        if any(m in r.stderr.lower() for m in _NO_SERVER):
            return set()
        raise RuntimeError(r.stderr.strip())
    return {f"{TMUX_PREFIX}{socket}:{p}" for p in r.stdout.split()}


def _tmux_type(term_id: str, text: str) -> str:
    socket, pane = _split(term_id)
    if term_id not in _tmux_panes(socket):
        return "notfound"
    r = _tmux(socket, "send-keys", "-t", pane, "-l", "--", text)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    time.sleep(0.3)
    _tmux(socket, "send-keys", "-t", pane, "Enter")
    return "sent"


# --- either terminal ---

def live_terminal_ids() -> set[str]:
    ids = {x for x in _osa("-", "list").splitlines() if x} if config.MAC else set()
    sockets = {_split(s.iterm_id)[0] for s in registry.all_sessions() if (s.iterm_id or "").startswith(TMUX_PREFIX)}
    for socket in sockets:
        ids |= _tmux_panes(socket)
    return ids


def read_screen(term_id: str) -> str:
    if term_id.startswith(TMUX_PREFIX):
        socket, pane = _split(term_id)
        r = _tmux(socket, "capture-pane", "-p", "-t", pane)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        return r.stdout
    return _osa(term_id, "read")


def type_into(session: registry.Session, text: str, source: str) -> str:
    """Returns 'sent', 'notfound' or 'error:<msg>'."""
    lg = log.get("inject")
    # A single line: newlines inside would submit early.
    text = " ".join(text.split())
    if not session.iterm_id:
        result = "error:no terminal id"
    else:
        try:
            if session.iterm_id.startswith(TMUX_PREFIX):
                result = _tmux_type(session.iterm_id, text)
            else:
                result = _osa(session.iterm_id, "type", text)
        except Exception as e:
            result = f"error:{e}"
    registry.log_injection(session, source, text, result)
    lg.info("inject ext=%s %s source=%s result=%s text=%r", session.ext, session.label, source, result, text)
    return result
