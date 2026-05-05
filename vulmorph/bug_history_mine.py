"""Mine historical bug-fix commits and patch snippets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .embeddings import _repo_output_name


BUG_FIX_KEYWORDS: dict[str, int] = {
    "cve": 12,
    "security": 10,
    "vulnerab": 10,
    "overflow": 9,
    "underflow": 9,
    "out-of-bounds": 9,
    "oob": 9,
    "bounds": 7,
    "integer": 6,
    "crash": 6,
    "fuzz": 5,
    "oss-fuzz": 6,
    "asan": 5,
    "ubsan": 5,
    "invalid": 4,
    "corrupt": 4,
    "fix": 3,
    "bug": 3,
}

NATIVE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
FALLBACK_OUTPUT_DIR = Path("data/bugfixes")


def find_bug_fix_commits(state: dict[str, Any]) -> dict[str, Any]:
    """Rank historical commits that look like bug/security fixes."""

    repo_result = state.get("repo_result", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot search bug-fix commits", "bug_fix_commits")

    request = dict(state.get("repo_request", {}))
    max_commits = int(request.get("bug_fix_max_commits", 20))
    log_limit = int(request.get("bug_fix_log_limit", 500))
    batch_size = max(1, int(request.get("bug_fix_llm_batch_size", 100)))
    mode = request.get("bug_fix_commit_filter", "llm")
    repo_path = Path(repo_result["path"])

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            f"-n{log_limit}",
            "--date=iso",
            "--pretty=format:%H%x1f%ad%x1f%s",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return _failure(state, result.stderr.strip() or "git log failed", "bug_fix_commits")

    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        commit, date, subject = parts
        score, matched = _score_subject(subject)
        commits.append(
            {
                "commit": commit,
                "date": date,
                "subject": subject,
                "score": score,
                "matched_keywords": matched,
            }
        )
    llm_client = state.get("_llm_client")
    if mode == "llm" and llm_client is not None:
        candidates, llm_errors = _llm_filter_commits(commits, llm_client, batch_size)
        filter_mode = "llm"
    else:
        candidates = [item for item in commits if item["score"] > 0]
        llm_errors = []
        filter_mode = "keyword"

    candidates.sort(key=lambda item: (item.get("confidence", 0), item["score"], item["date"]), reverse=True)
    return {
        "bug_fix_commits": {
            "ok": True,
            "repo": str(repo_path),
            "count": len(candidates[:max_commits]),
            "items": candidates[:max_commits],
            "log_limit": log_limit,
            "filter_mode": filter_mode,
            "llm_errors": llm_errors,
        }
    }


def extract_bug_fix_snippets(state: dict[str, Any]) -> dict[str, Any]:
    """Extract native-code diff hunks from ranked bug-fix commits."""

    repo_result = state.get("repo_result", {})
    commits = state.get("bug_fix_commits", {})
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot extract bug-fix snippets", "bug_fix_snippets")
    if not commits.get("ok"):
        return _failure(state, "bug-fix commit search failed; cannot extract snippets", "bug_fix_snippets")

    request = dict(state.get("repo_request", {}))
    max_snippets = int(request.get("bug_fix_max_snippets", 100))
    output_dir = Path(request.get("bug_fix_output_dir", FALLBACK_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_repo_output_name(state)}.bugfix_snippets.jsonl"

    repo_path = Path(repo_result["path"])
    scoped_files = set(state.get("source_scope", {}).get("files", []))
    snippets = []
    for commit in commits.get("items", []):
        diff = _git_show(repo_path, commit["commit"])
        if not diff:
            continue
        snippets.extend(_parse_diff_hunks(diff, commit, scoped_files))
        if len(snippets) >= max_snippets:
            snippets = snippets[:max_snippets]
            break

    with output_path.open("w", encoding="utf-8") as handle:
        for item in snippets:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    return {
        "bug_fix_snippets": {
            "ok": True,
            "count": len(snippets),
            "output_path": str(output_path),
            "items": snippets,
        }
    }


def _score_subject(subject: str) -> tuple[int, list[str]]:
    lower = subject.lower()
    matched = [keyword for keyword in BUG_FIX_KEYWORDS if keyword in lower]
    score = sum(BUG_FIX_KEYWORDS[keyword] for keyword in matched)
    if any(noise in lower for noise in ("typo", "readme", "documentation", "comment")):
        score -= 5
    return max(score, 0), matched


def _llm_filter_commits(
    commits: list[dict[str, Any]],
    llm_client: Any,
    batch_size: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    by_hash = {item["commit"]: item for item in commits}
    selected: list[dict[str, Any]] = []
    errors: list[str] = []
    for start in range(0, len(commits), batch_size):
        batch = commits[start:start + batch_size]
        payload = [
            {
                "commit": item["commit"],
                "date": item["date"],
                "subject": item["subject"],
                "keyword_score": item["score"],
                "matched_keywords": item["matched_keywords"],
            }
            for item in batch
        ]
        try:
            response = llm_client.classify_bug_fix_commits(payload)
            parsed = json.loads(response.get("content", "{}"))
        except Exception as exc:
            errors.append(f"batch {start // batch_size}: {exc}")
            continue
        for item in parsed.get("items", []):
            commit_hash = str(item.get("commit", ""))
            if not item.get("is_bug_fix") or commit_hash not in by_hash:
                continue
            base = dict(by_hash[commit_hash])
            base.update(
                {
                    "confidence": float(item.get("confidence", 0.0)),
                    "llm_reason": item.get("reason", ""),
                    "llm_category": item.get("category", ""),
                }
            )
            selected.append(base)

    if not selected and errors:
        selected = [item for item in commits if item["score"] > 0]
    return selected, errors


def _git_show(repo_path: Path, commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", "--format=", "--unified=20", commit],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _parse_diff_hunks(
    diff_text: str,
    commit: dict[str, Any],
    scoped_files: set[str],
) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    current_file = ""
    current_header = ""
    current_lines: list[str] = []

    def flush() -> None:
        if not current_file or not current_lines:
            return
        if not _is_native_source(current_file):
            return
        if scoped_files and current_file not in scoped_files:
            return
        if not any(line.startswith(("+", "-")) and not line.startswith(("+++", "---")) for line in current_lines):
            return
        snippets.append(
            {
                "commit": commit["commit"],
                "date": commit["date"],
                "subject": commit["subject"],
                "score": commit["score"],
                "file": current_file,
                "hunk_header": current_header,
                "text": "\n".join(current_lines),
            }
        )

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            current_file = ""
            current_header = ""
            current_lines = []
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].removeprefix("b/")
            continue
        if line.startswith("@@ "):
            flush()
            current_header = line
            current_lines = [line]
            continue
        if current_header:
            current_lines.append(line)
    flush()
    return snippets


def _is_native_source(path: str) -> bool:
    return Path(path).suffix.lower() in NATIVE_SUFFIXES


def _failure(state: dict[str, Any], message: str, key: str) -> dict[str, Any]:
    return {
        key: {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
