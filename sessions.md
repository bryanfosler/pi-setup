## Session 10 — OpenClaw (Piper) Telegram AI Bot

**Date:** 03.01.2026
**Time spent:** ~2h 30m

### What We Built
- OpenClaw gateway running as `openclaw-gateway` user systemd service
- Telegram bot `@Piper_RPi5Bot` connected and responding
- Notion integration (internal, read/write/insert) connected to Pi todo page
- Session-memory skill enabled for cross-conversation context

### What Shipped
- Piper responds to DMs in Telegram using Claude Haiku (Sonnet fallback)
- Notion pages writable from Telegram ("add a todo: X")
- Gateway auto-starts on boot via systemd user service

### Bugs Fixed
- 401 auth errors — old invalid Anthropic API key in auth-profiles.json; fixed by generating new key and writing via Python REPL `input()` prompt on Pi
- `systemctl restart openclaw` failed — correct service name is `openclaw-gateway`
- Warp terminal indentation — Python REPL and multi-line pastes cause IndentationError; workaround: use `input()` for key capture, or heredoc to write script file

### Decisions Made
- Haiku as primary model (cost), Sonnet as fallback (reasoning)
- Notion integration scoped to internal only (no OAuth app needed)
- Notion capabilities: read/write/insert content only; no comments or user info
- API keys stored in macOS Keychain Access going forward

## Session 9 — Remote Access, Auth & Stream Latency Fix

**Date:** 02.28.2026
**Time spent:** ~1h

### What We Built
- HTTP Basic Auth on all petcam routes (`GilligansIsland` / `Gilly1127`)
- Tailscale Funnel — public HTTPS URL, no Tailscale needed for viewer
- Shutdown button on web page (red, confirm dialog, POST `/shutdown` → `sudo shutdown -h now`)
- Passwordless sudo rule for petcam user: `/etc/sudoers.d/petcam-shutdown`
- `credentials.local.md` — gitignored local file with all Pi credentials

### What Shipped
- `https://bryanfoslerpi5.taildef31a.ts.net` — shareable link for wife, password protected
- Shutdown button accessible from any browser, anywhere
- 75-90 second stream delay reduced to ~1-2 seconds

### Bugs Fixed
- **75-90s live feed delay** — root cause: main loop read frames at 20fps but GoPro buffers at higher rate, causing frames to pile up in FFmpeg's FIFO. Fix: dedicated capture thread that drains the buffer as fast as possible (no sleep), main loop reads from shared latest frame. Also reduced `fifo_size` from 5MB → 64KB.
- MJPEG stream (`/stream`) caused stuck/looping video through Tailscale Funnel — HTTPS proxies buffer multipart responses. Fix: chained fetch of `/snapshot` (individual JPEG requests proxy cleanly, no buffering)

### Decisions Made
- Basic auth over HTTPS is sufficient for petcam — keeps honest people out, browser saves credentials after first entry
- Tailscale Funnel chosen over Cloudflare Tunnel (already had Tailscale) and router port forwarding (security concern)
- Funnel config is persistent (stored by tailscaled), survives reboots automatically

---

## Session 8 — GoPro Hero 12 USB + Petcam Live Stream

**Date:** 02.27.2026
**Time spent:** ~2h

### What We Built
- GoPro Hero 12 connected via USB as petcam source (1080p vs 640x480 webcam — massive quality improvement)
- GoPro connects via USB CDC NCM driver → eth1 at 172.23.194.51
- `gopro_start()` — HTTP call to GoPro API on startup to begin webcam stream
- `gopro_keepalive()` — background thread pinging GoPro every 2s (required or stream drops)
- Fixed petcam live stream viewer — multiple bugs uncovered and fixed

### Bugs Fixed
- **HTTPServer single-threaded**: `/stream` endpoint's infinite loop blocked all other requests → switched to `ThreadingHTTPServer`
- **Safari MJPEG**: `<img src="/stream">` doesn't update in Safari → replaced with JS snapshot polling every 500ms
- **Query string mismatch**: JS requests `/snapshot?timestamp` but handler checked `self.path == "/snapshot"` → strip query string with `split("?")[0]`
- **Ollama blocking capture loop**: `describe_frame()` blocks 30s on timeout → offloaded to background thread
- **Wrong deploy target**: edits to `~/pi-setup/petcam/petcam.py` didn't take effect — service runs `/usr/local/lib/petcam/petcam.py`
- **GoPro IP not .1**: GoPro ignores ICMP but responds to HTTP; found at 172.23.194.51 via HTTP scan

