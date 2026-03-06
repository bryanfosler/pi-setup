"""
Discord webhook sender — stdlib only, no external dependencies.
Used by cron scripts to post reports to a Discord channel.

Required env var:
  DISCORD_REPORTS_WEBHOOK  — webhook URL for the #daily-reports channel

Discord messages have a 2000 char hard limit per post.
Use send_chunked() for longer content.
"""

import json
import os
import urllib.request
import urllib.error


DISCORD_CHUNK_LIMIT = 1990   # leave a small buffer under 2000


class DiscordError(Exception):
    pass


class DiscordWebhook:
    def __init__(self, url: str | None = None, username: str = "Piper"):
        self.url      = url or os.environ.get("DISCORD_REPORTS_WEBHOOK", "")
        self.username = username
        if not self.url:
            raise DiscordError("DISCORD_REPORTS_WEBHOOK not set")

    def _post(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            self.url, data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PiperBot/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    raise DiscordError(f"Discord webhook returned {resp.status}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise DiscordError(f"Discord webhook {e.code}: {detail}") from e

    def send(self, content: str) -> None:
        """Send a single message (must be ≤2000 chars)."""
        if len(content) > DISCORD_CHUNK_LIMIT:
            raise DiscordError(
                f"Message too long ({len(content)} chars). Use send_chunked()."
            )
        self._post({"content": content, "username": self.username})

    def send_chunked(self, content: str) -> None:
        """Split content at newlines and post in ≤2000 char chunks."""
        lines   = content.splitlines(keepends=True)
        chunk   = ""
        for line in lines:
            if len(chunk) + len(line) > DISCORD_CHUNK_LIMIT:
                if chunk.strip():
                    self._post({"content": chunk, "username": self.username})
                chunk = line
            else:
                chunk += line
        if chunk.strip():
            self._post({"content": chunk, "username": self.username})


def post(content: str, username: str = "Piper") -> None:
    """Quick one-liner for scripts that just need to post a message."""
    DiscordWebhook(username=username).send_chunked(content)
