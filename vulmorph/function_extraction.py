"""CCScope-backed function extraction node."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


FUNCTION_KIND_NAMES = {"Function", "Method", "Constructor"}
DEFAULT_CCSCOPE_SRC = Path(__file__).resolve().parents[1] / "CCScope" / "src"


def extract_functions_with_ccscope(state: dict[str, Any]) -> dict[str, Any]:
    """Extract all function-like symbols from the acquired repository."""

    repo_result = state.get("repo_result", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot extract functions")

    root = Path(repo_result["path"])
    try:
        _ensure_ccscope_importable()
        from cc_analyzer import SyncCodebaseAnalyzer
    except Exception as exc:
        return _failure(state, f"CCScope is not importable: {exc}")

    functions: list[dict[str, Any]] = []
    failures: list[str] = []
    scoped_files = set(state.get("source_scope", {}).get("files", []))
    try:
        analyzer = SyncCodebaseAnalyzer.from_root(root)
        preflight = analyzer.preflight().to_dict()
        if not preflight["has_compile_commands"]:
            return _failure(
                state,
                f"compile_commands.json was not found under {root}; CCScope requires it for C/C++ analysis",
            )
        if not preflight["has_clangd"]:
            return _failure(state, "clangd was not found; CCScope requires clangd >= 18")
        if preflight["clangd_compatible"] is False:
            return _failure(state, f"CCScope requires clangd >= 18, found {preflight['clangd_version']}")

        with analyzer:
            files = analyzer.list_source_files(source="merged")
            for file_info in files:
                if scoped_files and file_info.relative_path not in scoped_files:
                    continue
                try:
                    symbols = analyzer.get_document_symbols(file_info.relative_path)
                except Exception as exc:
                    failures.append(f"{file_info.relative_path}: {exc}")
                    continue
                for symbol in symbols:
                    if symbol.kind_name not in FUNCTION_KIND_NAMES:
                        continue
                    item = symbol.to_dict()
                    item["file"] = file_info.relative_path
                    item["snippet"] = _snippet_for_symbol(analyzer, file_info.relative_path, item)
                    functions.append(item)
    except Exception as exc:
        return _failure(state, f"CCScope analysis failed: {exc}")

    return {
        "function_extraction": {
            "ok": True,
            "root": str(root),
            "count": len(functions),
            "functions": functions,
            "failures": failures,
            "preflight": preflight,
            "source_scope_count": len(scoped_files),
        }
    }


def _ensure_ccscope_importable() -> None:
    if DEFAULT_CCSCOPE_SRC.exists():
        sys.path.insert(0, str(DEFAULT_CCSCOPE_SRC))
    if "CLANGD_PATH" not in os.environ:
        for candidate in ("/usr/bin/clangd-18", "/usr/local/bin/clangd-18"):
            if Path(candidate).exists():
                os.environ["CLANGD_PATH"] = candidate
                break


def _snippet_for_symbol(analyzer: Any, relative_path: str, symbol: dict[str, Any]) -> dict[str, Any] | None:
    location = symbol.get("location") or {}
    raw_range = location.get("range") or symbol.get("range")
    if not raw_range:
        return None
    start = max(1, int(raw_range["start"]["line"]) - 2)
    end = int(raw_range["end"]["line"]) + 2
    try:
        return analyzer.get_snippet(relative_path, start, end).to_dict()
    except Exception:
        return None


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "function_extraction": {"ok": False, "errors": [message], "functions": []},
        "errors": [*state.get("errors", []), message],
    }
