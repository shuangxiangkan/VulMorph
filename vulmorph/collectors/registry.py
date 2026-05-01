"""Collector node registry."""

from __future__ import annotations

from vulmorph.collectors.git_log_bug_search import GIT_LOG_BUG_SEARCH_NODE
from vulmorph.collectors.patch_similarity_search import PATCH_SIMILARITY_SEARCH_NODE


COLLECTOR_NODES = {
    GIT_LOG_BUG_SEARCH_NODE.name: GIT_LOG_BUG_SEARCH_NODE,
    PATCH_SIMILARITY_SEARCH_NODE.name: PATCH_SIMILARITY_SEARCH_NODE,
}

__all__ = [
    "COLLECTOR_NODES",
    "GIT_LOG_BUG_SEARCH_NODE",
    "PATCH_SIMILARITY_SEARCH_NODE",
]