### What Shipped
- `petcam/petcam.py` — all fixes committed and pushed
- CLAUDE.md updated with deploy command for petcam updates

### Decisions Made
- `GOPRO_MODE = True` flag in petcam.py config; webcam fallback still supported with `GOPRO_MODE = False`
- GoPro IP hardcoded as `172.23.194.51` — consistent since GoPro is the DHCP server
- Next session: remote live stream access (Tailscale already installed — just needs port forwarding or direct Tailscale URL)

---

## Session 7 — BLE MIDI Debugging + Full Working Stack

**Date:** 02.27.2026
**Time spent:** ~2h

### What We Built
- Fully working BLE MIDI: Pi visible as "Pi BT MIDI" in Audio MIDI Setup → Bluetooth; Mac GarageBand receives MIDI notes over Bluetooth

### Bugs Fixed
- **WirePlumber conflict**: `spa.bluez5.midi` plugin intercepts BLE connections and fights our GATT server → fixed by adding `/etc/wireplumber/wireplumber.conf.d/50-disable-bluetooth-midi.conf` to disable `monitor.bluez-midi`
- **bluez MIDI plugin conflict**: built-in `profiles/midi/midi.c` also intercepts connections → fixed by adding `DisablePlugins = midi` to `/etc/bluetooth/main.conf`
- **D-Bus threading bug**: `alsa_poll_loop` runs in background thread but called `PropertiesChanged` D-Bus signal directly — dbus-python signals must be emitted from the main GLib thread → fixed with `GLib.idle_add(chrc.notify_midi, data)`
- Both fixes baked into `install-bt-midi.sh` for clean future deploys

### What Shipped
- `bt-midi/bt-midi-peripheral.py` — threading fix committed and pushed
- `setup/install-bt-midi.sh` — WirePlumber + bluez MIDI plugin disable steps added

### Decisions Made
- WirePlumber BLE MIDI disabled via profile override (not removed — just that component off)
- discoverable-timeout set to 0 (infinite) in install script so Pi stays visible permanently

---

## Session 6 — ntfy Setup + Open-WebUI + Petcam Topic Fix

**Date:** 02.27.2026
**Time spent:** ~30m

### What We Did
- Set up ntfy.sh app on iPhone, subscribed to topic `bryan-petcam-302`
- Updated `petcam.py` NTFY_TOPIC: `bfosler-petcam1` → `bryan-petcam-302`; restarted petcam service
- Installed Open-WebUI — Docker image already cached from prior session, container spun up immediately
- Confirmed all Pi services fully running: Ollama, Open-WebUI, petcam, bt-midi, rtpmidid, Tailscale

### What Shipped
- Open-WebUI live at `http://bryanfoslerpi5.local:3000`
- Petcam sending notifications to correct ntfy topic
- Pi setup fully complete — all scripts from the deployment checklist done

### Bugs Fixed
- Petcam had stale ntfy topic from earlier dev iteration

### Decisions Made
- Mac Internet Sharing skipped permanently — Mac is on WiFi so can't also broadcast a WiFi hotspot; iPhone hotspot + Pi hotspot covers all travel scenarios

---

## Session 5 — Full Deployment to Pi

**Date:** 02.26.2026
**Time spent:** ~1h 30m

### What We Built
- Deployed all scripts to live Pi for the first time
- Fixed Open-WebUI install: switched from pip to Docker (Debian Trixie ships Python 3.13; open-webui pip requires <3.13)
- Fixed moondream model name: `moondream2` → `moondream` in Ollama registry
- Fixed bt-midi venv creation (needs sudo for /opt)
- Fixed install-petcam.sh template variable substitution (deployed service directly)

### What Shipped
- All services running: Ollama, Open-WebUI (Docker), rtpmidid, midi-routing, bt-midi, Tailscale
- Network priorities set: GilligansIsland=10, iPhone hotspot=5
- Pi hotspot profile configured (BryanPi5 / 192.168.100.1)
- Tailscale connected: `100.99.74.37`
- Petcam ready — blocked on USB webcam not connected

### Bugs Fixed
- Open-WebUI pip fails on Python 3.13 → Docker workaround
- `moondream2` not in Ollama registry → correct name is `moondream`
- bt-midi `/opt/bt-midi-venv` needs sudo to create
- install-petcam.sh template vars (`__VENV_DIR__` etc.) need substitution before deploy

### Decisions Made
- Open-WebUI runs as Docker container with `--restart always`; systemd service is a oneshot wrapper (`docker start open-webui`)
- Mac Internet Sharing skipped — iPhone hotspot + Pi hotspot covers travel scenarios

---

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
