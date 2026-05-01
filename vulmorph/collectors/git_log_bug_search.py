"""Search git history for bug/security-fix candidates.

Public functions accept and return plain dictionaries so they can be used as
LangGraph nodes without adapters.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from vulmorph.collectors.commit_scoring import load_keywords, score_commit
from vulmorph.collectors.git_repo import ensure_repo, read_log, repo_head
from vulmorph.collectors.nodes import CollectorNode


def search_git_log_bugs(request: dict[str, Any]) -> dict[str, Any]:
    """Find likely bug/security-fix commits in a GitHub or local git repo.

    Request keys:
      - repo_url: GitHub URL to clone if repo_path is absent.
      - repo_path: existing local git repository path.
      - cache_dir: clone destination parent, default data/targets.
      - max_results: default 30.
      - keywords: optional {term: weight} or [term].
      - since / until: optional git date filters.
    """

    max_results = int(request.get("max_results", 30))
    keywords = load_keywords(request.get("keywords"))

    try:
        repo_path = ensure_repo(request)
        commits = read_log(repo_path, request)
        candidates = [score_commit(repo_path, commit, keywords) for commit in commits]
        candidates = [item for item in candidates if item["score"] > 0]
        candidates.sort(key=lambda item: (item["score"], item["date"]), reverse=True)

        return {
            "ok": True,
            "repo": {
                "url": request.get("repo_url", ""),
                "path": str(repo_path),
                "head": repo_head(repo_path),
            },
            "query": {
                "max_results": max_results,
                "since": request.get("since", ""),
                "until": request.get("until", ""),
                "keyword_count": len(keywords),
            },
            "candidates": candidates[:max_results],
            "errors": [],
        }
    except Exception as exc:  # pragma: no cover - keeps LangGraph state robust.
        return {
            "ok": False,
            "repo": {
                "url": request.get("repo_url", ""),
                "path": request.get("repo_path", ""),
            },
            "query": {
                "max_results": max_results,
                "since": request.get("since", ""),
                "until": request.get("until", ""),
                "keyword_count": len(keywords),
            },
            "candidates": [],
            "errors": [str(exc)],
        }


GIT_LOG_BUG_SEARCH_NODE = CollectorNode(
    name="git_log_bug_search",
    input_key="git_log_bug_search",
    output_key="git_log_bug_search_result",
    collect=search_git_log_bugs,
)


def search_git_log_bugs_node(state: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible LangGraph-style node."""

    return GIT_LOG_BUG_SEARCH_NODE.run(state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search git log bug/security candidates.")
    parser.add_argument("repo", help="GitHub URL or local repository path")
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--cache-dir", default="data/targets")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    args = parser.parse_args()

    repo_is_url = "://" in args.repo or args.repo.startswith("git@")
    request = {
        "repo_url" if repo_is_url else "repo_path": args.repo,
        "cache_dir": args.cache_dir,
        "max_results": args.max_results,
        "since": args.since,
        "until": args.until,
    }
    print(json.dumps(search_git_log_bugs(request), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
