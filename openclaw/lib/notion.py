"""
Notion API client — stdlib only, no external dependencies.
All skills that write to Notion import this module.

Required env var: NOTION_API_KEY
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone


NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


class NotionError(Exception):
    pass


class NotionClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("NOTION_API_KEY")
        if not self.token:
            raise NotionError("NOTION_API_KEY not set")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise NotionError(f"Notion API {e.code}: {detail}") from e

    # ── Pages ─────────────────────────────────────────────────────────────

    def create_page(self, database_id: str, properties: dict, icon_emoji: str | None = None) -> dict:
        """Create a page in a database. Returns the full page object."""
        body: dict = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        if icon_emoji:
            body["icon"] = {"type": "emoji", "emoji": icon_emoji}
        return self._request("POST", "/pages", body)

    def update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def get_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")

    # ── Databases ─────────────────────────────────────────────────────────

    def query_database(self, database_id: str, filter_body: dict | None = None,
                       sorts: list | None = None, page_size: int = 10) -> list[dict]:
        """Query a database, returns list of page objects."""
        body: dict = {"page_size": page_size}
        if filter_body:
            body["filter"] = filter_body
        if sorts:
            body["sorts"] = sorts
        result = self._request("POST", f"/databases/{database_id}/query", body)
        return result.get("results", [])

    def get_database_schema(self, database_id: str) -> dict:
        """Returns the database property schema — useful for discovering valid select options."""
        return self._request("GET", f"/databases/{database_id}")

    # ── Property builders ─────────────────────────────────────────────────

    @staticmethod
    def title(text: str) -> dict:
        return {"title": [{"text": {"content": text}}]}

    @staticmethod
    def rich_text(text: str) -> dict:
        return {"rich_text": [{"text": {"content": text}}]}

    @staticmethod
    def select(name: str) -> dict:
        return {"select": {"name": name}}

    @staticmethod
    def multi_select(names: list[str]) -> dict:
        return {"multi_select": [{"name": n} for n in names]}

    @staticmethod
    def date(start: str, end: str | None = None) -> dict:
        """start / end as ISO date strings: YYYY-MM-DD"""
        d: dict = {"start": start}
        if end:
            d["end"] = end
        return {"date": d}

    @staticmethod
    def url(value: str) -> dict:
        return {"url": value}

    @staticmethod
    def number(value: float) -> dict:
        return {"number": value}

    @staticmethod
    def checkbox(checked: bool) -> dict:
        return {"checkbox": checked}

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def page_url(page: dict) -> str:
        return page.get("url", "")

    @staticmethod
    def page_id(page: dict) -> str:
        return page.get("id", "")

    @staticmethod
    def iso_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
