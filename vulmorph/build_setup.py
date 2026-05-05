"""Build metadata preparation nodes."""

from __future__ import annotations

import shutil
import json
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
        _normalize_compile_commands(compile_commands)
        return {
            "build_setup": {
                "ok": True,
                "root": str(root),
                "compile_commands_path": str(compile_commands),
                "source": "existing",
            }
        }

    if (root / "CMakeLists.txt").exists():
        return _prepare_cmake(root, compile_commands, state)

    if (root / "configure.ac").exists() or (root / "Makefile.am").exists() or (root / "autogen.sh").exists():
        return _prepare_autotools(root, compile_commands, state)

    return {
        "build_setup": {
            "ok": False,
            "root": str(root),
            "compile_commands_path": "",
            "errors": [
                "No supported build metadata found. Expected CMakeLists.txt or Autotools files "
                "(configure.ac, Makefile.am, autogen.sh)."
            ],
        }
    }


def _prepare_cmake(root: Path, compile_commands: Path, state: dict[str, Any]) -> dict[str, Any]:
    build_dir = root / "build-vulmorph"
    result = subprocess.run(
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
    if result.returncode != 0:
        return _failure(state, result.stderr.strip() or "cmake configure failed")

    generated = build_dir / "compile_commands.json"
    if not generated.exists():
        return _failure(state, f"cmake did not produce {generated}")

    shutil.copy2(generated, compile_commands)
    _normalize_compile_commands(compile_commands)
    return {
        "build_setup": {
            "ok": True,
            "root": str(root),
            "compile_commands_path": str(compile_commands),
            "source": "cmake",
            "build_dir": str(build_dir),
        }
    }


def _prepare_autotools(root: Path, compile_commands: Path, state: dict[str, Any]) -> dict[str, Any]:
    capture_tool = _capture_tool()
    if capture_tool is None:
        return _failure(
            state,
            "Autotools project detected, but neither bear nor intercept-build is installed. "
            "Install bear or clang-tools to generate compile_commands.json.",
        )

    bootstrap = _run_autotools_bootstrap(root)
    if bootstrap["returncode"] != 0:
        return _failure(state, bootstrap["stderr"] or bootstrap["stdout"] or "Autotools bootstrap failed")

    configure = subprocess.run(
        ["./configure"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if configure.returncode != 0:
        return _failure(state, configure.stderr.strip() or configure.stdout.strip() or "./configure failed")

    if capture_tool == "bear":
        command = ["bear", "--", "make", "-j1"]
    else:
        command = ["intercept-build", "make", "-j1"]
    build = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0 and not compile_commands.exists():
        return _failure(state, build.stderr.strip() or build.stdout.strip() or "captured make failed")
    if not compile_commands.exists():
        return _failure(state, f"{capture_tool} did not produce {compile_commands}")
    _normalize_compile_commands(compile_commands)

    return {
        "build_setup": {
            "ok": True,
            "root": str(root),
            "compile_commands_path": str(compile_commands),
            "source": f"autotools:{capture_tool}",
        }
    }


def _capture_tool() -> str | None:
    if shutil.which("bear"):
        return "bear"
    if shutil.which("intercept-build"):
        return "intercept-build"
    return None


def _run_autotools_bootstrap(root: Path) -> dict[str, Any]:
    if (root / "configure").exists():
        return {"returncode": 0, "stdout": "", "stderr": ""}
    if (root / "autogen.sh").exists():
        command = ["sh", "autogen.sh"]
    elif shutil.which("autoreconf"):
        command = ["autoreconf", "-fi"]
    else:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Autotools project detected, but configure is missing and neither autogen.sh nor autoreconf is available.",
        }
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def _normalize_compile_commands(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for entry in payload:
        if "command" not in entry and isinstance(entry.get("arguments"), list):
            entry["command"] = " ".join(shlex_quote(str(part)) for part in entry["arguments"])
            changed = True
    if changed:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    if all(char.isalnum() or char in "@%_+=:,./-" for char in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "build_setup": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
