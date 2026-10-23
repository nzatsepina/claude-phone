# Windows (WSL 2) setup

Everything runs inside WSL 2 on Windows, in place of the Mac. The pieces swap like this:

| On a Mac | On Windows/WSL |
|---|---|
| iTerm2 tabs (typed into with AppleScript) | **tmux** panes inside WSL (typed into with `tmux send-keys`) |
| macOS `say` voices | **Piper** voices: free, offline, downloaded on first use |
| login keychain | `~/.claude-phone/secrets.json`, readable only by you |
| launchd | systemd user services |
| Homebrew `whisper-cpp` | `scripts/build-whisper.sh` builds it (CPU, or an NVIDIA GPU) |

Claude Code must run **inside WSL, inside tmux**. Sessions started in PowerShell or in a plain WSL terminal
outside tmux get no extension, because there is nothing to type your answers into.

> This port hasn't been run on real Windows hardware yet. The parts that touch WSL networking (steps 1 and 2)
> are the likeliest to need a tweak; `phone status` and `~/.claude-phone/logs/` will show where it's stuck.

## What you need

- **Windows 11 22H2 or later**, for WSL's mirrored networking. Windows 10's WSL can't receive the UDP
  traffic a phone sends, so it won't work there.
- WSL 2 with Ubuntu 24.04 (`wsl --install -d Ubuntu-24.04` in PowerShell if you don't have it).
- The phone on the same home network as the PC, plugged into the router. An analog phone needs an adapter
  first: [analog-phone.md](analog-phone.md).
- About 2 GB of disk (Asterisk build, speech model, voices).

## 1. Mirrored networking

The phone has to reach Asterisk at the PC's own LAN address. By default WSL sits behind its own private
network where the phone can't see it; mirrored mode gives WSL the PC's real address.

In Windows, create or edit `%UserProfile%\.wslconfig` (e.g. `C:\Users\you\.wslconfig`):

```ini
[wsl2]
networkingMode=mirrored
```

Then in PowerShell: `wsl --shutdown`, and open Ubuntu again. Check it worked: in WSL,
`hostname -I` should now show the same `192.168.x.x` address that `ipconfig` shows in Windows.

## 2. Let the phone in through the firewall

In **PowerShell as Administrator** (SIP on 5060, call audio on 10000-10100):

```powershell
New-NetFirewallHyperVRule -Name claude-phone -DisplayName "claude-phone (SIP and call audio)" `
  -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol UDP -LocalPorts 5060,10000-10100 -Action Allow
```

Also make sure Windows calls your home network **Private** (Settings → Network & internet → your connection).

## 3. systemd

New Ubuntu installs have it already. Check `/etc/wsl.conf` contains:

```ini
[boot]
systemd=true
```

(If you had to add it: `wsl --shutdown` in PowerShell and reopen.) Then, so the phone services run
without a login session:

```sh
sudo loginctl enable-linger "$USER"
```

## 4. Packages

```sh
sudo apt update
sudo apt install -y build-essential pkg-config cmake git curl bzip2 patch \
  libssl-dev libedit-dev uuid-dev libxml2-dev libsqlite3-dev \
  python3-venv tmux sox
```

Keep the repo in the Linux filesystem (`~/claude-phone`), not under `/mnt/c`, which is much slower.

```sh
cd ~ && git clone https://github.com/nzatsepina/claude-phone && cd claude-phone
```

## 5. Build and install

```sh
scripts/build-asterisk.sh        # ~10-20 min
scripts/build-whisper.sh         # ~3 min; GGML_CUDA=1 scripts/build-whisper.sh with an NVIDIA GPU + CUDA toolkit
python3 -m venv .venv && .venv/bin/pip install -e .   # includes Piper
mkdir -p ~/.claude-phone && cp config.example.toml ~/.claude-phone/config.toml
```

Edit `~/.claude-phone/config.toml`: set `owner_name`, and for an analog phone `callerid_max = 15`.
Once the router has reserved the PC's address, pin it there as `lan_ip`.

```sh
.venv/bin/phone install-services   # downloads the ~550 MB speech model on first run
.venv/bin/phone status
.venv/bin/phone say "Hello from the phone line"   # first run downloads the Piper voice (~60 MB)
```

`phone secret sip` prints the password the phone (or adapter) registers with.

**Speed check:** dial 600 once the phone is set up (echo test), then ring a session. If transcription
is slow on your CPU (more than ~3 s after you hang up; `phone.log` shows the timings), switch to a smaller model:
`whisper_model = "ggml-small.en-q5_1.bin"` in config.toml, then `phone install-services` again.

## 6. Claude Code in WSL, inside tmux

Install Claude Code inside WSL (`curl -fsSL https://claude.ai/install.sh | bash`), then wire it up as in the
README's **Claude Code wiring**, with the WSL path, e.g. `/home/you/claude-phone/.venv/bin/phone`:

```sh
claude mcp add --scope user claude-phone -- "$HOME/claude-phone/.venv/bin/phone" mcp
```

plus the four hooks in `~/.claude/settings.json` (inside WSL), and the
[CLAUDE.md snippet](claude-md-snippet.md) in `~/.claude/CLAUDE.md`.

Then work in tmux, one Claude Code session per window or pane:

```sh
tmux new -s work      # then: cd ~/some-repo && claude
                      # Ctrl-b c for another window, Ctrl-b n / p to switch, Ctrl-b d to detach
```

`phone list` shows each session's extension. Detached tmux sessions still work: the phone types into them
whether or not a window is showing them.

## 7. Keeping it running

The services start whenever WSL starts. Windows stops WSL a little while after its last terminal closes,
which is fine while you're working (your Claude Code sessions keep it up). To have the phone line ready
from Windows login, add a Task Scheduler task: trigger **At log on**, action
`wsl.exe -d Ubuntu-24.04 --exec sleep infinity`, and tick **Run whether user is logged on or not** so no
window appears.

## Voices

The default voices are Piper's British `en_GB-alan-medium` (calls) and `en_GB-cori-medium` (the operator on 0).
Listen to others at https://rhasspy.github.io/piper-samples/ and set them by name:

```toml
piper_voice = "en_US-lessac-medium"
operator_voice = "en_GB-jenny_dioco-medium"
```

Each voice downloads on first use. ElevenLabs works exactly as on a Mac (README → Voices); the API key
goes in `ELEVENLABS_API_KEY` or in `~/.claude-phone/secrets.json` under `"elevenlabs"`.

## Troubleshooting

- **Phone won't register:** `hostname -I` in WSL must match the PC's Windows address (step 1), the firewall
  rule must exist (step 2), and `phone status` must show asterisk running. Then the adapter's or phone's status page.
- **Rings, but no audio:** UDP 10000-10100 is blocked: step 2.
- **Text isn't typed:** the session must be in tmux (`echo $TMUX` in that pane prints something) and in `phone list`.
  Restart the Claude Code session if it was started before the hooks were added.
- **Services:** `systemctl --user status claude-phone-daemon`, logs in `~/.claude-phone/logs/`.
