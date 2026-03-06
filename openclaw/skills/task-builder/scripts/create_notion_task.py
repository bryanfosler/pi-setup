#!/usr/bin/env python3
"""
Create a structured task in Notion.
Called by the task-builder OpenClaw skill after the coaching conversation.

Usage:
  python3 create_notion_task.py --title "..." --project "..." --priority High
  python3 create_notion_task.py --title "..." --project "..." --priority Medium \
      --labels "research,infra" --due 2026-03-15 --notes "See issue #12"
  python3 create_notion_task.py ... --dry-run   # preview without writing

Required env vars:
  NOTION_API_KEY       — Notion integration token
  NOTION_TASKS_DB_ID   — Notion database ID for tasks
                         (create a Tasks DB or use the existing issues DB)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing from lib/ in the workspace root
workspace = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(workspace))

from lib.notion import NotionClient, NotionError


VALID_PRIORITIES = ["High", "Medium", "Low"]
VALID_STATUSES = ["Backlog", "In Progress", "Done"]

# ISO week and month helpers
def iso_week() -> str:
    today = datetime.now(timezone.utc)
    return f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"

def iso_month() -> str:
    today = datetime.now(timezone.utc)
    return f"{today.year}-{today.month:02d}"


def build_properties(args: argparse.Namespace) -> dict:
    notion = NotionClient.__new__(NotionClient)  # static methods only

    props: dict = {
        "Name": NotionClient.title(args.title),
        "Status": NotionClient.select("Backlog"),
        "Priority": NotionClient.select(args.priority),
        "Source": NotionClient.select("Piper"),
        "Week": NotionClient.select(iso_week()),
        "Month": NotionClient.select(iso_month()),
    }

    if args.project:
        props["Project"] = NotionClient.select(args.project)

    if args.notes:
        props["Notes"] = NotionClient.rich_text(args.notes)

    if args.due:
        props["Due"] = NotionClient.date(args.due)

    if args.labels:
        label_list = [l.strip() for l in args.labels.split(",") if l.strip()]
        if label_list:
            props["Labels"] = NotionClient.multi_select(label_list)

    return props


def main():
    parser = argparse.ArgumentParser(description="Create a Notion task from Piper")
    parser.add_argument("--title",    required=True,  help="Task title")
    parser.add_argument("--project",  required=True,  help="Project name (select value)")
    parser.add_argument("--priority", default="Medium",
                        choices=VALID_PRIORITIES,     help="Priority level")
    parser.add_argument("--labels",   default="",     help="Comma-separated labels")
    parser.add_argument("--due",      default="",     help="Due date (YYYY-MM-DD)")
    parser.add_argument("--notes",    default="",     help="Additional context or notes")
    parser.add_argument("--dry-run",  action="store_true",
                                                       help="Preview without writing to Notion")
    args = parser.parse_args()

    # Validate due date format
    if args.due:
        try:
            datetime.strptime(args.due, "%Y-%m-%d")
        except ValueError:
            print(f"Error: --due must be in YYYY-MM-DD format, got '{args.due}'", file=sys.stderr)
            sys.exit(1)

    db_id = os.environ.get("NOTION_TASKS_DB_ID")
    if not db_id:
        print("Error: NOTION_TASKS_DB_ID env var not set", file=sys.stderr)
        print("Set it in ~/.openclaw/openclaw.json under the 'env' block.", file=sys.stderr)
        sys.exit(1)

    properties = build_properties(args)

    if args.dry_run:
        print("=== DRY RUN — nothing will be written ===")
        print(json.dumps({"database_id": db_id, "properties": properties}, indent=2))
        sys.exit(0)

    try:
        client = NotionClient()
        page = client.create_page(db_id, properties, icon_emoji="✅")
        url = NotionClient.page_url(page)
        page_id = NotionClient.page_id(page)
        print(f"Created: {url}")
        # Also emit structured output for OpenClaw to parse
        print(json.dumps({"ok": True, "page_id": page_id, "url": url}))
    except NotionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
