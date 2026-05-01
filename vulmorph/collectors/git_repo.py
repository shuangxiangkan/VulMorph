"""Small git helpers shared by collectors."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"


def ensure_repo(request: dict) -> Path:
    """Return a local git repo path, cloning repo_url when needed."""

    repo_path_value = request.get("repo_path")
    if repo_path_value:
        repo_path = Path(repo_path_value).expanduser().resolve()
        if not (repo_path / ".git").exists():
            raise ValueError(f"not a git repository: {repo_path}")
        return repo_path

    repo_url = request.get("repo_url")
    if not repo_url:
        raise ValueError("repo_path or repo_url is required")

    cache_dir = Path(request.get("cache_dir", "data/targets")).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_path = cache_dir / repo_dir_name(repo_url)

    if (repo_path / ".git").exists():
        git(repo_path, ["fetch", "--all", "--tags", "--prune"])
        return repo_path

    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, str(repo_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return repo_path


def repo_dir_name(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else repo_url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.git$", "", name)


def repo_head(repo_path: Path) -> str:
    return git(repo_path, ["rev-parse", "--short", "HEAD"]).strip()


def read_log(repo_path: Path, request: dict) -> list[dict[str, str]]:
    pretty = f"%H{FIELD_SEP}%h{FIELD_SEP}%ad{FIELD_SEP}%an{FIELD_SEP}%s{RECORD_SEP}"
    args = ["log", "--all", "--date=iso-strict", f"--pretty=format:{pretty}"]
    if request.get("since"):
        args.append(f"--since={request['since']}")
    if request.get("until"):
        args.append(f"--until={request['until']}")

    raw = git(repo_path, args)
    commits: list[dict[str, str]] = []
    for record in raw.split(RECORD_SEP):
        record = record.strip()
        if not record:
            continue
        parts = record.split(FIELD_SEP)
        if len(parts) != 5:
            continue
        commit, short, date, author, subject = parts
        commits.append(
            {
                "commit": commit,
                "short": short,
                "date": date,
                "author": author,
                "subject": subject,
            }
        )
    return commits


def commit_stats(repo_path: Path, commit: str) -> dict:
    try:
        raw = git(repo_path, ["show", "--format=", "--numstat", commit])
    except subprocess.CalledProcessError:
        return empty_stats()

    additions = 0
    deletions = 0
    files: list[str] = []

    for line in raw.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 3:
            continue
        add, delete, path = parts
        additions += int(add) if add.isdigit() else 0
        deletions += int(delete) if delete.isdigit() else 0
        files.append(path)

    unique_files = list(dict.fromkeys(files))
    return {
        "changed_file_count": len(unique_files),
        "additions": additions,
        "deletions": deletions,
        "files": unique_files,
    }


def empty_stats() -> dict:
    return {
        "changed_file_count": 0,
        "additions": 0,
        "deletions": 0,
        "files": [],
    }


def git(repo_path: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout
