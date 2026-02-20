# Pi Setup — bryanfoslerpi5

Raspberry Pi 5 configuration for headless MIDI-over-Network, routing a CME C2MIDI Pro USB controller to a Mac via Apple Network MIDI (rtpMIDI).

## Hardware
- Raspberry Pi 5 (`bryanfoslerpi5.local`)
- CME C2MIDI Pro USB MIDI controller (connected to Pi via USB)
- Mac (Bryan's MacBook Air) on the same LAN

## What's Running

| Service | Purpose |
|---|---|
| `rtpmidid` | Headless rtpMIDI daemon — exposes the Pi to Mac's Audio MIDI Setup |
| `midi-routing` | Bidirectional ALSA routing: C2MIDI Pro ↔ Mac Network MIDI session |

## Fresh Install

SSH into the Pi and run:

```bash
bash <(curl -s https://raw.githubusercontent.com/bryanfosler/pi-setup/main/setup/install-rtpmidid.sh)
```

Then install the MIDI routing service:

```bash
sudo cp systemd/midi-routing.service /etc/systemd/system/
sudo cp setup/midi-routing.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/midi-routing.sh
sudo systemctl daemon-reload
sudo systemctl enable midi-routing
sudo systemctl start midi-routing
```

## Mac Connection (Audio MIDI Setup)

1. Open **Audio MIDI Setup** → **Window → Show MIDI Studio**
2. Double-click **Network**
3. Under **My Sessions**, click **+** → name it `Pi MIDI`
4. `bryanfoslerpi5` should appear automatically in **Directory** (mDNS)
5. Select it → click **Connect**

> If it doesn't auto-appear: click **+** under Directory, set Host to `bryanfoslerpi5.local`, Port `5004`

## MIDI Signal Flow

```
CME C2MIDI Pro (USB) → Pi (ALSA) → rtpmidid → Network → Mac
Mac → Network → rtpmidid → Pi (ALSA) → CME C2MIDI Pro (USB)
```

## Useful Commands

```bash
# SSH into Pi (no password — key already installed)
ssh bfosler@bryanfoslerpi5.local

# Check services
sudo systemctl status rtpmidid
sudo systemctl status midi-routing

# Check MIDI connections
aconnect -l

# Check rtpmidid is listening on UDP 5004/5005
sudo ss -ulnp | grep -E '500[45]'

# Manually re-establish routing if needed
aconnect "C2MIDI Pro MIDI 1" "Bryan's MacBook Air"
aconnect "Bryan's MacBook Air" "C2MIDI Pro MIDI 1"

# View live rtpmidid logs (shows latency ~3-5ms when Mac is connected)
journalctl -u rtpmidid -f
```

## Key Notes

- `rtpmidid` **must** be started with `--port 5004` — without it, the daemon runs in client-only mode and doesn't bind to any network port
- `rtpmidid` is not in Debian Trixie repos — must be built from source
- The midi-routing service waits up to 60s for the Mac to connect before timing out
- Both UDP ports 5004 (RTP data) and 5005 (RTCP control) must be open
