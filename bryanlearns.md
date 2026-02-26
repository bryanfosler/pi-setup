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
```
