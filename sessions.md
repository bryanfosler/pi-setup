## Session 15 — Hybrid Local AI Architecture for Piper

**Date:** 03.05.2026
**Time spent:** ~1h 30m

### What We Built
- Designed hybrid AI architecture: Qwen2.5-1.5B local model + Haiku API + Sonnet escalation
- Fixed the root cause of Ollama OOM: OpenClaw reads `contextWindow` from `models.json` and passes it directly as `num_ctx` — all llama models had 131072, causing 15.9GB allocation. Capped to 4096.
- Added `OLLAMA_KEEP_ALIVE=5m` and `MemoryMax=3G` to the Ollama systemd service override
- Pulled Qwen2.5-1.5B-Q4_K_M (986MB, ~1.4GB runtime, 0.6s warm latency)
- Added Qwen2.5 to `models.json` with `contextWindow: 4096`
- Built `local-infer` OpenClaw skill with circuit breaker: classifies/extracts/summarizes via local model; falls back to API after 3 failures; auto-resets after 30 min
- Debugged OpenClaw skill snapshot versioning: skills added after gateway startup require a `touch SKILL.md` to trigger file watcher and bump snapshot version

### What Shipped
- Local inference working: `llama3.2:1b` and `qwen2.5:1.5b-instruct-q4_K_M` both run at 4096 ctx
- `local-infer` skill live and visible to Piper agent — confirmed via `openclaw agent --agent main`
- Circuit breaker state file: `~/.openclaw/local-infer-state.json`
- Ollama service override: `/etc/systemd/system/ollama.service.d/override.conf`

### Bugs Fixed
- Ollama OOM fixed by capping `contextWindow` in `models.json` (was 131072 → 4096)
- OpenClaw skill not appearing in agent: required `touch SKILL.md` after gateway start to bump snapshot version counter from 0 to >0

### Decisions Made
- Use rule-based routing (not LLM-as-router) — faster, deterministic, zero RAM overhead
- One local model (Qwen2.5-1.5B) committed to; no hot-swappable second tier
- Defer RAG (chroma + sentence-transformers) until a concrete retrieval gap exists
- Sonnet escalation is explicit-only (never automatic) to keep costs predictable
- No proxy shim needed — OpenClaw exposes `contextWindow` in `models.json` as a direct fix point

## Session 14 — Strava API Integration for Piper

**Date:** 03.03.2026
**Time spent:** ~1h 30m

### What We Built
- Strava skill for Piper (`~/.openclaw/workspace/skills/strava/`) — running + cycling activity analysis via Strava API
- `strava_refresh.py` helper script: handles Strava's 6h OAuth token expiry using stored refresh token
- SKILL.md with 9 query workflows: recent activities, weekly volume, monthly comparison, pace trend, long run progression, cycling volume + climbing, PRs, athlete stats, and AI coaching analysis
- Auto-Obsidian logging: every weekly summary writes to `~/ObsidianVault/AI Knowledge/Training/YYYY-WW.md` and syncs to Mac via Syncthing

### What Shipped
- Skill deployed and live on Pi — Piper can now answer training questions in Telegram
- Token refresh confirmed working (tested on Pi)
- 4 Strava credentials stored in `openclaw.json` env block
- `~/ObsidianVault/AI Knowledge/Training/` folder created on Pi

### Bugs Fixed
- Reused existing Strava credentials from run-route-generator project — skipped OAuth setup entirely

### Decisions Made
- Strava API as single source of truth (no local data cache)
- Obsidian Training folder for auto-logging weekly summaries (separate from existing `AI Knowledge/Piper/` logs)
- Token refresh via Python stdlib script (no pip deps) — cleaner than inline curl chain in SKILL.md
- Obsidian logging triggered by Piper's weekly analysis (no cron job)

---

## Session 13 — Claude Code Obsidian Commands + Stop Hook Logging

**Date:** 03.03.2026
**Time spent:** ~45m

### What We Built
- `/context` command (`~/.claude/commands/context.md`) — reads full vault at session start, outputs structured briefing: active projects, priorities, recent CC sessions, Piper highlights, decisions log, carry-overs
- `/closeday` command (`~/.claude/commands/closeday.md`) — end-of-day synthesis; reads today's CC log + Piper summary → writes `Daily/YYYY-MM-DD.md`
- Obsidian logging in Stop hook: always-on (no `CLAUDE_VOICE` required), appends `### HH:MM — project` breadcrumb to `AI Knowledge/Claude Code/YYYY-MM-DD.md` after every response
- Created `~/.claude/commands/` directory — native CC slash commands (distinct from `~/.claude/skills/`)

