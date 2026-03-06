#!/usr/bin/env python3
"""
daily_digest.py — 7am morning briefing via Discord.

Sections:
  1. High-priority Notion tasks (High priority, not Done)
  2. Training week vs plan + Claude coaching note
  3. PM headlines (RSS feeds + Reddit)

Side effect: writes ~/ObsidianVault/AI Knowledge/Training/YYYY-WXX.md

Cron: 0 7 * * * /usr/bin/python3 ~/.openclaw/workspace/scripts/daily_digest.py >> /tmp/daily_digest.log 2>&1

Required env vars (loaded from ~/.openclaw/openclaw.json):
  NOTION_API_KEY, NOTION_TASKS_DB_ID
  DISCORD_REPORTS_WEBHOOK
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  ANTHROPIC_API_KEY
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN, STRAVA_ATHLETE_ID
"""

import json
import os
import re
import sys
import datetime
import subprocess
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE      = Path(__file__).resolve().parents[1]
HOME           = Path.home()
OBSIDIAN_DIR   = HOME / "ObsidianVault" / "AI Knowledge" / "Training"
TRAINING_PLAN  = OBSIDIAN_DIR / "Eugene Training Plan.md"
STRAVA_REFRESH = WORKSPACE / "skills" / "strava" / "scripts" / "strava_refresh.py"

sys.path.insert(0, str(WORKSPACE))
from lib.notion   import NotionClient, NotionError
from lib.discord  import DiscordWebhook, DiscordError
from lib.telegram import TelegramClient, TelegramError

# Inline Claude call — stdlib only, no anthropic package needed
def claude_complete(prompt: str, system: str, max_tokens: int = 300) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "(ANTHROPIC_API_KEY not set)"
    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["content"][0]["text"]

# ── Config ────────────────────────────────────────────────────────────────────
PLAN_START = datetime.date(2026, 1, 5)
RACE_DATE  = datetime.date(2026, 4, 26)
RACE_NAME  = "Eugene Marathon"

RSS_FEEDS = [
    ("Lenny's",        "https://www.lennysnewsletter.com/feed"),
    ("Product Talk",   "https://www.producttalk.org/feed/"),
    ("SVPG",           "https://www.svpg.com/feed/"),
    ("John Cutler",    "https://cutlefish.substack.com/feed"),
    ("Melissa Perri",  "https://melissaperri.substack.com/feed"),
    ("Ken Norton",     "https://knorton.substack.com/feed"),
]

REDDIT_SUBS = [
    "ProductManagement",
    "ProductManagementLife",   # more active sub
    "startups",
    "agile",
]

MIN_REDDIT_SCORE = 20   # Skip low-signal posts
MAX_PER_SOURCE   = 2    # Max items per feed/subreddit
HEADLINE_COUNT   = 8    # Total headlines in digest


# ── Env loader ────────────────────────────────────────────────────────────────
def load_env():
    """
    Load env vars from ~/.openclaw/openclaw.json.
    Reads from:
      - top-level 'env' block  (NOTION_API_KEY, ANTHROPIC_API_KEY, Strava creds, etc.)
      - channels.telegram.botToken  → TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID defaults to Bryan's user ID if not set.
    """
    config = HOME / ".openclaw" / "openclaw.json"
    try:
        d = json.loads(config.read_text())

        # Primary env block
        for k, v in d.get("env", {}).items():
            os.environ.setdefault(k, str(v))

        # Discord webhook lives in channels config if not in env block
        os.environ.setdefault(
            "DISCORD_REPORTS_WEBHOOK",
            d.get("channels", {}).get("discord", {}).get("reportsWebhook", ""),
        )

        # Telegram bot token lives in channels config
        os.environ.setdefault(
            "TELEGRAM_BOT_TOKEN",
            d.get("channels", {}).get("telegram", {}).get("botToken", ""),
        )
        os.environ.setdefault("TELEGRAM_CHAT_ID", "8585314501")

    except Exception as e:
        print(f"[warn] openclaw.json load failed: {e}", file=sys.stderr)


