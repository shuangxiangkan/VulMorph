"""Repository acquisition node."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_TARGET_DIR = Path("data/targets")


def repo_slug(repo_url: str) -> str:
    """Create a stable local directory name for a repository URL."""

    parsed = urlparse(repo_url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.removesuffix(".git").strip("/")
        base = path.replace("/", "__") or parsed.netloc
    else:
        base = Path(repo_url).name.removesuffix(".git")
    digest = hashlib.sha1(repo_url.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def acquire_repo(state: dict[str, Any]) -> dict[str, Any]:
    """Clone a remote repo or reuse an existing local repo.

    Expected state["repo_request"] keys:
      - repo_url: required unless repo_path is provided.
      - repo_path: optional existing local repository.
      - target_dir: clone parent directory, default data/targets.
      - force_pull: if true, run git fetch in an existing clone.
    """

    request = dict(state.get("repo_request", {}))
    repo_path = request.get("repo_path")
    repo_url = request.get("repo_url")
    target_dir = Path(request.get("target_dir", DEFAULT_TARGET_DIR))
    force_pull = bool(request.get("force_pull", False))

    if repo_path:
        path = Path(repo_path).expanduser().resolve()
        if not path.exists():
            return _failure(state, f"repo_path does not exist: {path}")
        return {
            "repo_result": {
                "ok": True,
                "source": "local",
                "repo_url": repo_url or "",
                "path": str(path),
                "head": _git_head(path),
            }
        }

    if not repo_url:
        return _failure(state, "repo_request must include repo_url or repo_path")

    target_dir.mkdir(parents=True, exist_ok=True)
    path = (target_dir / repo_slug(str(repo_url))).resolve()
    if path.exists():
        if force_pull:
            fetch = subprocess.run(
                ["git", "-C", str(path), "fetch", "--all", "--tags", "--prune"],
                capture_output=True,
                text=True,
                check=False,
            )
            if fetch.returncode != 0:
                return _failure(state, fetch.stderr.strip() or "git fetch failed")
        source = "existing-clone"
    else:
        clone = subprocess.run(
            ["git", "clone", str(repo_url), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone.returncode != 0:
            return _failure(state, clone.stderr.strip() or "git clone failed")
        source = "cloned"

    return {
        "repo_result": {
            "ok": True,
            "source": source,
            "repo_url": str(repo_url),
            "path": str(path),
            "head": _git_head(path),
        }
    }


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "repo_result": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
