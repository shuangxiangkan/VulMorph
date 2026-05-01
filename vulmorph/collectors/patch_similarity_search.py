"""Interface sketch for recurring-vulnerability and incomplete-fix search.

This module intentionally keeps the first implementation small. The real
algorithm can later reuse git_repo.py for diffs and add AST/CPG/LLM evidence.
"""

from __future__ import annotations

from typing import Any

from vulmorph.collectors.nodes import CollectorNode


def search_patch_similarities(request: dict[str, Any]) -> dict[str, Any]:
    """Return the stable output shape for future patch-similarity collectors.

    Intended request keys:
      - repo_url or repo_path
      - fix_commit
      - target_ref, optional
      - search_scope, optional list of paths
    """

    return {
        "ok": False,
        "mode": "interface_only",
        "repo": {
            "url": request.get("repo_url", ""),
            "path": request.get("repo_path", ""),
        },
        "query": {
            "fix_commit": request.get("fix_commit", ""),
            "target_ref": request.get("target_ref", "HEAD"),
            "search_scope": request.get("search_scope", []),
        },
        "candidates": [],
        "errors": ["patch similarity search is not implemented yet"],
    }


PATCH_SIMILARITY_SEARCH_NODE = CollectorNode(
    name="patch_similarity_search",
    input_key="patch_similarity_search",
    output_key="patch_similarity_search_result",
    collect=search_patch_similarities,
)


def search_patch_similarities_node(state: dict[str, Any]) -> dict[str, Any]:
    return PATCH_SIMILARITY_SEARCH_NODE.run(state)
