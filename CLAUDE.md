# Pi Setup — Project Context

## Hardware
- **Device:** Raspberry Pi 5
- **Hostname:** `bryanfoslerpi5` / `bryanfoslerpi5.local`
- **User:** `bfosler`
- **SSH:** `ssh bfosler@bryanfoslerpi5.local` (key auth, no password)
- **OS:** Debian Trixie (13)

## Connected Devices
- **CME C2MIDI Pro** — USB MIDI controller, shows as ALSA client 24 (`C2MIDI Pro MIDI 1`)

## Quick Access URLs

| What | Local | Via Tailscale |
|---|---|---|
| Open-WebUI (chat) | http://bryanfoslerpi5.local:3000 | http://100.99.74.37:3000 |
| Petcam viewer | http://bryanfoslerpi5.local:8080 | http://100.99.74.37:8080 |
| Petcam viewer (public, no Tailscale) | — | https://bryanfoslerpi5.taildef31a.ts.net |
| Petcam stream (direct MJPEG) | http://bryanfoslerpi5.local:8080/stream | http://100.99.74.37:8080/stream |
| Ollama API | http://bryanfoslerpi5.local:11434 | http://100.99.74.37:11434 |
| Homebridge UI | http://bryanfoslerpi5.local:8581 | http://100.99.74.37:8581 |
| ntfy alerts | https://ntfy.sh/bryan-petcam-302 | — |
| SSH (local) | `ssh bfosler@bryanfoslerpi5.local` | `ssh bfosler@100.99.74.37` |

## Services
| Service | Port | Status | Notes |
|---|---|---|---|
| `rtpmidid` | UDP 5004/5005 | enabled, auto-start | Must use `--port 5004` flag or it won't bind |
| `midi-routing` | — | enabled, auto-start | Waits for Mac connection, then routes bidirectionally |
| `bt-midi` | BLE | enabled, auto-start | Pi as BLE MIDI peripheral; connects from Audio MIDI Setup → Bluetooth |
| `ollama` | 11434 | enabled, auto-start | Restricted to `127.0.0.1:11434` — override in `/etc/systemd/system/ollama.service.d/override.conf` |
| `open-webui` | 3000 | enabled, auto-start | Docker container; browser chat UI for Ollama |
| `petcam` | 8080 (stream) | enabled, auto-start | Motion detection + moondream + ntfy.sh notifications |
| `openclaw-gateway` | 18789 (ws) | enabled, **user** systemd | Telegram AI bot (Piper); restart: `systemctl --user restart openclaw-gateway` |
| `piper-logger` | — | enabled, **user** systemd | Polls OpenClaw session JSONL files → SQLite `~/.openclaw/piper_logs.db` |
| `homebridge` | 8581 (UI), 51732 (HAP) | Docker, `--restart=unless-stopped` | HomeKit bridge; config at `/opt/homebridge/config.json` |

## OpenClaw (Piper) — Telegram AI Bot
- **Bot:** `@Piper_RPi5Bot`
- **Config:** `~/.openclaw/openclaw.json`
- **API key:** `~/.openclaw/agents/main/agent/auth-profiles.json` (profile: `anthropic:manual`)
- **Model:** `claude-haiku-4-5-20251001` (primary), `claude-sonnet-4-6` (fallback)
- **Skills:** session-memory, obsidian, notion, local-infer (requires `NOTION_API_KEY` in config env block)
- **To replace API key:** `python3` REPL on Pi → `key = input('Paste key: ')` → update auth-profiles.json → restart service
- **To check logs:** `npx openclaw logs --plain --limit 50`
- **To verify model:** look for `model=` in `embedded run start` log line
- **models.json:** `~/.openclaw/agents/main/agent/models.json` — all local models must have `contextWindow: 4096` (not 131072)
- **Adding a new skill:** after creating `~/.openclaw/workspace/skills/<name>/SKILL.md`, run `touch` on the file while gateway is running to trigger skill snapshot refresh
- **local-infer skill:** `~/.openclaw/workspace/skills/local-infer/` — classification, extraction, summarization via Qwen2.5-1.5B; circuit breaker state at `~/.openclaw/local-infer-state.json`

## Piper Logging Stack
- **Logger:** `~/.openclaw/piper_logger.py` — polls `~/.openclaw/agents/main/sessions/*.jsonl` every 15s
- **DB:** `~/.openclaw/piper_logs.db` (tables: messages, sessions, errors)
- **Notion writer:** `~/.openclaw/piper_notion.py --summary | --errors | --status | --force`
- **Cron:** daily summary at 23:30, error sync hourly
- **Notion integration:** "Piper OpenClaw" (separate from Claude Code integration)
- **Obsidian output:** `~/ObsidianVault/AI Knowledge/Piper/YYYY-MM-DD.md` → syncs to Mac via Syncthing

## Security Hardening (applied 2026-03-02)
- UFW: default deny-incoming; allow SSH (22), Tailscale (41641/udp), HAP (51732 local), petcam (8080 local), Open-WebUI/Homebridge (Tailscale-only)
- SSH: `PasswordAuthentication no` (line 57 of `/etc/ssh/sshd_config`)
- Ollama: `127.0.0.1:11434` only — NOT accessible from LAN (use Tailscale if needed remotely)
- rpcbind: disabled (service + socket)

