# Full Setup Guide — bryanfoslerpi5
*Complete deployment reference — updated 02.26.2026*

This is the single doc to follow when setting up the Pi from scratch.
Run everything in order. Each section builds on the previous one.

---

## Prerequisites

- Raspberry Pi 5 (8GB) running Debian Trixie
- SSH key already installed (no password prompt)
- Ethernet cable + router access for initial setup
- USB webcam plugged into Pi
- iPhone with ntfy app installed

---

## Step 0 — Get Connected

Plug the Pi into your router via ethernet, then SSH in from your Mac:

```bash
ssh bfosler@bryanfoslerpi5.local
```

If that doesn't resolve, find the Pi's IP on your router's device list and use:
```bash
ssh bfosler@<ip-address>
```

---

## Step 1 — Clone the Repo

All setup scripts live in the repo. Clone it onto the Pi first:

```bash
git clone https://github.com/bryanfosler/pi-setup.git
cd pi-setup
```

> Everything below is run from inside this `pi-setup/` directory on the Pi.

---

## Step 2 — WiFi Networks

Adds iPhone hotspot and Mac Internet Sharing as backup networks so you can
SSH in without ethernet in the future.

**Before running — fill in three placeholders in the script:**
```bash
nano setup/add-networks.sh
```
Set these values:
- `HOME_SSID` — your home WiFi network name
- `MAC_SHARING_SSID` — set this up first (see note below)
- `MAC_SHARING_PASSWORD` — same

> **Mac Internet Sharing setup (do on Mac first):**
> System Settings → General → Sharing → Internet Sharing
> Turn on → Share via Wi-Fi → set a custom network name + password
> Use those values for `MAC_SHARING_SSID` and `MAC_SHARING_PASSWORD`

```bash
bash setup/add-networks.sh
```

**Network priority order after this runs:**
| Network | Priority |
|---------|---------|
| Home WiFi | 10 (always preferred) |
| iPhone Hotspot (`Bryan's iPhone` / `11111111`) | 5 |
| Mac Internet Sharing | 3 |

**Switching networks manually:**
```bash
bash setup/switch-network.sh             # show status
bash setup/switch-network.sh iphone      # force iPhone hotspot
bash setup/switch-network.sh home        # force home WiFi
bash setup/switch-network.sh mac         # force Mac sharing
```

---

## Step 3 — Ollama (LLM Engine)

Installs Ollama, exposes it on the network, and pulls `llama3.2:3b` (~2GB).

```bash
bash setup/install-ollama.sh
```

**What this does:**
- Installs Ollama and registers it as a systemd service
- Sets `OLLAMA_HOST=0.0.0.0:11434` so your Mac can reach the API
- Pulls `llama3.2:3b` as the default chat model

**After install — test it:**
```bash
ollama run llama3.2:3b "Hello, are you working?"
# Ctrl+D to exit
```

**Available models (pull any time):**
```bash
ollama pull llama3.2:1b    # faster, lighter
ollama pull mistral:7b     # more capable, slower (~3-5 tok/s)
ollama pull moondream2     # vision model — needed for pet cam
```

---

## Step 4 — Open-WebUI (Browser Chat Interface)

Installs a browser-based chat UI for Ollama. Takes 5-10 minutes.

```bash
bash setup/install-open-webui.sh
```

**After install:**
- Open `http://bryanfoslerpi5.local:3000` in any browser on your network
- Create a local admin account (first launch only — credentials stay on Pi, not sent anywhere)
- Select a model and start chatting

---

## Step 5 — Pet Cam

Installs the motion-triggered AI camera with live stream and push notifications.

**Before running — customize the ntfy topic:**
```bash
nano petcam/petcam.py
```
Change `NTFY_TOPIC = "bryanpi-petcam"` to something unique to you.

```bash
bash setup/install-petcam.sh
```

**What this does:**
- Installs OpenCV and dependencies in a Python venv
- Pulls `moondream2` vision model (~1.8GB)
- Deploys `petcam.service` — starts automatically on boot, after Ollama

**Set up phone notifications:**
1. iPhone App Store → search **ntfy** → install
2. Open ntfy → **+** → enter your `NTFY_TOPIC` name exactly

**Test the notification pipeline:**
```bash
# From Pi — sends a test notification to your phone
curl -d "test from Pi" ntfy.sh/YOUR_TOPIC_NAME
```

**Live stream:**
```
http://bryanfoslerpi5.local:8080
```
Open in Safari on iPhone — no app needed, ~10fps.

---

## Step 5b — BLE MIDI Peripheral (Bluetooth MIDI)

Makes the Pi visible as a Bluetooth MIDI device — no WiFi required for MIDI.
Mac/iOS connects directly via Bluetooth in Audio MIDI Setup.

```bash
bash setup/install-bt-midi.sh
```

**What this does:**
- Installs bluez + Python BLE GATT dependencies
- Deploys `bt-midi-peripheral.py` — implements the BLE MIDI spec (MMA)
- Registers `bt-midi.service` — starts automatically on boot, after bluetooth

**Connect on Mac:**
1. Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup")
2. **Window → Show MIDI Studio**
3. Double-click the **Bluetooth** icon in the toolbar
4. Find **"Pi BT MIDI"** → click **Connect**

