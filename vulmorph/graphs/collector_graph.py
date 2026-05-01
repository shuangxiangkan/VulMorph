"""LangGraph builders for collector workflows."""

from __future__ import annotations

from typing import Any, Iterable, TypedDict

from vulmorph.collectors.registry import COLLECTOR_NODES


class CollectorState(TypedDict, total=False):
    git_log_bug_search: dict[str, Any]
    git_log_bug_search_result: dict[str, Any]
    patch_similarity_search: dict[str, Any]
    patch_similarity_search_result: dict[str, Any]


def build_collector_graph(node_names: Iterable[str] = ("git_log_bug_search",)):
    """Build a sequential LangGraph collector graph.

    LangGraph is imported lazily so collectors remain usable without it.
    """

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - depends on local env.
        raise RuntimeError(
            "langgraph is required to build graphs. Install it before calling "
            "build_collector_graph()."
        ) from exc

    names = list(node_names)
    graph = StateGraph(CollectorState)

    for name in names:
        graph.add_node(name, COLLECTOR_NODES[name])

    if not names:
        graph.add_edge(START, END)
    else:
        graph.add_edge(START, names[0])
        for prev, current in zip(names, names[1:]):
            graph.add_edge(prev, current)
        graph.add_edge(names[-1], END)

    return graph.compile()