## SSH Troubleshooting
- `bryanfoslerpi5.local` mDNS sometimes fails → fall back to Tailscale IP `100.99.74.37`
- Host key error after IP change: `ssh-keygen -R 100.99.74.37`
- Multi-line Python scripts over SSH: write locally with Write tool, pipe with `ssh host "cat > /remote/path" < /local/file`

## Connected Devices
- **CME C2MIDI Pro** — USB MIDI controller, ALSA client 24 (`C2MIDI Pro MIDI 1`)
- **USB Webcam** — `/dev/video0`, used by petcam service

## Deployment
Scripts live in the repo. Clone first, then run in order:
```bash
git clone https://github.com/bryanfosler/pi-setup.git && cd pi-setup
bash setup/add-networks.sh       # fill in HOME_SSID, MAC_SHARING_SSID, MAC_SHARING_PASSWORD first
bash setup/install-ollama.sh
bash setup/install-open-webui.sh
bash setup/install-petcam.sh     # set NTFY_TOPIC in petcam/petcam.py first
bash setup/install-bt-midi.sh    # BLE MIDI peripheral (Pi BT MIDI)
bash setup/setup-hotspot.sh      # fill in HOTSPOT_PASSWORD first
```
See `docs/full-setup-guide-02.26.2026.md` for full walkthrough.

## WiFi Hotspot (Pi as AP)
`setup/setup-hotspot.sh` configures Pi as access point (run once after filling HOTSPOT_PASSWORD).
- Enable: `bash setup/switch-network.sh hotspot`
- Pi IP on hotspot: `192.168.100.1`
- Pi has no internet when in hotspot mode (one radio, no uplink)
- Disable: `bash setup/switch-network.sh home`

## BLE MIDI Key Files on Pi
- `/usr/local/lib/bt-midi/bt-midi-peripheral.py` — main script
- `/opt/bt-midi-venv/` — Python venv with python-rtmidi
- `/etc/systemd/system/bt-midi.service`
- `/etc/bluetooth/main.conf` — must have `DisablePlugins = midi` (bluez MIDI plugin conflicts with custom GATT)
- `/etc/wireplumber/wireplumber.conf.d/50-disable-bluetooth-midi.conf` — must disable `monitor.bluez-midi`

## Critical: BLE MIDI Three-Conflict Pattern
Any custom BLE MIDI GATT server on Linux will hit all three of these:
1. **bluez MIDI plugin** — `profiles/midi/midi.c` intercepts BLE connections → fix: `DisablePlugins = midi` in `/etc/bluetooth/main.conf`
2. **WirePlumber** — `spa.bluez5.midi` monitor also intercepts → fix: `monitor.bluez-midi = disabled` in wireplumber conf.d
3. **D-Bus threading** — dbus-python silently drops signals not emitted from main GLib thread → fix: `GLib.idle_add(chrc.notify_midi, data)` instead of direct call from background thread

## Critical: rtpmidid --port flag
rtpmidid v2 does NOT bind to port 5004 unless `--port 5004` is explicitly passed.
Without it: client-only mode, no network socket, Mac cannot connect.
Service file is at `/etc/systemd/system/rtpmidid.service`.

## MIDI Routing
Bidirectional: `C2MIDI Pro MIDI 1` ↔ `Bryan's MacBook Air` (via rtpmidid)

Manual reconnect if needed:
```bash
aconnect "C2MIDI Pro MIDI 1" "Bryan's MacBook Air"
aconnect "Bryan's MacBook Air" "C2MIDI Pro MIDI 1"
```

## Mac Audio MIDI Setup
- Session name: `Pi MIDI`
- Pi appears via mDNS as `bryanfoslerpi5` — do NOT add manual entry, causes duplicates
- Ports: UDP 5004 (RTP data) and 5005 (RTCP control)

## Key Files on Pi
- `/usr/local/bin/rtpmidid` — built from source
- `/usr/local/bin/midi-routing.sh` — ALSA routing script
- `/etc/systemd/system/rtpmidid.service`
- `/etc/systemd/system/midi-routing.service`
- `~/rtpmidid/` — source tree (keep for rebuilds)

## Useful Commands
```bash
aconnect -l                          # show all ALSA MIDI connections
sudo ss -ulnp | grep -E '500[45]'   # verify rtpmidid is listening
journalctl -u rtpmidid -f           # live log (shows ~3-5ms latency when Mac connected)
sudo systemctl restart rtpmidid     # restart (clears stale ALSA ports)
```

## Deploying petcam.py Updates
The service runs from `/usr/local/lib/petcam/petcam.py` (not the repo copy).
After editing `petcam/petcam.py` in the repo, deploy with:
```bash
# From Mac:
scp petcam/petcam.py bfosler@bryanfoslerpi5.local:~/pi-setup/petcam/petcam.py
ssh bfosler@bryanfoslerpi5.local "sudo cp ~/pi-setup/petcam/petcam.py /usr/local/lib/petcam/petcam.py && sudo systemctl restart petcam"

# Or from the Pi directly:
sudo cp ~/pi-setup/petcam/petcam.py /usr/local/lib/petcam/petcam.py && sudo systemctl restart petcam
```
