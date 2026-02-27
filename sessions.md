## Session 4 — BLE MIDI Peripheral + Pi WiFi Hotspot

**Date:** 02.26.2026
**Time spent:** ~1h 30m

### What We Built
- `bt-midi/bt-midi-peripheral.py` — Python BLE MIDI peripheral using bluez GATT + D-Bus; bridges ALSA virtual port "Pi BT MIDI" ↔ BLE MIDI (MMA spec); Mac/iOS connects from Audio MIDI Setup → Bluetooth
- `setup/install-bt-midi.sh` — installs deps (bluez, python3-dbus, python3-gi, python-rtmidi venv), deploys script, enables `bt-midi.service`
- `systemd/bt-midi.service` — auto-starts after bluetooth.target
- `setup/setup-hotspot.sh` — creates `pi-hotspot` NetworkManager connection in AP mode with `ipv4.method shared`; Pi broadcasts as `BryanPi5`, is reachable at `192.168.100.1`
- Updated `setup/switch-network.sh` — added `hotspot` shortcut with proper AP ↔ client teardown logic

### What Shipped
- All files committed and pushed to `bryanfosler/pi-setup`
- BLE MIDI and hotspot sections added to `docs/full-setup-guide-02.26.2026.md`
- `CLAUDE.md` updated with bt-midi service row and hotspot notes

### Bugs Fixed
- N/A (new feature session)

### Decisions Made
- BLE MIDI peripheral runs as user `bfosler` (not root) — uses D-Bus system bus for bluez access
- Python venv at `/opt/bt-midi-venv` with `--system-site-packages` to share python3-dbus/gi from system
- Pi hotspot uses `autoconnect no` — never enables automatically, only via explicit `switch-network.sh hotspot`
- Single WiFi radio means hotspot mode = no internet; acceptable for local MIDI/AI use case

---

## Session 3 — Ollama, Open-WebUI, Pet Cam + Live Stream

**Date:** 02.26.2026
**Time spent:** ~1h 30m

### What We Built
- `setup/install-ollama.sh` — installs Ollama with LAN network access, pulls `llama3.2:3b`
- `setup/install-open-webui.sh` — browser chat UI in Python venv, systemd service on port 3000
- `petcam/petcam.py` — motion detection + moondream2 AI description + ntfy.sh push notifications + built-in MJPEG live stream on port 8080
- `setup/install-petcam.sh` — full petcam install script
- `docs/ollama-guide-02.26.2026.md` — Ollama model reference and API usage
- `docs/petcam-guide-02.26.2026.md` — pet cam config, tuning, troubleshooting
- `docs/full-setup-guide-02.26.2026.md` — end-to-end deployment guide covering all steps in order

### What Shipped
- All files committed and pushed to `bryanfosler/pi-setup`
- Ready to deploy: `git clone` repo on Pi, then run install scripts in order

### Bugs Fixed
- N/A (new feature session)

### Decisions Made
- Single process owns camera — MJPEG stream server runs in background thread, no `/dev/video0` conflict
- ntfy.sh for push notifications (reaches phone anywhere, already works off-network)
- Tailscale for remote SSH/stream/API access (covers all services, free)
- Scripts require `git clone` on Pi first — they reference sibling files (systemd/, petcam/)

---

## Session 2 — Quick Reference Doc + Network Switching Scripts

**Date:** 02.26.2026
**Time spent:** ~45m

### What We Built
- `docs/pi5-quick-reference-02.26.2026.md` — full Pi 5 command reference (SSH, system info, services, logs, file system, networking, updates, MIDI, troubleshooting)
- `setup/add-networks.sh` — one-time script to add iPhone hotspot + Mac Internet Sharing with autoconnect priorities
- `setup/switch-network.sh` — manual network switcher with `home/iphone/mac` shortcuts

### What Shipped
- All three files committed and pushed to `bryanfosler/pi-setup`
- iPhone hotspot credentials already filled in; Mac Internet Sharing placeholders to complete at home

### Bugs Fixed
- N/A (documentation + prep session)

### Decisions Made
- Network priority order: home WiFi=10, iPhone hotspot=5, Mac Internet Sharing=3
- iPhone hotspot preferred over Mac Internet Sharing for travel (simpler, works regardless of Mac state)
- Pi 5 USB-C is power only, USB-A ports are host only — ethernet or WiFi required for SSH

---

## Session 1 — Headless rtpMIDI + Mac MIDI Routing

**Date:** 02.20.2026
**Time spent:** ~1h 30m

### What We Built
- Headless rtpMIDI daemon (rtpmidid) built from source and running as a systemd service
- Bidirectional ALSA MIDI routing: CME C2MIDI Pro ↔ Mac Network MIDI
- GitHub repo (`bryanfosler/pi-setup`) with install scripts and README for reproducibility

### What Shipped
- `rtpmidid.service` — auto-starts on boot, listens on UDP 5004/5005
- `midi-routing.service` — waits for Mac connection then routes C2MIDI Pro ↔ Mac
- SSH public key auth (already installed, confirmed working)

### Bugs Fixed
- qmidinet fails headless (GUI app requires display) → replaced with rtpmidid
- rtpmidid not binding to port 5004 → must pass `--port 5004` explicitly; without it runs client-only
- Duplicate "Bryan's MacBook Air" ALSA ports → caused by manual + mDNS entries both connected; resolved by removing manual entry in Audio MIDI Setup

### Decisions Made
- Use rtpmidid (built from source) over raveloxmidi — simpler build, cleaner systemd integration
- Bidirectional routing so CME controller can send to Mac AND Mac can send to CME