### What Shipped
- Both commands live and discoverable in Claude Code command palette
- Stop hook confirmed working: created today's CC log during session
- `AI Knowledge/Claude Code/2026-03-03.md` created automatically

### Bugs Fixed
- Stop hook had early CLAUDE_VOICE guard that would have skipped Obsidian logging when TTS off — restructured flow so logging always runs, TTS remains opt-in

### Decisions Made
- `/today` deferred — needs daily note writing habit + calendar integration first
- Native `~/.claude/commands/` for prompt-style slash commands; `~/.claude/skills/` reserved for procedural SKILL.md skills using the Skill tool
- `/closeday` is the reflective counterpart to `/wrap-up` — wrap-up ships work to GitHub/Notion, closeday captures it to Obsidian for future self

---

## Session 12 — Piper Logging, Security Hardening, Notion Sprint Board & Obsidian Vault

**Date:** 03.02.2026
**Time spent:** ~2h 30m

### What We Built
- Piper logger daemon (`piper_logger.py`): polls OpenClaw session JSONL files every 15s, indexes messages/sessions/errors into SQLite (`piper_logs.db`)
- `piper-logger.service`: user systemd service, auto-starts on boot
- Piper Notion writer (`piper_notion.py`): `--status`, `--errors`, `--summary`, `--force` — posts to Notion and writes daily markdown to Obsidian vault
- Cron jobs: daily summary at 23:30, error sync hourly
- Obsidian vault (`~/Documents/ObsidianVault/`) created on Mac; Pi vault at `~/ObsidianVault/`
- Syncthing configured and paired on both Pi and Mac — vault syncs over local network
- Notion sprint board: all 5 repos updated (statusMap `Open` → `Backlog`, `Source: Claude Code` added)
- 8 Notion backlog cards created (security assessment, Discord, Obsidian CC logging, skills deep dive, OpenClaw config, Piper tools, vector memory, FastAPI gateway)

### What Shipped
- Piper daily summaries appear in Obsidian vault (AI Knowledge/Piper/YYYY-MM-DD.md) and Notion
- Piper errors sync to Notion backlog hourly
- Sprint board live with Backlog/Ready/In Progress/Blocked/Done columns
- Security hardening applied: UFW rules, SSH password auth off, Ollama localhost-only, rpcbind disabled

### Bugs Fixed
- SSH to `bryanfoslerpi5.local` failing (Undefined error: 0) → switched to Tailscale IP `100.99.74.37`
- Host key verification failed → `ssh-keygen -R 100.99.74.37`
- SSH password auth `sed` missed commented-out line → targeted line 57 directly
- Python heredoc over SSH failing with nested quotes → Write file locally + pipe via SSH stdin
- Syncthing restart 405 error → used `/rest/system/restart` POST instead
- Notion 404 on Pi API calls → "Piper OpenClaw" integration needed DB sharing step in Notion UI

### Decisions Made
- Separate Notion integration for Pi ("Piper OpenClaw") vs Mac ("Claude Code") — good security boundaries
- Obsidian vault folder structure: `AI Knowledge/{Claude Code,Piper,Decisions}`, `Projects/`, `Daily/`
- Source tagging: `OpenClaw` for Pi-generated items, `Claude Code` for GitHub-synced items, `Manual` for user-added
- Reviewed Obsidian + Claude Codebook PDF (12 slash commands) — `/context`, `/today`, `/closeday` are top priorities to build

---

## Session 11 — Homebridge + Google Nest HomeKit Bridge

**Date:** 03.01.2026
**Time spent:** ~1h 30m

### What We Built
- Homebridge running on Pi 5 via Docker (`ghcr.io/homebridge/homebridge:latest`)
- `homebridge-nest-accfactory@0.3.9` plugin — bridges Google Nest devices to HomeKit without the $5 Google SDM fee
- Google account auth via Safari cookie extraction (issueToken + full cookie string)
- Apple TV HD configured as Home Hub for remote access

### What Shipped
- Nest Learning Thermostat (3rd gen) visible in iPhone Home app as "Entryway"
- Nest Doorbell (wired) visible in Home app as "Front Door"
- Siri thermostat control and remote access working via Apple TV hub

### Bugs Fixed
- Plugin not loading — installed to global npm path, must use `--prefix /var/lib/homebridge` instead
- Config rejected with "No connections specified" — wrong key names: `googleAuth` → `google`, `issueToken` → `issuetoken`, `cookies` → `cookie`
- issueToken not appearing in Chrome — must use Safari (ITP blocks the iframerpc request in other browsers)