# ── Training plan parser ──────────────────────────────────────────────────────
def parse_weekly_targets() -> dict[int, int]:
    """
    Parse the markdown table in Eugene Training Plan.md.
    Returns {week_num: target_miles}.
    Table rows look like: | 9 | Mar 2-8 | ... | 40 |
    """
    try:
        text = TRAINING_PLAN.read_text()
    except FileNotFoundError:
        print(f"[warn] Training plan not found: {TRAINING_PLAN}", file=sys.stderr)
        return {}

    targets = {}
    # Match rows: first col is week number (1-16), last col before trailing | is total miles
    for line in text.splitlines():
        m = re.match(r'^\|\s*(\d{1,2})\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|\s*(\d+)\s*\|', line)
        if m:
            week_num = int(m.group(1))
            if 1 <= week_num <= 16:
                targets[week_num] = int(m.group(2))
    return targets


def current_plan_week() -> int:
    """Week number (1-16) based on days elapsed since plan start."""
    delta = (datetime.date.today() - PLAN_START).days
    return max(1, min(16, delta // 7 + 1))


# ── Section 1: Notion tasks ───────────────────────────────────────────────────
def fetch_tasks() -> str:
    today_str = datetime.date.today().isoformat()
    try:
        db_id = os.environ.get("NOTION_TASKS_DB_ID", "")
        if not db_id:
            return "(NOTION_TASKS_DB_ID not set)"

        notion = NotionClient()
        pages = notion.query_database(
            db_id,
            filter_body={
                "and": [
                    {"property": "Priority", "select": {"equals": "High"}},
                    {"property": "Status",   "select": {"does_not_equal": "Done"}},
                ]
            },
            sorts=[{"property": "Due", "direction": "ascending"}],
            page_size=10,
        )

        if not pages:
            return "Nothing in the queue. Clean slate."

        lines = []
        for p in pages:
            props = p.get("properties", {})

            title_parts = props.get("Name", {}).get("title", [])
            title = title_parts[0]["text"]["content"] if title_parts else "Untitled"

            due = props.get("Due", {}).get("date")
            due_str = ""
            if due and due.get("start"):
                if due["start"] < today_str:
                    due_str = f" [overdue: {due['start']}]"
                elif due["start"] == today_str:
                    due_str = " [due today]"
                else:
                    due_str = f" [due {due['start']}]"

            status = props.get("Status", {}).get("select", {}).get("name", "")
            icon = ">>" if status == "In Progress" else "-"
            lines.append(f"{icon} {title}{due_str}")

        return "\n".join(lines)

    except NotionError as e:
        return f"(Notion error: {e})"
    except Exception as e:
        return f"(Tasks unavailable: {e})"


# ── Section 2: Training ───────────────────────────────────────────────────────
def get_strava_token() -> str | None:
    try:
        result = subprocess.run(
            [sys.executable, str(STRAVA_REFRESH)],
            capture_output=True, text=True, timeout=15,
            env={**os.environ},
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"[warn] Strava token refresh: {result.stderr.strip()}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[warn] Strava subprocess: {e}", file=sys.stderr)
        return None


def strava_get(token: str, url: str) -> list | dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_strava_this_week(token: str) -> dict:
    today  = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    after  = int(datetime.datetime.combine(monday, datetime.time.min).timestamp())
    url    = f"https://www.strava.com/api/v3/athlete/activities?after={after}&per_page=100"
    try:
        activities = strava_get(token, url)
    except Exception as e:
        return {"error": str(e)}

    miles = 0.0
    runs  = 0
    for a in activities:
        if a.get("type") == "Run":
            miles += a.get("distance", 0) * 0.000621371
            runs  += 1
    return {"miles": round(miles, 1), "runs": runs}


def fetch_strava_recent_weeks(token: str, n: int = 4) -> list[dict]:
    after = int((datetime.datetime.now() - datetime.timedelta(weeks=n)).timestamp())
    url   = f"https://www.strava.com/api/v3/athlete/activities?after={after}&per_page=200"
    try:
        activities = strava_get(token, url)
    except Exception:
        return []

    weeks: dict[str, dict] = {}
    for a in activities:
        if a.get("type") != "Run":
            continue
        ds = a.get("start_date_local", "")[:10]
        if not ds:
            continue
        wk = datetime.date.fromisoformat(ds).strftime("%G-W%V")
        if wk not in weeks:
            weeks[wk] = {"week": wk, "miles": 0.0, "runs": 0}
        weeks[wk]["miles"] = round(weeks[wk]["miles"] + a["distance"] * 0.000621371, 1)
        weeks[wk]["runs"]  += 1

    return sorted(weeks.values(), key=lambda x: x["week"])


def get_coaching_note(week_num, target_miles, actual_miles, run_count,
                      days_left, days_to_race, recent_weeks, weekly_targets) -> str:
    try:
        recent_str = "\n".join(
            f"  {w['week']}: {w['miles']}mi ({w['runs']} runs)"
            for w in recent_weeks[-4:]
        ) or "  No recent data"

        upcoming_str = "\n".join(
            f"  Week {wk}: {weekly_targets[wk]}mi target"
            for wk in range(week_num, min(week_num + 3, 17))
            if wk in weekly_targets
        )

        prompt = (
            f"Bryan is training for {RACE_NAME} in {days_to_race} days.\n"
            f"Plan week: {week_num}/16 | Target: {target_miles or 'N/A'}mi | "
            f"Actual so far: {actual_miles}mi ({run_count} runs) | Days left: {days_left}\n"
            f"Recent weeks:\n{recent_str}\n"
            f"Upcoming targets:\n{upcoming_str}\n\n"
            "Give 3-4 coaching bullets specific to this data. "
            "Direct, brief, actionable. Start each with a bullet character."
        )
        system = (
            "You are a running coach giving a morning briefing. "
            "Be direct and data-driven. No preamble. Each point on its own line starting with -"
        )
        return claude_complete(prompt, system=system, max_tokens=300)
    except Exception as e:
        return f"(Coaching unavailable: {e})"


def write_obsidian_weekly(week_num, actual_miles, run_count, target_miles, coaching):
    try:
        today  = datetime.date.today()
        iso_wk = today.strftime("%G-W%V")
        monday = today - datetime.timedelta(days=today.weekday())
        sunday = monday + datetime.timedelta(days=6)
        OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
        out = OBSIDIAN_DIR / f"{iso_wk}.md"
        out.write_text(
            f"---\n"
            f"source: piper-daily-digest\n"
            f"ai: true\n"
            f"week: {iso_wk}\n"
            f"date: {today.isoformat()}\n"
            f"tags: [piper, strava, training]\n"
            f"---\n\n"
            f"# Training Week {iso_wk} ({monday.strftime('%b %-d')} - {sunday.strftime('%b %-d')})\n\n"
            f"## Running\n"
            f"- Distance: {actual_miles} mi across {run_count} runs\n"
            f"- Plan target: {target_miles or 'N/A'} mi (Week {week_num}/16)\n\n"
            f"## Coaching Notes\n{coaching}\n\n"
            f"---\n_Updated by daily_digest.py on {today.isoformat()}_\n"
        )
        print(f"[ok] Obsidian weekly written: {out.name}", file=sys.stderr)
    except Exception as e:
        print(f"[warn] Obsidian write failed: {e}", file=sys.stderr)


def build_training_section() -> str:
    today         = datetime.date.today()
    days_to_race  = (RACE_DATE - today).days
    week_num      = current_plan_week()
    targets       = parse_weekly_targets()
    target_miles  = targets.get(week_num)
    days_left     = 6 - today.weekday()   # 0=Mon ... 6=Sun

    token    = get_strava_token()
    wk_data  = fetch_strava_this_week(token) if token else {"error": "token failed"}
    recent   = fetch_strava_recent_weeks(token, 4) if token else []

    actual_miles = wk_data.get("miles", 0.0)
    run_count    = wk_data.get("runs", 0)
    strava_err   = wk_data.get("error")

    # Header
    if target_miles:
        remaining = round(target_miles - actual_miles, 1)
        header = f"Week {week_num}/16 — {actual_miles}mi / {target_miles}mi target"
        if remaining > 0:
            header += f" ({remaining}mi to go, {days_left}d left)"
        else:
            header += " — target hit!"
    else:
        header = f"Week {week_num}/16 — {actual_miles}mi this week"

    header += f"\n{RACE_NAME} is {days_to_race} days away."

    # Coaching
    if strava_err:
        coaching = f"(Strava unavailable: {strava_err})"
    else:
        coaching = get_coaching_note(
            week_num=week_num, target_miles=target_miles,
            actual_miles=actual_miles, run_count=run_count,
            days_left=days_left, days_to_race=days_to_race,
            recent_weeks=recent, weekly_targets=targets,
        )
        write_obsidian_weekly(week_num, actual_miles, run_count, target_miles, coaching)

    return f"{header}\n\n{coaching}"


# ── Section 3: PM Headlines ───────────────────────────────────────────────────
def fetch_rss(name: str, url: str) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PiperDigest/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            root = ET.fromstring(resp.read())

        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.findall(".//item"):
            t = item.find("title")
            l = item.find("link")
            if t is not None and t.text:
                items.append({"source": name, "title": t.text.strip(),
                               "url": l.text.strip() if l is not None and l.text else ""})
            if len(items) == MAX_PER_SOURCE:
                break

        if not items:
            for entry in root.findall(".//atom:entry", ns):
                t = entry.find("atom:title", ns)
                l = entry.find("atom:link", ns)
                if t is not None and t.text:
                    items.append({"source": name, "title": t.text.strip(),
                                   "url": l.get("href", "") if l is not None else ""})
                if len(items) == MAX_PER_SOURCE:
                    break

        return items
    except Exception as e:
        print(f"[warn] RSS {name}: {e}", file=sys.stderr)
        return []


def fetch_reddit(sub: str) -> list[dict]:
    try:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=10"
        req = urllib.request.Request(url, headers={"User-Agent": "PiperDigest/1.0 by u/bfosler"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        items = []
        for post in data.get("data", {}).get("children", []):
            p = post.get("data", {})
            if p.get("score", 0) < MIN_REDDIT_SCORE:
                continue
            items.append({
                "source": f"r/{sub}",
                "title":  p.get("title", "").strip(),
                "url":    f"https://reddit.com{p.get('permalink', '')}",
                "score":  p.get("score", 0),
            })
            if len(items) == MAX_PER_SOURCE:
                break
        return items
    except Exception as e:
        print(f"[warn] Reddit r/{sub}: {e}", file=sys.stderr)
        return []


def fetch_headlines() -> str:
    all_items: list[dict] = []
    for name, url in RSS_FEEDS:
        all_items.extend(fetch_rss(name, url))
    for sub in REDDIT_SUBS:
        all_items.extend(fetch_reddit(sub))

    if not all_items:
        return "(Headlines unavailable)"

    seen:   set[str] = set()
    unique: list[dict] = []
    for item in all_items:
        key = item["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Sort Reddit by score (RSS items get 9999 so they stay near top)
    unique.sort(key=lambda x: x.get("score", 9999), reverse=True)
    selected = unique[:HEADLINE_COUNT]

    lines = []
    for item in selected:
        url = item.get("url", "")
        if url:
            lines.append(f"- **[{item['source']}]** [{item['title']}]({url})")
        else:
            lines.append(f"- **[{item['source']}]** {item['title']}")
    return "\n".join(lines)


# ── Delivery ──────────────────────────────────────────────────────────────────
def _strip_md(text: str) -> str:
    """Strip Discord markdown for Telegram plain-text delivery."""
    text = text.replace("**", "")
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [title](url) → title
    return text


def send_both(message: str) -> None:
    """Post to Discord (with markdown) and Telegram (plain text)."""
    try:
        DiscordWebhook().send_chunked(message)
        print("[ok] Discord sent.", file=sys.stderr)
    except DiscordError as e:
        print(f"[warn] Discord send failed: {e}", file=sys.stderr)

    try:
        tg = TelegramClient()
        plain = _strip_md(message)
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

    today    = datetime.date.today()
    day_name = today.strftime("%A, %B %-d")
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Building daily digest for {day_name}...", file=sys.stderr)

    print("[1/3] Notion tasks...", file=sys.stderr)
    tasks = fetch_tasks()

    print("[2/3] Training...", file=sys.stderr)
    training = build_training_section()

    print("[3/3] Headlines...", file=sys.stderr)
    headlines = fetch_headlines()

    message = (
        f"**Good morning! {day_name}**\n"
        f"\n"
        f"**— HIGH PRIORITY TASKS —**\n{tasks}\n"
        f"\n"
        f"**— TRAINING —**\n{training}\n"
        f"\n"
        f"**— PM READS —**\n{headlines}\n"
    )

    send_both(message)


if __name__ == "__main__":
    main()
