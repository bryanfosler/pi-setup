# Bryan Learns: Headless Pi MIDI

---

## The Snapshot Version Trap (OpenClaw Skill Discovery)

Here's a subtle one that cost us a good chunk of debugging time.

When OpenClaw's gateway starts up, it scans the `~/.openclaw/workspace/skills/` directory and builds a "snapshot" of all available skills. This snapshot gets stored in each session's JSON with a **version number**. The version starts at 0.

When a file in the skills directory changes, a filesystem watcher increments the version counter to 1, 2, 3... The gateway then compares: "Does the session's cached snapshot have a version lower than the current counter?" If yes, it refreshes. If not, it reuses the old snapshot.

The trap: **if you add a new skill after the gateway starts, and then restart the gateway, the version counter resets to 0.** The old cached sessions also have version 0 in their snapshot. So 0 ≥ 0 — no refresh triggered. The new skill never appears.

The fix is stupidly simple: `touch ~/.openclaw/workspace/skills/local-infer/SKILL.md` after the gateway is running. The file watcher fires, bumps the counter to 1, and all sessions get a fresh snapshot on the next message.

**Lesson:** if you ever add a skill and it doesn't show up even after a restart, just `touch` its SKILL.md.

---

## How OpenClaw Passes Context Window Size to Ollama

This was the root cause of the Ollama OOM crashes. You'd try to load `llama3.2:1b` (a 1.3GB model!) and the Pi would run out of memory. But why? It's a *1B parameter* model — should fit easily.

The answer is context window size. When you run an LLM locally, you allocate memory not just for the weights but for the **KV cache** — a chunk of memory that stores all the token computations from the current conversation. A context window of 131,072 tokens needs roughly 14GB of KV cache. The model weights themselves are only 1.3GB, but the KV cache makes the total ~15.9GB.

So how did a 1.3GB model need 15.9GB? OpenClaw reads `contextWindow` from `models.json` and passes it directly as `num_ctx` (the Ollama parameter that controls KV cache size). Every llama model in models.json had `"contextWindow": 131072` — which is the model's *declared maximum*, not a practical default.

The fix: edit `models.json` and change `"contextWindow": 131072` to `"contextWindow": 4096`. Now Ollama allocates a 4096-token KV cache (~1.4GB total) and everything fits in RAM. One JSON edit. No proxy needed, no custom modelfiles.

**The general principle:** the memory a local model uses isn't just its weight file. It's weights + KV cache. KV cache scales linearly with context window size. At 4096 tokens, llama3.2:1b uses ~1.4GB. At 131072 tokens, it needs ~15.9GB. Always check what num_ctx you're actually sending.

---

## The Big Picture

You want to play your CME keyboard (connected to the Pi via USB) and have the MIDI notes show up on your Mac — wirelessly, over your home network — so you can use it in GarageBand, Logic, or anything else. The Pi acts as a bridge: keyboard plugs into Pi, Pi talks to Mac over WiFi using a protocol called **rtpMIDI** (also called Apple Network MIDI).

---

## Why Not Just Plug the Keyboard Into the Mac?

You could. But the Pi setup lets you:
- Keep the keyboard across the room or in another space
- Route MIDI to multiple destinations on the Pi before it hits the Mac
- Build toward more complex setups (running a synth engine on the Pi itself, for example)

---

## The Protocol: rtpMIDI

Macs have built-in support for something called **Network MIDI** — it's in Audio MIDI Setup under the "Network" icon. It uses a protocol called **rtpMIDI** (RTP = Real-Time Protocol, same family as video streaming). Your Mac can send and receive MIDI over WiFi or Ethernet using this protocol natively.

On Linux/Raspberry Pi, there's no built-in support. You need a daemon to implement it. That daemon is **rtpmidid**.

---

## Why We Had to Build From Source

The first instinct was `sudo apt-get install rtpmidid`. Nope — not in the Debian Trixie package repos. Neither is `raveloxmidi` (another option). So we pulled the source from GitHub, compiled it on the Pi itself, and installed the binary manually. The Pi 5 is plenty fast enough to build it in under a minute.

---

## The `--port 5004` Gotcha

This one burned us. We installed rtpmidid, started it as a service, and... nothing. The Mac couldn't see it.

