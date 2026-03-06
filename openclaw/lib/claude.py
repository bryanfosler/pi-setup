"""
Claude API wrapper for standalone Pi scripts (n8n-triggered, cron, etc.).
OpenClaw already manages its own Claude calls — this is for scripts that run
outside OpenClaw's context (e.g. digest compiler, research fetcher).

Requires: pip install anthropic  (already present if OpenClaw is installed)

Required env var: ANTHROPIC_API_KEY
"""

import os
import anthropic


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
FALLBACK_MODEL = "claude-sonnet-4-6"


class ClaudeClient:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 1024) -> str:
        """Single-turn completion. Returns the text content."""
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        msg = self.client.messages.create(**kwargs)
        return msg.content[0].text

    def summarize(self, content: str, max_words: int = 150) -> str:
        """Convenience: summarize a block of text."""
        return self.complete(
            f"Summarize the following in under {max_words} words. Be direct, no preamble:\n\n{content}",
            system="You are a concise technical summarizer. Output only the summary."
        )

    def classify(self, content: str, categories: list[str]) -> str:
        """Classify content into one of the given categories."""
        cats = ", ".join(categories)
        result = self.complete(
            f"Classify the following into exactly one category: {cats}\n\nContent:\n{content}\n\nReply with only the category name.",
            system="You are a classifier. Output only one of the allowed category names, nothing else."
        )
        return result.strip()
