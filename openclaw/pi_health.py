#!/usr/bin/env python3
"""
Pi Health Monitor — zero tokens, direct Telegram Bot API alerts.

Checks:
  - systemd user services: openclaw-gateway, piper-logger
  - systemd system services: petcam, ollama, rtpmidid, bt-midi
  - docker containers: homebridge, open-webui
  - HTTP endpoints: petcam, ollama, open-webui, homebridge
  - Discord connection state (log pattern)
  - Tailscale connectivity

Sends alerts to the PI Alerts Telegram group.
Auto-restarts openclaw-gateway if Discord is detected dead.

State file: ~/.openclaw/pi_health_state.json
  Tracks last-alerted status per service to suppress repeat alerts.

Run via cron every 5 minutes:
  */5 * * * * /usr/bin/python3 /home/bfosler/.openclaw/pi_health.py >> /home/bfosler/.openclaw/pi_health.log 2>&1
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
STATE_FILE = Path.home() / ".openclaw" / "pi_health_state.json"

# Telegram group for alerts (PI Alerts)
ALERT_CHAT_ID = -1003836641590

# How long to suppress repeat alerts for the same issue (minutes)
ALERT_COOLDOWN_MINUTES = 30

# ── Service definitions ───────────────────────────────────────────────────────

SYSTEMD_USER_SERVICES = [
    "openclaw-gateway",
    "piper-logger",
]

SYSTEMD_SYSTEM_SERVICES = [
    "petcam",
    "ollama",
    "rtpmidid",
    "bt-midi",
]

DOCKER_CONTAINERS = [
    "homebridge",
    "open-webui",
]

HTTP_CHECKS = [
    # petcam excluded — port 8080 only binds when GoPro is connected (by design)
    ("ollama",     "http://localhost:11434", 5),
    ("open-webui", "http://localhost:3000",  8),
    ("homebridge", "http://localhost:8581",  8),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_config() -> dict:
    return json.loads(OPENCLAW_CONFIG.read_text())


def get_bot_token(config: dict) -> str:
    return config["channels"]["telegram"]["botToken"]


def send_telegram(token: str, chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        log(f"Alert sent: {text[:80]}...")
    except urllib.error.URLError as e:
        log(f"Failed to send Telegram alert: {e}")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def should_alert(state: dict, key: str) -> bool:
    if key not in state:
        return True
    last = datetime.fromisoformat(state[key]["last_alerted"])
    return datetime.now(timezone.utc) - last > timedelta(minutes=ALERT_COOLDOWN_MINUTES)


def mark_alerted(state: dict, key: str):
    state[key] = {"last_alerted": datetime.now(timezone.utc).isoformat()}


def clear_alert(state: dict, key: str):
    state.pop(key, None)


# ── Checks ────────────────────────────────────────────────────────────────────

def check_systemd(service: str, user: bool = False) -> bool:
    flag = ["--user"] if user else []
    result = subprocess.run(
        ["systemctl"] + flag + ["is-active", "--quiet", service],
        capture_output=True
    )
    return result.returncode == 0


def check_docker(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "true"


def check_http(url: str, timeout: int) -> bool:
    """Any HTTP response (including 4xx/5xx) means the service is up."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        # Got a response — service is listening, just returned an error code
        return True
    except Exception:
        return False


def check_discord_connected() -> tuple:
    """Parse openclaw logs for Discord state. Returns (is_connected, detail)."""
    try:
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        result = subprocess.run(
            ["npx", "openclaw", "logs", "--plain", "--limit", "200"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path.home() / ".openclaw"),
            env=env
        )
        lines = result.stdout.splitlines()
        discord_lines = [
            l for l in lines
            if "gateway/channels/discord" in l or "discord gateway" in l.lower()
        ]

        if not discord_lines:
            return False, "no discord log entries found"

        last = discord_lines[-1]

        if "logged in to discord" in last:
            return True, "connected"

        if "WebSocket connection closed" in last or "closed with code" in last:
            try:
                ts_str = last.split("Z")[0] + "Z"
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - ts
                mins = int(age.total_seconds() / 60)
                return False, f"WebSocket closed {mins}m ago"
            except Exception:
                return False, "WebSocket closed (unknown time)"

        return True, "recent activity"

    except Exception as e:
        return False, f"log check error: {e}"