Turns out: **rtpmidid v2 doesn't bind to any network port unless you explicitly pass `--port 5004`**. Without that flag, it runs in "client-only mode" — it can discover other rtpMIDI sessions, but it doesn't advertise itself or accept incoming connections. The help text says "Default 5004" which is misleading — it means *if you use the flag*, 5004 is the default value, not that it runs on 5004 automatically.

The fix was adding `--port 5004` to the systemd `ExecStart` line.

---

## mDNS: How the Mac Finds the Pi Automatically

When rtpmidid starts with `--port 5004`, it registers itself with **Avahi** (the Linux implementation of Apple's Bonjour/mDNS). This is how your Mac's Audio MIDI Setup can see `bryanfoslerpi5` in the Directory without you typing in an IP address. Both devices are on the same WiFi network, and mDNS lets them announce themselves and find each other automatically.

This is the same mechanism that makes AirDrop, AirPlay, and shared printers work on your home network.

---

## ALSA: The Linux MIDI Plumbing

On Linux, MIDI devices and applications are connected through **ALSA** (Advanced Linux Sound Architecture). Think of it like a virtual patch bay. Every MIDI device or app gets a "client" number and "port" number.

In our setup:
- `client 24: C2MIDI Pro` — the CME keyboard, connected via USB
- `client 128: rtpmidid / Bryan's MacBook Air` — the network MIDI connection to the Mac

These two aren't connected by default. You have to wire them together with `aconnect`:

```bash
aconnect "C2MIDI Pro MIDI 1" "Bryan's MacBook Air"   # keyboard -> Mac
aconnect "Bryan's MacBook Air" "C2MIDI Pro MIDI 1"   # Mac -> keyboard
```

The tricky part: ALSA connections are **not persistent**. They vanish if rtpmidid restarts or the Mac disconnects. That's why we wrote `midi-routing.sh` as a systemd service — it waits for the Mac to appear, then re-establishes the connections automatically.

---

## The Duplicate Port Problem

At one point, `aconnect -l` showed two `Bryan's MacBook Air` ports. This happened because:
1. We added the Pi manually in Audio MIDI Setup (by IP)
2. mDNS also auto-discovered the Pi and connected that too

Both connections were live simultaneously, which wasn't harmful but was messy. The fix: remove the manual entry in Audio MIDI Setup and let mDNS handle it automatically.

---

## The Signal Flow (Final State)

```
CME Keyboard → USB → Pi (ALSA client 24)
                          ↕ aconnect (bidirectional)
                     rtpmidid (ALSA client 128)
                          ↕ UDP 5004/5005 over WiFi
                     Mac Network MIDI session ("Pi MIDI")
```

---

---

## Pi 5 USB: What Each Port Actually Does

This one trips people up. The Pi 5 has three kinds of ports and none of them do what you might hope for networking:

- **USB-C** — power delivery only. No data. Can't use it to connect to a Mac.
- **USB-A (x4)** — these are *host* ports. Things plug *into* the Pi here (keyboard, MIDI controller, USB drive). You can't plug the Pi into your Mac through these.
- **Ethernet** — this is your SSH port. Always.

The Pi Zero is the famous one that supports USB networking (OTG mode) — you plug it into your Mac's USB and it shows up as a network device. Pi 5 simply doesn't support that. If you're ever stuck without ethernet, you need WiFi.

---

## SSH: What "Connected" Actually Looks Like

When SSH works, it looks anticlimactic. No splash screen, no loading bar. You just get:

```
bfosler@bryanfoslerpi5:~$
```

That `$` is the Pi waiting for you. If you see that, you're in. If the terminal just hangs after running the SSH command, the Pi isn't reachable — either it's off, on a different network, or SSH isn't running.

Adding `-v` to your SSH command (`ssh -v bfosler@bryanfoslerpi5.local`) shows you exactly where it's stuck. The most common hang point is `Connecting to bryanfoslerpi5.local port 22...` — which means the hostname resolved but the TCP connection never opened.

---

## nmcli: Managing WiFi Networks Like a Pro

`nmcli` is the command-line tool for NetworkManager on Linux. Think of it like your Mac's Network System Settings, but text-based. It manages connections, priorities, and switching.

**Key concept: autoconnect-priority**
Every saved network has a priority number. When the Pi boots or loses a connection, it scans for all networks it knows and connects to whichever has the highest priority that it can actually see. Higher number = preferred.

Our setup:
```
Home WiFi:         priority 10  ← always preferred when home
iPhone Hotspot:    priority  5  ← travel fallback
Mac Int. Sharing:  priority  3  ← last resort
```

This means you never have to think about it — the Pi figures it out. But if you *want* to force a specific network (say you're home but want to test the hotspot), `switch-network.sh iphone` overrides and connects manually.

**The add/switch scripts we wrote** handle all of this so you don't have to remember nmcli syntax. But if you ever need to do it raw:
```bash
nmcli connection show                          # list all saved connections
nmcli connection up iphone-hotspot            # manually connect
nmcli connection modify home connection.autoconnect-priority 10  # set priority
```

---

---

## The Three-Bug BLE MIDI Debugging Story

Getting BLE MIDI working on the Pi took three separate bug hunts, each one hiding behind the previous. It's a good story about how Linux audio/Bluetooth is genuinely layered — and how to read the breadcrumbs.

### Bug 1: The Connection That Immediately Dropped

First symptom: Audio MIDI Setup showed "Pi BT MIDI", you clicked Connect, and it disappeared. Over and over. No error message — just gone.

The first instinct was to check our custom Python GATT server. But the clue was in the bluez logs:

```
profiles/midi/midi.c: MIDI I/O: Failed to read initial request
```

**The culprit:** bluez (the Linux Bluetooth stack) has a **built-in MIDI plugin** (`profiles/midi/midi.c`) that activates the moment any BLE connection comes in. It tries to act as a MIDI client — reading the remote device's MIDI service. But the Mac was connecting as a *client* (looking for a server), not a server, so there was nothing to read. The plugin failed, dropped the connection.

**The fix:** `DisablePlugins = midi` in `/etc/bluetooth/main.conf`. This tells bluez to not load its own MIDI plugin at all, leaving the field clear for our code.

### Bug 2: WirePlumber Doing the Same Thing

After disabling the bluez MIDI plugin, the connection still dropped. Different error this time, buried in the system logs (not the bluetooth service logs):

```
wireplumber: spa.bluez5.midi: org.bluez.GattCharacteristic1.ReadValue() failed: Timeout was reached
```

**The culprit:** WirePlumber (the PipeWire session manager that handles audio routing on modern Linux) has its *own* BLE MIDI implementation. It also intercepts every BLE connection and tries to read MIDI services from the connecting device. Same problem, different layer.

WirePlumber's BLE MIDI is designed for the Pi to act as a Central (connecting *to* BLE MIDI instruments like a wireless keyboard). When the Mac shows up as a Central (expecting the Pi to be the Peripheral/server), WirePlumber tries to read from the Mac and times out.

**The fix:** A WirePlumber config override disabling just the BLE MIDI monitor:
```
/etc/wireplumber/wireplumber.conf.d/50-disable-bluetooth-midi.conf
```
```
wireplumber.profiles = {
  main = {
    monitor.bluez-midi = disabled
  }
}
```

This is surgical — WirePlumber keeps running (it handles all audio routing), just with BLE MIDI disabled.

### Bug 3: The Silent Threading Problem

After both those fixes, the Mac finally stayed connected — `Client subscribed to notifications` appeared in the logs for the first time. But sending test notes produced nothing in GarageBand.

This one was invisible because it produced no error. The code ran, the ALSA poll loop picked up MIDI messages, `notify_midi()` was called — and nothing happened.

**The culprit:** Thread safety with D-Bus. Our ALSA poll loop runs in a background thread. Inside it, we called `self.PropertiesChanged(...)` — a D-Bus signal — directly. But dbus-python signals **must be emitted from the main GLib event loop thread**. Calling them from a background thread silently does nothing. No error, no crash, just silence.

**The fix:** One line change — instead of calling `chrc.notify_midi(data)` directly, schedule it on the main thread:
```python
GLib.idle_add(chrc.notify_midi, data)
```

`GLib.idle_add()` queues a function to run on the main loop the next time it's idle. This is the standard pattern for safely passing work from a background thread to a GLib event loop.

### The Meta-Lesson: Linux Audio/BT Is Deeply Layered

The Pi's Bluetooth stack has at least four players involved in any BLE connection:
1. **The kernel** — raw HCI packets
2. **bluez** — manages connections, has its own MIDI plugin
3. **WirePlumber/PipeWire** — session manager, also does BLE MIDI
4. **Your code** — GATT server registered via D-Bus

When something goes wrong, it could be any of those layers. The key is knowing what logs each one writes:
- **bluez:** `journalctl -u bluetooth`
- **WirePlumber:** `journalctl` (general system log, search for `wireplumber`)
- **kernel:** `dmesg | grep -i bluetooth`
- **Your code:** `journalctl -u bt-midi`

Working top-down (our code first) would have taken forever. Working bottom-up (kernel → bluez → WirePlumber → our code) revealed each issue in sequence.

---

## Ollama: Running AI Models Locally

Ollama is a tool that lets you download and run large language models (LLMs) on your own hardware — no internet required once the model is downloaded, no API costs, no data leaving your network.

Think of it like a local version of ChatGPT running entirely on your Pi. The tradeoff is speed — a 3 billion parameter model on a Pi 5 generates about 8-12 words per second, which feels a bit slow compared to cloud AI but is totally usable.

**The model size vs. speed tradeoff on Pi 5 (8GB):**
- `llama3.2:1b` — 1 billion parameters, 1.3GB, ~15-20 tok/s. Fast but simple.
- `llama3.2:3b` — 3 billion parameters, 2GB, ~8-12 tok/s. Good sweet spot.
- `mistral:7b` — 7 billion parameters, 4.1GB, ~3-5 tok/s. More capable, noticeably slow.

Parameters are roughly analogous to "how much the model knows." More parameters = smarter but slower and heavier. Your 8GB of RAM is the hard ceiling — a model plus its working memory has to fit in RAM or it won't run at all.

**The network access piece:** By default, Ollama only accepts connections from the Pi itself (localhost). We added one environment variable — `OLLAMA_HOST=0.0.0.0:11434` — which tells it to listen on all network interfaces. That's what lets your Mac (or any device on your network) call the API. Without that, you'd have to SSH in and curl from the Pi itself.

---

## How the Pet Cam Avoids a Classic Problem

Here's a problem we had to solve: the motion detection code and the live stream both need to read from the webcam. On Linux, most USB webcams only allow **one process to open them at a time**. If you tried to run a separate streaming app (like `mjpeg-streamer`) alongside the petcam script, one of them would fail with "device busy."

The solution: **one process, two threads**.

Python's `threading` module lets you run multiple things concurrently inside a single program. Our petcam.py does this:
- **Main thread** — reads frames from the camera, runs motion detection, calls Ollama
- **Background thread** — runs a tiny HTTP server that streams those same frames to your browser

Both threads share a single frame buffer (a variable protected by a lock so they don't overwrite each other mid-read). The camera stays open in one place, and both features work simultaneously.

It's like one chef cooking who also hands plates to a waiter — vs. two separate chefs fighting over the same pan.

---

## ntfy.sh: Push Notifications Without an Account

ntfy.sh is beautifully simple. There's no account, no signup. You just POST to a URL that includes your "topic" name, and anyone subscribed to that topic gets the notification.

```bash
curl -d "your dog is on the couch" ntfy.sh/bryanpi-petcam
```

That's the whole API. The topic name is essentially a shared secret — anyone who knows it can send to or subscribe to it. Pick something unique and non-guessable.

The iOS app subscribes to topics and shows them as native push notifications. You can attach images too (send the image as the request body, put the message in a header) — that's how the pet cam sends you a photo of whatever triggered the alert.

---

## Tailscale: A VPN That Just Works

Your Pi is on your home network, behind your router's firewall. From outside — on your phone's cellular, at a coffee shop — there's no way to reach it directly. Your router doesn't know to forward incoming connections to the Pi.

Tailscale solves this by creating a **mesh VPN**. Each device you add (Pi, iPhone, Mac) connects to Tailscale's coordination server and gets a stable private IP in the `100.x.x.x` range. When your phone wants to reach the Pi, Tailscale brokers a direct peer-to-peer connection — your phone and Pi talk directly, encrypted, with Tailscale only handling the handshake.

The result: your Pi gets a permanent address like `100.64.x.x` that your phone can always reach, no matter where either device is. SSH, the live stream, Open-WebUI, the Ollama API — all of it becomes accessible from anywhere with zero extra configuration per service.

Free tier covers everything we need (up to 100 devices).

---

## Bluetooth MIDI (BLE MIDI): A Second Way to Connect

We built two MIDI paths between the Pi and Mac: **rtpMIDI** (over WiFi) and **BLE MIDI** (over Bluetooth). They do the same thing at the application level — MIDI notes and CC messages flow both ways — but the underlying plumbing is completely different.

### What "BLE MIDI" Actually Means

BLE stands for *Bluetooth Low Energy*, which is the modern Bluetooth protocol introduced around 2010. It's distinct from "classic Bluetooth" (the old kind used for headphones, mice, etc.). BLE is designed for small, bursty data — think fitness trackers, smartwatches, MIDI controllers.

Apple pioneered BLE MIDI around 2014 — it's now an official spec from the MIDI Manufacturers Association (MMA). The spec defines exactly how MIDI packets are wrapped into BLE packets: there's a timestamp header, then the MIDI bytes. Mac, iPhone, and iPad all support it natively with zero configuration.

### GATT: The BLE Application Layer

BLE devices communicate through a system called **GATT** (Generic ATTribute Profile). Think of it like a menu at a restaurant:

- **Service**: a category (e.g., "MIDI")
- **Characteristic**: a specific item on the menu (e.g., "MIDI I/O")

The BLE MIDI spec has exactly one service and one characteristic — both identified by fixed UUIDs (long hex numbers). When the Pi's `bt-midi-peripheral.py` starts, it:
1. Registers a GATT server with those UUIDs via **bluez** (Linux's Bluetooth stack)
2. Starts advertising itself over BLE so nearby devices can see it
3. When the Mac connects and subscribes, opens a two-way MIDI pipe

The Mac side is handled entirely by the OS — no drivers, no setup. It just works because Apple built the BLE MIDI client into macOS.

### How We Implemented It

The tricky part: bluez (the Linux BLE stack) doesn't have a simple "start a GATT server" command. You have to communicate with it through **D-Bus**, which is Linux's system message bus (a way for processes to talk to each other). Our Python script does this:

```
bt-midi-peripheral.py
    ├── D-Bus → bluez GATT → registers MidiService + MidiCharacteristic
    ├── D-Bus → bluez LE → starts advertisement ("Pi BT MIDI")
    └── python-rtmidi → opens virtual ALSA port "Pi BT MIDI"

When Mac connects:
    Mac sends MIDI → BLE characteristic → WriteValue() → decode → ALSA out
    ALSA in → ALSA poll thread → encode → notify characteristic → Mac
```

The timestamp thing is subtle: BLE MIDI packets aren't just raw MIDI bytes. Each message gets a 13-bit millisecond timestamp prepended. This lets the receiving end reconstruct precise timing even if packets arrive slightly out of order or late. We encode timestamps when sending, and strip them when receiving.

### Network MIDI vs BLE MIDI: When to Use Which

| | Network MIDI (rtpmidid) | BLE MIDI (bt-midi) |
|--|--|--|
| Requires | Same WiFi network | Within Bluetooth range (~10m) |
| Latency | ~3-5ms (on good WiFi) | ~5-15ms |
| Setup | Audio MIDI Setup → Network | Audio MIDI Setup → Bluetooth |
| Works without WiFi | No | Yes |
| Multiple clients | Yes (any device on network) | One at a time |

Use Network MIDI at home (lower latency, more stable). Use BLE MIDI when you're away from home WiFi — playing in a different room, at a studio, or if your router dies.

---

## Pi as a WiFi Hotspot: Flipping the Network Around

Every setup so far has the Pi acting as a *client* — it connects to your router, iPhone, or Mac's shared network. The hotspot is the opposite: the Pi *becomes the router*.

### Why This Is Useful

If you're in a situation with no home WiFi, no iPhone, and no ethernet (say, setting up in a basement studio with just the Pi and your Mac), you'd be stuck. Tailscale helps for internet access, but you still need a local network for SSH and low-latency MIDI.

The hotspot solves this. The Pi broadcasts its own WiFi network (SSID: `BryanPi5`). Your Mac connects to that network. Now you have a direct Pi ↔ Mac link and everything works: SSH, Network MIDI, Ollama API, Open-WebUI.

### How It Works: `ipv4.method shared`

NetworkManager makes this surprisingly easy. One magic setting — `ipv4.method shared` — does two things:
1. Assigns the Pi a static IP on that network (`192.168.100.1`)
2. Automatically runs `dnsmasq` in the background to hand out DHCP addresses to devices that connect

You don't have to install or configure `dnsmasq` yourself. NetworkManager handles it under the hood when you use AP mode with `shared` addressing. Mac connects to the Pi's network, gets an IP like `192.168.100.10`, and immediately you can `ssh bfosler@192.168.100.1`.

### The One Catch: One Radio, One Role

The Pi 5 has a single WiFi chip. It can either be a *client* (connecting to a network) or an *access point* (hosting a network), but not both at the same time. So when hotspot mode is active:
- Pi is NOT connected to home WiFi, iPhone hotspot, etc.
- Pi has no internet access
- All services work locally (MIDI, Ollama, petcam) but can't reach the internet

This is fine for the use case — you're using it for local MIDI and maybe local AI. Once you're done, `switch-network.sh home` tears down the hotspot and reconnects to your home WiFi normally.

---

## Key Commands to Know

```bash
# See all MIDI connections on the Pi
aconnect -l

# Watch live MIDI events on a port (great for debugging)
aseqdump -p 24:0    # monitor C2MIDI Pro
aseqdump -p 128:1   # monitor Mac connection

# Check rtpmidid is listening on the network
sudo ss -ulnp | grep -E '500[45]'

# See live rtpmidid log (shows latency readings every 10s when Mac is connected)
journalctl -u rtpmidid -f

# Check BLE MIDI service
journalctl -u bt-midi -f
sudo systemctl status bt-midi

# Hotspot
bash setup/switch-network.sh hotspot   # enable
bash setup/switch-network.sh home      # disable
```

---

# Bryan Learns: Running an AI Bot on Your Pi (OpenClaw + Telegram)

## The Big Picture

You now have a personal AI assistant — "Piper" — running 24/7 on your Raspberry Pi. It lives in Telegram, responds to your DMs, can read and write your Notion pages, and remembers things across conversations. The Pi handles all the infrastructure; Anthropic's Claude handles the thinking.

## How It Works

Think of it as a chain: **Telegram → Pi → Claude API → back to Telegram**.

When you send Piper a message, Telegram delivers it to a process called the **OpenClaw gateway** running on your Pi. The gateway figures out which AI model to use, sends your message to Anthropic's API, gets a response, and sends it back to you in Telegram. All of this happens in ~1-2 seconds on Haiku.

The Pi doesn't do the AI heavy lifting — it's just the switchboard. The actual intelligence comes from Claude running in Anthropic's cloud.

## Why Haiku as the Default?

Claude comes in three sizes: Haiku (fast, cheap), Sonnet (smart, moderate cost), and Opus (most capable, most expensive). For everyday tasks — "add this to Notion", "what's the weather", "remind me about X" — Haiku is more than capable and costs roughly 20x less than Opus. Sonnet is set as a fallback for when Piper hits something genuinely complex.

You can always change the model: `npx openclaw config set agents.defaults.model.primary anthropic/claude-sonnet-4-6` on the Pi.

## The 401 Problem: A Lesson in API Keys

We hit a wall early on: Piper kept returning 401 errors ("invalid x-api-key"). The tricky part was the key *looked* valid — it was stored in the right file, the config showed it was loaded. But Anthropic was rejecting it.

The root cause: the key was from a test account or had been revoked. The lesson: **when you get a 401 from Anthropic, don't debug the code — generate a fresh key from console.anthropic.com first.** A bad key looks identical to a good one until you actually make an API call.

## The Terminal Paste Problem

Setting keys on the Pi turned into an unexpected adventure. The challenge: you can't paste a secret key into chat (security), but pasting multi-line Python into Warp terminal caused IndentationError because Warp's input editor treats newlines literally.

The solution that worked: Python's `input()` function inside the REPL, which handles long pastes cleanly without bash getting involved. For any future scripting on the Pi where you need to enter secrets, this is the pattern:

```bash
python3
>>> key = input('Paste key: ')
# paste here, press Enter
>>> # use key...
```

## Skills: Piper's Superpowers

OpenClaw has a skill system — modular capabilities you add like plugins. Each skill has requirements (usually an API key or CLI tool). The ones enabled for Piper:

- **session-memory** — Piper remembers what you talked about last time
- **notion** — Piper can read and write your Notion pages (requires your integration secret in the config env block)
- **obsidian** — available for when/if you use Obsidian vaults

The `npx openclaw skills list` command shows all available skills and which ones are "ready" vs "missing" their requirements.

## User vs System Systemd Services

One gotcha: OpenClaw installs as a *user* systemd service, not a system service. That means `sudo systemctl restart openclaw-gateway` won't work — you need `systemctl --user restart openclaw-gateway` (no sudo). User services run under your account and start when you log in, not at boot (unless you've enabled lingering, which OpenClaw does automatically).


---

## The OpenClaw 3.2 Upgrade Disaster (And What We Learned)

This session was a good reminder that upgrading software without reading the changelog is like updating your iPhone and then wondering why all your apps moved. OpenClaw 3.2 had multiple silent breaking changes that caused everything to stop working at once — which made it feel catastrophic even though each fix was simple once found.

### Breaking Change #1: Plugins Don't Auto-Enable Anymore

In older OpenClaw, if you had a Telegram or Discord token configured, the channel adapter would just... work. In 3.2, all channel adapters ship *disabled by default*. They've been moved to a plugin system.

The symptom was "Unknown channel: telegram" even with a valid token in the config. The fix was just:
```bash
npx openclaw plugins enable telegram
npx openclaw plugins enable discord
```

**Lesson:** Whenever a major version upgrade breaks things across the board, check if the software restructured how features are activated before digging into credentials and networking.

### Breaking Change #2: Upgrade Wiped the Channel Tokens

The upgrade also cleared the Telegram and Discord bot tokens from `openclaw.json`. No warning, no migration. Gone. Had to re-add both.

**Lesson:** Always export or back up app configs before upgrading software that stores auth tokens. A quick `cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak` would have made this a 30-second fix.

### The Silent Systemd Override

OpenClaw's systemd service had a broken drop-in override file (`override.conf`). The file was missing the `[` before `Service]` — so it read `Service]` instead of `[Service]`. Systemd silently ignored the whole file rather than erroring, which means we thought there was a functional override when there wasn't one.

This caused the gateway to bind to loopback-only (127.0.0.1), which meant the WebUI couldn't connect from the Mac. Fix: delete the broken override, set `gateway.bind: "lan"` directly in `openclaw.json`.

**Lesson:** Systemd drop-in files fail silently on syntax errors. If a service isn't behaving the way its config says it should, check the override files — and validate them with `systemd-analyze verify`.

### The Ollama Memory Trap

The plan was to stop using the Anthropic API and run local LLMs on the Pi to save money. Makes sense, right? Pi5 with 8GB RAM, llama3.2:1b is a tiny 1-billion parameter model — should fit easily.

It didn't. OpenClaw reads the model's architecture metadata from Ollama, finds `context_length: 131072` (the max context the architecture *supports*), and passes that as the `num_ctx` parameter when loading the model. This means Ollama tries to allocate memory for 131,000 tokens of context, even if you add `PARAMETER num_ctx 4096` to a custom modelfile — OpenClaw overrides it.

Result: "model requires more system memory (15.9 GiB) than is available (7.4 GiB)."

Even if we'd gotten past the memory issue, Pi5 CPU inference takes 2-4 minutes per response. That's not a chat assistant — that's a very slow email.

**Lesson:** Local LLMs need RAM proportional to context window × precision, not just model parameters. A "1B parameter" model with a 128K context window is not small. Pi5 CPU inference is fine for batch tasks but terrible for interactive chat. For Piper to feel snappy, it needs either a GPU or to use a hosted API.

### Discord's `dmPolicy: "open"` Crash

Setting `dmPolicy` to `"open"` on the Discord channel caused the gateway to crash on startup. The reason: `open` policy means "anyone can message me" — but OpenClaw still validates the `allowFrom` list to have at least one wildcard entry (`"*"`) when in open mode. Without it, the configuration is considered invalid.

The fix was using `allowlist` + adding `"*"` to `allowFrom` for the use cases where we want open access. Counterintuitive naming, but logical once you understand the model.

### The Real Root Cause: Upgrade Without a Migration Guide

All five of these issues happened in the same session because there was no migration path documented. The upgrade script just replaced the binary and moved on. When you're running a homelab AI assistant that touches multiple integrations (Telegram, Discord, WebUI, Ollama, Anthropic), "silent breaking changes × 5" adds up fast.

Going forward: treat OpenClaw upgrades like a database migration — make a backup, read the release notes, test channels one at a time after upgrading.

---

## Quick Secret Entry on zsh (No Echo, No Paste in Chat)

When entering sensitive tokens in a zsh terminal, use:

```bash
read -rs "DISCORD_TOKEN?Paste new Discord bot token: "; echo
```

Then pipe directly to the target command and `unset` the variable right after. This avoids putting secrets in command history, avoids accidental chat paste, and avoids bash-specific `read -p` errors (`read: -p: no coprocess`) that happen in zsh.

---

## "OpenClaw Is Crashing" Was a Mental Model, Not a Fact

Here's the most expensive lesson from a recent reliability investigation. We spent weeks operating under the assumption that "OpenClaw keeps crashing" — based on a steady stream of Telegram notifications saying things were broken. The actual data refuted every word of that sentence.

### The Detective Work

When we finally pulled hard data from systemd, the gateway showed `NRestarts=0` over 11 hours of continuous uptime. The watchdog log showed 91 gateway crashes total across all of history — *every single one of them on 2026-04-19*, zero crashes in the five days since. The gateway was, in fact, *fine*.

So what was firing all those Telegram alerts? `pi_health.py` runs every 5 minutes and checks a list of services. One of those services — Open WebUI — had been intentionally turned off on 04-19 during a memory-cascade cleanup. We never told the watchdog. So twice an hour, for four straight days, it cried wolf about a service we'd deliberately killed.

The Telegram subject line for every alert was the generic `⚠️ Pi Health Alert`. The brain auto-completes the rest. After enough fires, "Pi Health Alert" *means* "OpenClaw is broken" — even when 100% of the recent firings are about a totally different service.

### Three Distinct Failure Modes Hiding in the Logs

While we were in the journal, three real (smaller) issues surfaced. None of them were what we thought was wrong:

1. **97% of the gateway's request errors came from 3 abandoned browser tabs.** Someone (you) had paired the OpenClaw web UI on a phone or other laptop without granting full operator scopes. The tabs were polling `sessions.list` every 30 seconds and getting a 100% rejection rate (459 failures / 24h). Aggregate failure-rate metrics looked alarming until we sliced by connection ID and realized it was a per-client problem, not a per-method problem. Fix: un-pair the orphans. Result: 0 errors in the next hour.

2. **Discord 401 retry loop.** The OpenClaw gateway's Discord bot (separate from Halo's Discord bot, which is critical to remember) was on its 8th of 10 auto-restart attempts before giving up forever. Token had been revoked or the app deleted. Resetting in the developer portal + re-encrypting into the credstore + restarting the gateway was a 30-second fix. The interesting thing is *it never asked for help* — Discord 401s landed in journal logs that nobody was looking at, and the script was about to silently abandon the integration.

3. **`chat.send thinking` rejection.** Session 44 had migrated the `thinking` field from a boolean to a string ("on" / "off"), but the gateway treats absent key as "off" and rejects "off" as an unrecognized value. Every time you used ClawDeck with thinking disabled, you were silently getting a rejection. 13 failures / 24h, six different connection IDs — clearly a code path bug, not one bad client.

### The Actual Lesson

Three takeaways that will outlive this specific bug:

**Process reliability is not user reliability.** A service can have zero crashes and still feel completely broken to the user. NRestarts=0 plus 30% request failure rate is a real signature for "the process is fine but the system is broken." Always ask both questions: is the process alive, AND are its requests succeeding? They have separate answers.

**Generic alert headers compound into false narratives.** If your watchdog sends ten different services all under the subject "Pi Health Alert," operator brain will eventually attribute all of them to whichever service is on your mind. The fix is partly mechanical (alert subjects should name the service) and partly process (always verify the *body* against the count, especially when alerts share headers).

**Watchdog calibration is its own bug class.** The first version of the new `discord_socket_watch.py` script we wrote *immediately* fired two false-positive alerts. First because it grep'd for "starting provider" without the bot identity suffix and matched 595 unrelated subsystem events. Second because it counted reconnect failures from before the token reset (when the bot was legitimately broken). Final logic only flags "currently stuck" state — not "any failure within the window." When you write monitoring code, you need to test it against real history, not synthetic happy-path data — otherwise the first thing it does in production is shout about ghosts.

The whole investigation took ~1h45m and shipped four cleanups. The most valuable artifact wasn't any of the fixes — it was the mental-model correction. "OpenClaw is broken" had been load-bearing in every decision for weeks. Now it isn't.
