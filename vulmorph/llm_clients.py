"""LLM clients used by VulMorph nodes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


class DeepSeekRepoStructureClient:
    """Small OpenAI-compatible client for repository structure analysis."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "DeepSeekRepoStructureClient":
        load_env_file()
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        return cls(
            api_key=api_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def analyze_repo_structure(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You analyze C/C++ repositories for a vulnerability research pipeline. "
                    "Return concise structured JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Analyze this repository structure. Identify likely project purpose, "
                    "build system, important source directories, test directories, and any "
                    "notes relevant to later function extraction.\n\n"
                    f"{payload}"
                ),
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
