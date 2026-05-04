"""Build metadata preparation nodes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def prepare_compile_commands(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure a root-level compile_commands.json exists when possible."""

    repo_result = state.get("repo_result", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot prepare compile_commands.json")

    root = Path(repo_result["path"])
    compile_commands = root / "compile_commands.json"
    if compile_commands.exists():
        return {
            "build_setup": {
                "ok": True,
                "root": str(root),
                "compile_commands_path": str(compile_commands),
                "source": "existing",
            }
        }

    if not (root / "CMakeLists.txt").exists():
        return {
            "build_setup": {
                "ok": False,
                "root": str(root),
                "compile_commands_path": "",
                "errors": ["No root CMakeLists.txt; cannot auto-generate compile_commands.json"],
            }
        }

    build_dir = root / "build-vulmorph"
    configure = subprocess.run(
        [
            "cmake",
            "-S",
            str(root),
            "-B",
            str(build_dir),
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if configure.returncode != 0:
        return _failure(state, configure.stderr.strip() or "cmake configure failed")

    generated = build_dir / "compile_commands.json"
    if not generated.exists():
        return _failure(state, f"cmake did not produce {generated}")

    shutil.copy2(generated, compile_commands)
    return {
        "build_setup": {
            "ok": True,
            "root": str(root),
            "compile_commands_path": str(compile_commands),
            "source": "cmake",
            "build_dir": str(build_dir),
        }
    }


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "build_setup": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
