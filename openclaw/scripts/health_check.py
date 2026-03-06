#!/usr/bin/env python3
"""
Pi5 health check — runs via cron every 6h, alerts via Telegram only on anomaly.
No output = all clear. Messages to Telegram only when something needs attention.

Cron entry (add with: crontab -e):
  0 */6 * * * /usr/bin/python3 ~/.openclaw/workspace/scripts/health_check.py >> /tmp/health_check.log 2>&1

Required env vars (set in crontab or systemd env):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

Thresholds (edit below to tune):
  TEMP_WARN_C      = 70    alert yellow
  TEMP_CRIT_C      = 78    alert red
  DISK_WARN_PCT    = 75
  DISK_CRIT_PCT    = 85
  RAM_WARN_PCT     = 80
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))

from lib.telegram import TelegramClient, TelegramError

# ── Thresholds ────────────────────────────────────────────────────────────────
TEMP_WARN_C   = 70
TEMP_CRIT_C   = 78
DISK_WARN_PCT = 75
DISK_CRIT_PCT = 85
RAM_WARN_PCT  = 80

SERVICES = [
    "openclaw-gateway",
    "petcam",
    "piper-logger",
]

# ── Collectors ────────────────────────────────────────────────────────────────

def cpu_temp() -> float | None:
    """Read Pi CPU temperature in Celsius."""
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return int(raw) / 1000.0
    except Exception:
        return None


def disk_usage_pct(path: str = "/") -> float:
    usage = shutil.disk_usage(path)
    return (usage.used / usage.total) * 100


def ram_usage_pct() -> float:
    try:
        output = subprocess.check_output(["free", "-b"], text=True)
        for line in output.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                total, used = int(parts[1]), int(parts[2])
                return (used / total) * 100
    except Exception:
        pass
    return 0.0


def check_services(names: list[str]) -> list[str]:
    """Returns list of service names that are NOT active."""
    down = []
    for name in names:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", name],
                capture_output=True, text=True
            )
            if result.stdout.strip() != "active":
                down.append(name)
        except Exception:
            down.append(name)
    return down


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    alerts: list[str] = []

    # Temperature
    temp = cpu_temp()
    if temp is not None:
        if temp >= TEMP_CRIT_C:
            alerts.append(f"🔴 CPU temp critical: *{temp:.1f}°C* (threshold: {TEMP_CRIT_C}°C)")
        elif temp >= TEMP_WARN_C:
            alerts.append(f"🟡 CPU temp high: *{temp:.1f}°C* (threshold: {TEMP_WARN_C}°C)")

    # Disk
    disk = disk_usage_pct("/")
    if disk >= DISK_CRIT_PCT:
        alerts.append(f"🔴 Disk critical: *{disk:.0f}%* used (threshold: {DISK_CRIT_PCT}%)")
    elif disk >= DISK_WARN_PCT:
        alerts.append(f"🟡 Disk high: *{disk:.0f}%* used (threshold: {DISK_WARN_PCT}%)")

    # RAM
    ram = ram_usage_pct()
    if ram >= RAM_WARN_PCT:
        alerts.append(f"🟡 RAM high: *{ram:.0f}%* used (threshold: {RAM_WARN_PCT}%)")

    # Services
    down = check_services(SERVICES)
    for name in down:
        alerts.append(f"🔴 Service down: *{name}*")

    if not alerts:
        return  # All clear — no message sent

    # Build alert message
    lines = ["*Pi5 Health Alert*", ""]
    lines.extend(alerts)
    if temp is not None:
        lines.append(f"\nTemp: {temp:.1f}°C | Disk: {disk:.0f}% | RAM: {ram:.0f}%")

    msg = "\n".join(lines)

    try:
        TelegramClient().send(msg)
    except TelegramError as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
