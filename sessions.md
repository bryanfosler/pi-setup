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
