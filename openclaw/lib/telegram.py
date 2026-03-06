"""
Telegram sender — stdlib only, no external dependencies.
Used by standalone scripts (health checks, n8n-triggered scripts) to push messages.

Required env vars:
  TELEGRAM_BOT_TOKEN  — the bot token for @Piper_RPi5Bot
  TELEGRAM_CHAT_ID    — Bryan's Telegram user ID (8585314501)
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        if not self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN not set")
        if not self.chat_id:
            raise TelegramError("TELEGRAM_CHAT_ID not set")

    def _api(self, method: str, params: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = json.dumps(params).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise TelegramError(f"Telegram API {e.code}: {detail}") from e

    def send(self, text: str, parse_mode: str = "Markdown") -> dict:
        """Send a message to the configured chat."""
        return self._api("sendMessage", {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        })

    def send_alert(self, title: str, body: str) -> dict:
        """Convenience wrapper for structured alerts."""
        msg = f"*{title}*\n{body}"
        return self.send(msg)


def notify(text: str) -> None:
    """Quick one-liner for scripts that just need to push a message."""
    TelegramClient().send(text)
