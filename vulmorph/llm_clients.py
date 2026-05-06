"""LLM clients used by VulMorph nodes."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


class DeepSeekRepoStructureClient:
    """Small OpenAI-compatible client for repository structure analysis."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)

    @classmethod
    def from_env(cls) -> "DeepSeekRepoStructureClient":
        load_env_file()
        return cls(
            api_key=_required_env("DEEPSEEK_API_KEY"),
            model=_required_env("DEEPSEEK_MODEL"),
            base_url=_required_env("DEEPSEEK_BASE_URL"),
            timeout=_env_float("DEEPSEEK_TIMEOUT", 180.0),
            max_retries=_env_int("DEEPSEEK_MAX_RETRIES", 2),
        )

    def analyze_repo_structure(self, payload: dict[str, Any]) -> dict[str, Any]:
        system_prompt = _load_prompt("json_system.txt")
        user_prompt = _load_prompt("repo_structure_user.txt").replace("{payload}", str(payload))
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]
        data = self._post_chat(messages)
        content = data["choices"][0]["message"]["content"]
        return {
            "provider": "deepseek",
            "model": self.model,
            "content": content,
            "raw_usage": data.get("usage", {}),
        }

    def classify_bug_fix_commits(self, commits: list[dict[str, Any]]) -> dict[str, Any]:
        system_prompt = _load_prompt("json_system.txt")
        user_prompt = _load_prompt("bug_fix_commit_user.txt").replace(
            "{payload}",
            json.dumps(commits, ensure_ascii=False, indent=2),
        )
        data = self._chat_json(system_prompt, user_prompt)
        return {
            "provider": "deepseek",
            "model": self.model,
            "content": data["choices"][0]["message"]["content"],
            "raw_usage": data.get("usage", {}),
        }

    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self._post_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

    def _post_chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"DeepSeek request failed after {self.max_retries + 1} attempts: {last_exc}") from last_exc


def load_env_file(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from .env without overriding existing env vars."""

    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _load_prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
