"""Repository structure analysis node."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Protocol


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "__pycache__",
}


class LLMClient(Protocol):
    def analyze_repo_structure(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a structured analysis for a repository summary."""


def analyze_repo_structure(state: dict[str, Any], llm_client: LLMClient | None = None) -> dict[str, Any]:
    """Summarize repo structure and optionally hand it to an LLM client."""

    repo_result = state.get("repo_result", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot analyze structure")

    root = Path(repo_result["path"])
    summary = build_structure_summary(root)
    llm_payload = None
    if llm_client is not None:
        llm_payload = llm_client.analyze_repo_structure(summary)

    return {
        "structure_analysis": {
            "ok": True,
            "root": str(root),
            "summary": summary,
            "llm": llm_payload or heuristic_structure_analysis(summary),
            "used_llm": llm_client is not None,
        }
    }


def build_structure_summary(root: Path, file_limit: int = 500) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    suffixes: Counter[str] = Counter()
    top_dirs: Counter[str] = Counter()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in EXCLUDED_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            relative = path.relative_to(root).as_posix()
            suffix = path.suffix.lower() or "<none>"
            suffixes[suffix] += 1
            top_dirs[relative.split("/", 1)[0] if "/" in relative else "."] += 1
            if len(files) < file_limit:
                files.append(
                    {
                        "path": relative,
                        "suffix": suffix,
                        "size": path.stat().st_size,
                    }
                )

    return {
        "file_count_sampled": len(files),
        "suffix_counts": dict(suffixes.most_common(30)),
        "top_level_counts": dict(top_dirs.most_common(30)),
        "files": files,
    }


def heuristic_structure_analysis(summary: dict[str, Any]) -> dict[str, Any]:
    suffix_counts = summary.get("suffix_counts", {})
    native_count = sum(suffix_counts.get(ext, 0) for ext in (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"))
    build_files = [
        item["path"]
        for item in summary.get("files", [])
        if item["path"] in {"CMakeLists.txt", "Makefile", "configure", "meson.build"}
        or item["path"].endswith(("/CMakeLists.txt", "/Makefile", "/meson.build"))
    ][:30]
    return {
        "purpose_guess": "C/C++ codebase" if native_count else "unknown",
        "native_file_count": native_count,
        "build_files": build_files,
        "notes": [
            "No LLM client was supplied, so this is a deterministic structure summary.",
            "Pass an LLMClient implementation to analyze_repo_structure for richer analysis.",
        ],
    }


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "structure_analysis": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
