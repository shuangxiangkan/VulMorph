"""Heuristics for ranking bug/security-fix commits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vulmorph.collectors.git_repo import commit_stats, empty_stats


DEFAULT_KEYWORDS: dict[str, int] = {
    "cve": 10,
    "security": 9,
    "vulnerab": 9,
    "overflow": 8,
    "underflow": 8,
    "out-of-bounds": 8,
    "oob": 8,
    "bounds": 6,
    "integer": 5,
    "truncate": 5,
    "asan": 5,
    "ubsan": 5,
    "fuzz": 5,
    "oss-fuzz": 6,
    "crash": 4,
    "invalid": 4,
    "corrupt": 4,
    "memory": 4,
    "leak": 3,
    "fix": 2,
    "bug": 2,
}

NOISE_PATTERNS = (
    "typo",
    "comment",
    "readme",
    "documentation",
    "formatting",
    "whitespace",
)


def score_commit(
    repo_path: Path,
    commit: dict[str, str],
    keywords: dict[str, int],
) -> dict[str, Any]:
    subject = commit["subject"]
    text = subject.lower()
    matched = [term for term in keywords if term.lower() in text]
    score = sum(keywords[term] for term in matched)

    if any(pattern in text for pattern in NOISE_PATTERNS):
        score -= 4

    stats = commit_stats(repo_path, commit["commit"]) if score > 0 else empty_stats()
    if 0 < stats["changed_file_count"] <= 3:
        score += 2
    if stats["changed_file_count"] > 12:
        score -= 3
    if any(looks_security_relevant_file(path) for path in stats["files"]):
        score += 1

    return {
        **commit,
        "score": max(score, 0),
        "matched_keywords": matched,
        "changed_file_count": stats["changed_file_count"],
        "additions": stats["additions"],
        "deletions": stats["deletions"],
        "files": stats["files"][:20],
        "inspect_command": f"git -C {repo_path} show {commit['commit']}",
    }


def load_keywords(value: Any) -> dict[str, int]:
    if value is None:
        return dict(DEFAULT_KEYWORDS)
    if isinstance(value, dict):
        return {str(term).lower(): int(weight) for term, weight in value.items()}
    if isinstance(value, list):
        return {str(term).lower(): 5 for term in value}
    raise TypeError("keywords must be a dict, a list, or omitted")


def looks_security_relevant_file(path: str) -> bool:
    lower = path.lower()
    return lower.endswith((".c", ".cc", ".cpp", ".h", ".hpp")) and not any(
        token in lower for token in ("test", "doc", "example")
    )