After connecting, the Pi appears as a MIDI device in GarageBand, Logic, or any MIDI app — just like the network MIDI session but over Bluetooth.

**MIDI routing:** BLE MIDI ↔ ALSA virtual port "Pi BT MIDI". Wire it to the C2MIDI Pro with aconnect if you want the keyboard → BT chain:
```bash
aconnect "C2MIDI Pro MIDI 1" "Pi BT MIDI"
aconnect "Pi BT MIDI" "C2MIDI Pro MIDI 1"
```

**Check the service:**
```bash
journalctl -u bt-midi -f
sudo systemctl status bt-midi
```

> **Network MIDI vs BLE MIDI:** Both work. Network MIDI (rtpmidid) is lower latency on a good WiFi network. BLE MIDI works anywhere — no WiFi needed — but adds ~5-10ms of BLE latency. Use whichever fits the situation.

---

## Step 5c — Pi WiFi Hotspot

Lets the Pi create its own WiFi network. Use this when there's no router, no iPhone, no ethernet — Mac connects to the Pi directly.

**Before running — set a password in the script:**
```bash
nano setup/setup-hotspot.sh
```
Set `HOTSPOT_PASSWORD` to something 8+ characters.

```bash
bash setup/setup-hotspot.sh
```

**Network priority order (updated):**
| Network | Priority | Notes |
|---------|---------|-------|
| Home WiFi | 10 | always preferred when home |
| iPhone Hotspot | 5 | travel fallback |
| Mac Internet Sharing | 3 | last resort client mode |
| Pi Hotspot | manual only | Pi becomes the AP, no autoconnect |

**Using the hotspot:**
```bash
bash setup/switch-network.sh hotspot   # Pi starts broadcasting BryanPi5
bash setup/switch-network.sh home      # back to normal WiFi
```

While hotspot is active:
- Pi IP: `192.168.100.1`
- SSH: `ssh bfosler@192.168.100.1`
- All services reachable at `192.168.100.1` (Ollama, Open-WebUI, petcam, MIDI)
- Pi has no internet access (single WiFi radio — can't uplink and host simultaneously)

---

## Step 6 — Remote Access (Tailscale)

Lets you SSH, view the stream, and use Open-WebUI from anywhere — not just home WiFi.

**On the Pi:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Follow the auth link it prints — log in with your Tailscale account (free).

**On your iPhone:**
- App Store → **Tailscale** → install → sign in with same account

**After setup:**
- Pi gets a stable Tailscale IP (e.g. `100.x.x.x`) — find it with `tailscale ip`
- From anywhere: `ssh bfosler@100.x.x.x`
- Live stream from anywhere: `http://100.x.x.x:8080`
- Open-WebUI from anywhere: `http://100.x.x.x:3000`
- Ollama API from anywhere: `http://100.x.x.x:11434`

```bash
# Check Tailscale status
tailscale status

# Get your Pi's Tailscale IP
tailscale ip
```

---

## All Services at a Glance

| Service | Port | Access | Started by |
|---------|------|--------|-----------|
| SSH | 22 | LAN + Tailscale | OS |
| Ollama API | 11434 | LAN + Tailscale | `ollama.service` |
| Open-WebUI | 3000 | LAN + Tailscale | `open-webui.service` |
| Pet cam stream | 8080 | LAN + Tailscale | `petcam.service` |
| rtpmidid (Network MIDI) | 5004/5005 UDP | LAN | `rtpmidid.service` |
| BLE MIDI | Bluetooth | Bluetooth range | `bt-midi.service` |

---

## Useful Daily Commands

```bash
# Check all services at once
sudo systemctl status ollama open-webui petcam rtpmidid midi-routing

# Restart everything
sudo systemctl restart ollama open-webui petcam

# Watch pet cam live (motion events + AI descriptions)
journalctl -u petcam -f

# List installed Ollama models
ollama list

# Pull a new model
ollama pull <model-name>

# Check Pi temperature (should be under 80°C)
vcgencmd measure_temp

# Tailscale status
tailscale status
```

---

## Key File Locations on Pi

| Path | Purpose |
|------|---------|
| `~/pi-setup/` | Cloned repo (keep — rerun scripts if needed) |
| `/usr/local/bin/rtpmidid` | MIDI daemon (built from source) |
| `/usr/local/bin/midi-routing.sh` | ALSA routing script |
| `/usr/local/lib/petcam/petcam.py` | Pet cam script (edit config here) |
| `/opt/open-webui-venv/` | Open-WebUI Python venv |
| `/opt/petcam-venv/` | Pet cam Python venv |
| `~/.ollama/models/` | Downloaded Ollama models |
| `~/.open-webui/` | Open-WebUI data |
| `/etc/systemd/system/` | All service files |

---

## Related Docs

| Doc | What's in it |
|-----|-------------|
| `docs/pi5-quick-reference-02.26.2026.md` | General Pi 5 commands |
| `docs/ollama-guide-02.26.2026.md` | Ollama model management + API |
| `docs/petcam-guide-02.26.2026.md` | Pet cam config + tuning |
| `README.md` | Project overview + MIDI setup |
