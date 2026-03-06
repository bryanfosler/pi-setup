"""
GitHub API client — stdlib only, no external dependencies.
Used by the GitHub dev agent skill and n8n-triggered scripts.

Required env var: GITHUB_TOKEN
"""

import json
import os
import urllib.request
import urllib.error
from typing import Any


class GitHubError(Exception):
    pass


class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise GitHubError("GITHUB_TOKEN not set")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self.BASE}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise GitHubError(f"GitHub API {e.code} {method} {path}: {detail}") from e

    # ── Issues ────────────────────────────────────────────────────────────

    def list_issues(self, owner: str, repo: str, state: str = "open",
                    labels: str = "", per_page: int = 30) -> list[dict]:
        path = f"/repos/{owner}/{repo}/issues?state={state}&per_page={per_page}"
        if labels:
            path += f"&labels={labels}"
        return self._request("GET", path)

    def get_issue(self, owner: str, repo: str, number: int) -> dict:
        return self._request("GET", f"/repos/{owner}/{repo}/issues/{number}")

    def add_labels(self, owner: str, repo: str, number: int, labels: list[str]) -> dict:
        return self._request("POST", f"/repos/{owner}/{repo}/issues/{number}/labels",
                             {"labels": labels})

    def create_comment(self, owner: str, repo: str, number: int, body: str) -> dict:
        return self._request("POST", f"/repos/{owner}/{repo}/issues/{number}/comments",
                             {"body": body})

    def update_issue(self, owner: str, repo: str, number: int, **kwargs) -> dict:
        """Update title, body, state, labels, assignees, milestone."""
        return self._request("PATCH", f"/repos/{owner}/{repo}/issues/{number}", kwargs)

    # ── Repos ─────────────────────────────────────────────────────────────

    def list_repos(self, username: str, per_page: int = 30) -> list[dict]:
        return self._request("GET", f"/users/{username}/repos?per_page={per_page}&sort=updated")

    def get_repo(self, owner: str, repo: str) -> dict:
        return self._request("GET", f"/repos/{owner}/{repo}")

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def parse_repo(repo_string: str) -> tuple[str, str]:
        """Parse 'owner/repo' string into (owner, repo) tuple."""
        parts = repo_string.strip().split("/")
        if len(parts) != 2:
            raise GitHubError(f"Invalid repo format: '{repo_string}'. Expected 'owner/repo'.")
        return parts[0], parts[1]
