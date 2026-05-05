"""Select library-source scope before function extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


NATIVE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
DEFAULT_EXCLUDED_PARTS = {
    ".git",
    "build",
    "build-vulmorph",
    "cmake-build-debug",
    "cmake-build-release",
    "CMakeFiles",
    "test",
    "tests",
    "testing",
    "fuzz",
    "fuzzer",
    "fuzzing",
    "example",
    "examples",
    "doc",
    "docs",
    "benchmark",
    "benchmarks",
    "build-aux",
    "extra",
    "external",
    "gnulib",
    "third_party",
    "tools",
    "vendor",
    "windows",
}


def select_source_scope(state: dict[str, Any]) -> dict[str, Any]:
    """Choose the library source files that should be analyzed by CCScope."""

    repo_result = state.get("repo_result", {})
    structure = state.get("structure_analysis", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot select source scope")
    if not structure.get("ok"):
        return _failure(state, "structure analysis failed; cannot select source scope")

    root = Path(repo_result["path"])
    summary = structure.get("summary", {})
    summary_files = summary.get("native_files") or summary.get("files", [])
    llm_scope = _scope_from_llm(structure.get("llm"))
    candidates = _native_files(summary_files)

    selected = _apply_scope(root, candidates, llm_scope)
    if not selected:
        selected = _heuristic_scope(candidates)

    return {
        "source_scope": {
            "ok": True,
            "root": str(root),
            "source": "llm" if llm_scope else "heuristic",
            "files": selected,
            "count": len(selected),
            "excluded_parts": sorted(DEFAULT_EXCLUDED_PARTS),
            "llm_scope": llm_scope or {},
        }
    }


def _native_files(summary_files: list[dict[str, Any]]) -> list[str]:
    return sorted(
        item["path"]
        for item in summary_files
        if Path(item["path"]).suffix.lower() in NATIVE_SUFFIXES
    )


def _scope_from_llm(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
    elif isinstance(content, dict):
        parsed = content
    else:
        parsed = payload

    files = _string_list(
        parsed,
        "library_source_files",
        "source_files",
        "src_files",
        "core_source_files",
    )
    dirs = _string_list(
        parsed,
        "library_source_dirs",
        "source_dirs",
        "src_dirs",
        "core_source_dirs",
    )
    excludes = _string_list(parsed, "exclude_dirs", "excluded_dirs", "exclude_paths")
    if not files and not dirs and not excludes:
        return None
    return {
        "files": files,
        "dirs": dirs,
        "excludes": excludes,
        "reason": parsed.get("reason") or parsed.get("rationale") or "",
    }


def _string_list(payload: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return sorted({str(item).strip("/") for item in value if str(item).strip()})
    return []


def _apply_scope(root: Path, candidates: list[str], scope: dict[str, Any] | None) -> list[str]:
    if not scope:
        return []
    explicit_files = {path for path in scope.get("files", []) if (root / path).exists()}
    dirs = tuple(path.strip("/") + "/" for path in scope.get("dirs", []) if path.strip())
    excludes = {part for part in scope.get("excludes", []) if part}

    selected = []
    for path in candidates:
        if _has_excluded_part(path, excludes | DEFAULT_EXCLUDED_PARTS):
            continue
        if path in explicit_files or (dirs and path.startswith(dirs)):
            selected.append(path)
    if explicit_files:
        selected.extend(sorted(explicit_files - set(selected)))
    return sorted(set(selected))


def _heuristic_scope(candidates: list[str]) -> list[str]:
    return [
        path
        for path in candidates
        if not _has_excluded_part(path, DEFAULT_EXCLUDED_PARTS)
    ]


def _has_excluded_part(path: str, excluded: set[str]) -> bool:
    name = Path(path).name.lower()
    if name == "test.c" or name.startswith("test_") or "_test" in name or name.endswith("_tests.c"):
        return True
    parts = set(Path(path).parts)
    lower_parts = {part.lower() for part in parts}
    lower_excluded = {part.lower() for part in excluded}
    return bool(lower_parts & lower_excluded)


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "source_scope": {"ok": False, "errors": [message], "files": []},
        "errors": [*state.get("errors", []), message],
    }
