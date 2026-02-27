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
| Petcam stream (direct MJPEG) | http://bryanfoslerpi5.local:8080/stream | http://100.99.74.37:8080/stream |
| Ollama API | http://bryanfoslerpi5.local:11434 | http://100.99.74.37:11434 |
| ntfy alerts | https://ntfy.sh/bryan-petcam-302 | — |
| SSH (local) | `ssh bfosler@bryanfoslerpi5.local` | `ssh bfosler@100.99.74.37` |

## Services
| Service | Port | Status | Notes |
|---|---|---|---|
| `rtpmidid` | UDP 5004/5005 | enabled, auto-start | Must use `--port 5004` flag or it won't bind |
| `midi-routing` | — | enabled, auto-start | Waits for Mac connection, then routes bidirectionally |
| `bt-midi` | BLE | enabled, auto-start | Pi as BLE MIDI peripheral; connects from Audio MIDI Setup → Bluetooth |
| `ollama` | 11434 | enabled, auto-start | `OLLAMA_HOST=0.0.0.0` override in systemd drop-in |
| `open-webui` | 3000 | enabled, auto-start | Docker container; browser chat UI for Ollama |
| `petcam` | 8080 (stream) | enabled, auto-start | Motion detection + moondream + ntfy.sh notifications |

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
