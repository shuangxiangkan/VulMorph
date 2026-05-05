"""LLM clients used by VulMorph nodes."""

from __future__ import annotations

import os
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
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "DeepSeekRepoStructureClient":
        load_env_file()
        return cls(
            api_key=_required_env("DEEPSEEK_API_KEY"),
            model=_required_env("DEEPSEEK_MODEL"),
            base_url=_required_env("DEEPSEEK_BASE_URL"),
        )

    def analyze_repo_structure(self, payload: dict[str, Any]) -> dict[str, Any]:
        system_prompt = _load_prompt("repo_structure_system.txt")
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
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return {
            "provider": "deepseek",
            "model": self.model,
            "content": content,
            "raw_usage": data.get("usage", {}),
        }


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
