# Analog phone setup (e.g. Pashaphone KX-T8001CID)

An ordinary corded phone, the kind that plugs into a wall phone socket, can't talk to a computer by itself.
It needs an **ATA** (analog telephone adapter): a small box with a network port on one side and a phone
socket on the other. The ATA registers to Asterisk as extension 200 and the phone plugs into it.

**Buy:** a **Grandstream HT801** (one phone port, the cheapest good one) or HT802 (two ports). Get a plain retail
unit, not one locked to a phone provider. Other unlocked SIP ATAs work the same way, with different menu names.

## What you get, and what you don't

| Works | Instead of |
|---|---|
| Claude rings you, you answer and speak | |
| Caller ID: the session's extension (e.g. `301`) as the number, plus `repo/branch` if the phone shows names | |
| Dialling sessions (301-399), operator (0), all-hands (9), voicemail (500), echo test (600) | |
| Message waiting: **stutter dial tone** when you pick up (the adapter plays it) | the T31P's message light |
| | per-repo ringtones (a Yealink feature) |
| | the session list on the phone's screen: use the operator (dial 0, say the repo) or `phone list` |
| | the Message key: dial 500 |

## 1. Wire it up

1. ATA's **Internet/LAN** port → router, with a network cable. ATA's power adapter → wall.
2. The phone's line cord → ATA's **Phone** port (not the wall socket).
3. Pick up the handset: you should hear a tone from the ATA (not yet a working dial tone until step 3).

## 2. Find the ATA and log in

- Its address: your router's list of connected devices, or pick up the phone, dial `***`, then `02`: it reads
  out its IP address.
- Open `http://<ata-ip>` in a browser. Log in as `admin` with the password printed on the label underneath
  (older units: `admin`). Change the password when asked.

## 3. Register as extension 200

Get the SIP password from WSL (or the Mac): `phone secret sip`. The server address is the computer's LAN IP
(`phone status` prints it; `lan_ip` in config.toml pins it).

**FXS Port** (HT801: *FXS Port* tab; HT802: *FXS Port 1*):

| Field | Value |
|---|---|
| Account Active | Yes |
| Primary SIP Server | the computer's LAN IP, e.g. `192.168.1.50` |
| Outbound Proxy | empty |
| SIP Transport | UDP |
| NAT Traversal | No |
| SIP User ID | `200` |
| Authenticate ID | `200` |
| Authenticate Password | output of `phone secret sip` |
| Name | anything, e.g. `Desk` |
| SIP Registration | Yes |
| Send SUBSCRIBE for MWI | No (Asterisk sends the message-waiting signal unprompted) |
| Preferred Vocoder | choice 1: **G.722**, choice 2: PCMU, choice 3: PCMA |
| DTMF | **RFC2833** first; In-audio and SIP INFO off (needed so `#` and `7` work in voicemail) |
| Dial Plan | `{ 0 \| 9 \| [2-6]xx }` (dials the moment a full extension is in, no waiting) |
| Caller ID Scheme | Bellcore/Telcordia; if the phone's screen stays blank on a call, try ETSI-FSK, then ETSI-DTMF |
| Stutter dial tone / MWI tone | On (that's the "you have voicemail" signal) |

Apply, and reboot the ATA if it asks. Its status page should show the account **Registered**, and
`phone status` should list a contact for 200.

## 4. Settings on the computer

In `~/.claude-phone/config.toml`:

```toml
ring_ext = "200"      # the ATA
callerid_max = 15     # analog caller ID carries at most 15 characters of name
```

then `phone restart daemon`.

## 5. Test

1. Pick up, dial **600**: you should hear yourself (echo test). **601** plays a steady tone.
2. Start a Claude Code session (in tmux on WSL), ask it to ring you. The phone rings and shows `301`.
3. Hang up, dial the session's extension, speak, hang up: your words appear in that session.

## Troubleshooting

- **Dial tone is fast/odd and dialling does nothing:** not registered. Check the IP, password, and on WSL the
  firewall rule ([windows-wsl.md](windows-wsl.md) step 2).
- **"I didn't catch anything" although you spoke:** the handset is quiet. In the ATA's FXS settings raise the
  transmit audio gain (*Audio Gain*/*Tx Gain*) by 3-6 dB.
- **No caller ID on the screen:** try the other Caller ID schemes above. Some phones only show the number.
- **`#` doesn't end a recording:** DTMF must be RFC2833.