### Decisions Made
- Cookie-based auth (no $5 SDM fee) — try it free first; pay only if it breaks and stays broken
- Docker install with `--net=host` required for mDNS/HomeKit discovery
- Plugin path: `/var/lib/homebridge/node_modules` (not global npm)
- Do NOT log out of home.nest.com — invalidates auth tokens

---

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

## Session 15 — OpenClaw 3.2 Upgrade Recovery

**Date:** 03.05.2026
**Time spent:** ~2h

### What We Built
- Re-established all OpenClaw channels after upgrade broke them
- Security lockdown: Discord + Telegram scoped to Bryan's user IDs only
- Guild-level `requireMention: false` so Bryan can chat in Discord channels without tagging @Piper

### What Shipped
- OpenClaw back to fully operational: Telegram ✅, Discord DM ✅, Discord server channels ✅, WebUI ✅
- Model: Anthropic Haiku (local LLM deferred — Pi5 CPU + RAM insufficient)
- Gateway accessible over LAN (`bind: lan`)

### Bugs Fixed
- **Plugin system (3.2 breaking change)** — all channel adapters disabled by default; fixed with `openclaw plugins enable telegram/discord`
- **Broken systemd override** — missing `[` before `Service]`, silently ignored by systemd; deleted it
- **Gateway loopback-only** — changed `gateway.bind` from `loopback` to `lan`
- **Channel tokens wiped** — upgrade cleared Telegram and Discord tokens from config; re-added
- **Discord `dmPolicy: open` crash** — requires `"*"` in allowFrom; changed to `allowlist`
- **Ollama OOM** — Pi5 (7.4GB RAM) can't run llama3.2:1b because OpenClaw passes architecture `context_length: 131072` regardless of modelfile PARAMETER overrides (needs 15.9GB)
- **Discord server channels not receiving messages** — `groupPolicy: open` + `requireMention: false` per guild

### Decisions Made
- Local LLM abandoned for now: Pi5 CPU inference takes 2-4 min per response; not viable for chat
- Anthropic Haiku as permanent model until Pi5 gets GPU or we move to a faster device
- `allowFrom` locked to Bryan's IDs only; add more users manually when ready

## Session 16 — Pi5 Edge AI Hub Phase 1: Architecture, shared lib, task-builder skill

**Date:** 03.05.2026
**Time spent:** ~2h 30m

### What We Built
- Full Pi5 Edge AI Hub architecture design (OpenClaw + n8n + shared lib pattern)
- Shared Python lib: `notion.py`, `claude.py`, `telegram.py`, `github.py` (all stdlib-only)
- `task-builder` OpenClaw skill — conversational Notion task creation with coaching flow
- `create_notion_task.py` — script with --dry-run, validated end-to-end against Notion API
- `health_check.py` — cron-based Pi health monitor (temp/disk/RAM/services → Telegram)
- `deploy.sh` — rsync-based deployer with --dry-run and --skill=<name> flags
- 5 detailed backlog GitHub issues (#15-19) for deferred Phase 2+ components

### What Shipped
- Shared lib committed and deployed to Pi
- Task-builder SKILL.md + script deployed, verified ✅ in `npx openclaw skills list`
- `create_notion_task.py` tested live — Notion page created successfully
- OpenClaw model switched from `ollama/qwen2.5` → `claude-haiku-4-5-20251001`
- Piper Tasks Notion DB created with correct schema

### Bugs Fixed
- rsync `--delete` flag wiped strava/obsidian/piper-memory skills on first deploy — restored from sandbox, removed --delete
- SKILL.md frontmatter was wrong format — OpenClaw needs `name`/`description`/`metadata.openclaw` not `emoji`/`requires`
- `NOTION_API_KEY` missing from Pi openclaw.json env block — set securely via terminal

### Decisions Made
- Skills deployed additively (no --delete) — Pi skills not in repo are never touched
- Phase 2 items (Grafana, Gitea, Neo4j, Node-RED, home agent) tracked as backlog with detailed gate conditions
- OpenClaw = interactive chat; n8n = scheduled/autonomous workflows — strict boundary

### Remaining / Next Session
- task-builder skill routes to command execution instead of coaching flow (#22)
- Automate `touch` snapshot refresh in deploy.sh (#23)
- n8n + Docker Compose for Phase 1
- Daily Digest workflow
- Pi health check cron: wire TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars
