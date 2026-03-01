# Bryan Learns: Headless Pi MIDI

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
