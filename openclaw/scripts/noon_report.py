#!/usr/bin/env python3
"""
noon_report.py — Midday Pi/Piper activity report via Discord + Telegram.

Sections:
  1. Piper activity since midnight (sessions, messages, errors from SQLite)
  2. Pi system health (CPU, RAM, temp, disk)
  3. Service status (openclaw-gateway, petcam, ollama, homebridge)

Cron: 0 12 * * * /usr/bin/python3 ~/.openclaw/workspace/scripts/noon_report.py >> /tmp/noon_report.log 2>&1

Required env vars (loaded from ~/.openclaw/openclaw.json):
  DISCORD_REPORTS_WEBHOOK
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import json
import os
import re
import sys
import datetime
import sqlite3
import subprocess
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE  = Path(__file__).resolve().parents[1]
HOME       = Path.home()
PIPER_DB   = HOME / ".openclaw" / "piper_logs.db"

sys.path.insert(0, str(WORKSPACE))
from lib.discord  import DiscordWebhook, DiscordError
from lib.telegram import TelegramClient, TelegramError


# ── Env loader ────────────────────────────────────────────────────────────────
def load_env():
    config = HOME / ".openclaw" / "openclaw.json"
    try:
        d = json.loads(config.read_text())
        for k, v in d.get("env", {}).items():
            os.environ.setdefault(k, str(v))
        # Discord webhook may also be stored in channels config
        os.environ.setdefault(
            "DISCORD_REPORTS_WEBHOOK",
            d.get("channels", {}).get("discord", {}).get("reportsWebhook", ""),
        )
        os.environ.setdefault(
            "TELEGRAM_BOT_TOKEN",
            d.get("channels", {}).get("telegram", {}).get("botToken", ""),
        )
        os.environ.setdefault("TELEGRAM_CHAT_ID", "8585314501")
    except Exception as e:
        print(f"[warn] openclaw.json load failed: {e}", file=sys.stderr)


# ── Section 1: Piper activity ─────────────────────────────────────────────────
def fetch_piper_activity() -> str:
    if not PIPER_DB.exists():
        return "(piper_logs.db not found)"

    try:
        conn = sqlite3.connect(str(PIPER_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        midnight = datetime.datetime.combine(datetime.date.today(), datetime.time.min).isoformat()

        # Sessions started today
        cur.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE started_at >= ?", (midnight,)
        )
        sessions_today = cur.fetchone()["cnt"]

        # Total messages today
        cur.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE created_at >= ?", (midnight,)
        )
        messages_today = cur.fetchone()["cnt"]

        # Errors today
        cur.execute(
            "SELECT COUNT(*) as cnt FROM errors WHERE created_at >= ?", (midnight,)
        )
        errors_today = cur.fetchone()["cnt"]

        conn.close()

        lines = [
            f"  Sessions today: {sessions_today}",
            f"  Messages today: {messages_today}",
        ]
        if errors_today:
            lines.append(f"  Errors today: {errors_today} ⚠️")
        else:
            lines.append("  Errors today: 0")

        return "\n".join(lines)

    except Exception as e:
        return f"(DB error: {e})"


# ── Section 2: System health ──────────────────────────────────────────────────
def run(cmd: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def fetch_system_health() -> str:
    lines = []

    # CPU usage (1-second sample via top)
    cpu_out = run(["top", "-bn1"])
    cpu_pct = ""
    for line in cpu_out.splitlines():
        if "Cpu(s)" in line or "%Cpu" in line:
            # e.g. "%Cpu(s):  3.1 us,  0.6 sy, ..."
            parts = line.split()
            for i, p in enumerate(parts):
                if p in ("us,", "us") and i > 0:
                    cpu_pct = parts[i - 1].replace(",", "") + "%"
                    break
            break
    lines.append(f"  CPU: {cpu_pct or 'n/a'}")

    # RAM
    mem_out = run(["free", "-m"])
    for line in mem_out.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            total, used = int(parts[1]), int(parts[2])
            pct = round(used / total * 100) if total else 0
            lines.append(f"  RAM: {used}MB / {total}MB ({pct}%)")
            break

    # CPU temperature (Pi-specific)
    temp_out = run(["cat", "/sys/class/thermal/thermal_zone0/temp"])
    if temp_out.isdigit():
        temp_c = round(int(temp_out) / 1000, 1)
        lines.append(f"  Temp: {temp_c}°C")

    # Disk usage
    disk_out = run(["df", "-h", "/"])
    for line in disk_out.splitlines():
        if line.startswith("/"):
            parts = line.split()
            lines.append(f"  Disk: {parts[2]} used / {parts[1]} total ({parts[4]})")
            break

    return "\n".join(lines) if lines else "(unavailable)"


# ── Section 3: Service status ─────────────────────────────────────────────────
SERVICES = [
    ("openclaw-gateway", "user"),
    ("petcam",           "system"),
    ("ollama",           "system"),
]

def check_service(name: str, scope: str) -> str:
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd += ["is-active", name]
    result = subprocess.run(cmd, capture_output=True, text=True)
    status = result.stdout.strip()
    icon = "✓" if status == "active" else "✗"
    return f"  {icon} {name}: {status}"


def fetch_service_status() -> str:
    return "\n".join(check_service(name, scope) for name, scope in SERVICES)


# ── Delivery ──────────────────────────────────────────────────────────────────
def send_both(message: str) -> None:
    """Post to Discord (with markdown) and Telegram (plain text)."""
    try:
        DiscordWebhook().send_chunked(message)
        print("[ok] Discord sent.", file=sys.stderr)
    except DiscordError as e:
        print(f"[warn] Discord send failed: {e}", file=sys.stderr)

    try:
        tg = TelegramClient()
        plain = message.replace("**", "")
        plain = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain)
        lines = plain.splitlines(keepends=True)
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) > 4000:
                if chunk.strip():
                    tg._api("sendMessage", {"chat_id": tg.chat_id, "text": chunk})
                chunk = line
            else:
                chunk += line
        if chunk.strip():
            tg._api("sendMessage", {"chat_id": tg.chat_id, "text": chunk})
        print("[ok] Telegram sent.", file=sys.stderr)
    except TelegramError as e:
        print(f"[warn] Telegram send failed: {e}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    load_env()

    now = datetime.datetime.now()
    print(f"[{now.strftime('%H:%M:%S')}] Building noon report...", file=sys.stderr)

    print("[1/3] Piper activity...", file=sys.stderr)
    piper = fetch_piper_activity()

    print("[2/3] System health...", file=sys.stderr)
    health = fetch_system_health()

    print("[3/3] Service status...", file=sys.stderr)
    services = fetch_service_status()

    message = (
        f"**Midday Pi Report — {now.strftime('%A, %B %-d')} @ {now.strftime('%I:%M %p')}**\n"
        f"\n"
        f"**— PIPER ACTIVITY —**\n{piper}\n"
        f"\n"
        f"**— SYSTEM HEALTH —**\n{health}\n"
        f"\n"
        f"**— SERVICES —**\n{services}\n"
    )

    send_both(message)


if __name__ == "__main__":
    main()