def check_tailscale() -> bool:
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        return data.get("BackendState") == "Running"
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("=== Pi Health Check ===")

    try:
        config = load_config()
        token = get_bot_token(config)
    except Exception as e:
        log(f"FATAL: cannot load config: {e}")
        sys.exit(1)

    state = load_state()
    failures = []
    recoveries = []

    # Systemd user services
    for svc in SYSTEMD_USER_SERVICES:
        key = f"systemd_user_{svc}"
        ok = check_systemd(svc, user=True)
        log(f"  [{'OK' if ok else 'FAIL'}] systemd user: {svc}")
        if not ok:
            if should_alert(state, key):
                failures.append(f"🔴 <b>{svc}</b> (systemd user) is not running")
                mark_alerted(state, key)
        else:
            if key in state:
                recoveries.append(f"🟢 <b>{svc}</b> (systemd user) recovered")
                clear_alert(state, key)

    # Systemd system services
    for svc in SYSTEMD_SYSTEM_SERVICES:
        key = f"systemd_sys_{svc}"
        ok = check_systemd(svc, user=False)
        log(f"  [{'OK' if ok else 'FAIL'}] systemd system: {svc}")
        if not ok:
            if should_alert(state, key):
                failures.append(f"🔴 <b>{svc}</b> (systemd) is not running")
                mark_alerted(state, key)
        else:
            if key in state:
                recoveries.append(f"🟢 <b>{svc}</b> (systemd) recovered")
                clear_alert(state, key)

    # Docker containers
    for container in DOCKER_CONTAINERS:
        key = f"docker_{container}"
        ok = check_docker(container)
        log(f"  [{'OK' if ok else 'FAIL'}] docker: {container}")
        if not ok:
            if should_alert(state, key):
                failures.append(f"🔴 <b>{container}</b> (docker) is not running")
                mark_alerted(state, key)
        else:
            if key in state:
                recoveries.append(f"🟢 <b>{container}</b> (docker) recovered")
                clear_alert(state, key)

    # HTTP endpoints
    for name, url, timeout in HTTP_CHECKS:
        key = f"http_{name}"
        ok = check_http(url, timeout)
        log(f"  [{'OK' if ok else 'FAIL'}] http: {name} ({url})")
        if not ok:
            if should_alert(state, key):
                failures.append(f"🔴 <b>{name}</b> HTTP not responding ({url})")
                mark_alerted(state, key)
        else:
            if key in state:
                recoveries.append(f"🟢 <b>{name}</b> HTTP recovered")
                clear_alert(state, key)

    # Discord connection
    key = "discord_connected"
    disc_ok, disc_detail = check_discord_connected()
    log(f"  [{'OK' if disc_ok else 'FAIL'}] discord: {disc_detail}")
    if not disc_ok:
        # Auto-restart gateway regardless of alert cooldown
        log("  → Auto-restarting openclaw-gateway for Discord...")
        subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway"])
        if should_alert(state, key):
            failures.append(f"🔴 <b>Discord</b> disconnected ({disc_detail}) — restarting gateway")
            mark_alerted(state, key)
    else:
        if key in state:
            recoveries.append("🟢 <b>Discord</b> reconnected")
            clear_alert(state, key)

    # Tailscale
    key = "tailscale"
    ts_ok = check_tailscale()
    log(f"  [{'OK' if ts_ok else 'FAIL'}] tailscale")
    if not ts_ok:
        if should_alert(state, key):
            failures.append("🔴 <b>Tailscale</b> is not running")
            mark_alerted(state, key)
    else:
        if key in state:
            recoveries.append("🟢 <b>Tailscale</b> recovered")
            clear_alert(state, key)

    # Send alerts
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if failures:
        msg = f"⚠️ <b>Pi Health Alert</b> — {now}\n\n" + "\n".join(failures)
        send_telegram(token, ALERT_CHAT_ID, msg)

    if recoveries:
        msg = f"✅ <b>Pi Recovery</b> — {now}\n\n" + "\n".join(recoveries)
        send_telegram(token, ALERT_CHAT_ID, msg)

    if not failures and not recoveries:
        log("  All services healthy, no alerts needed.")

    save_state(state)
    log("=== Done ===")


if __name__ == "__main__":
    main()
