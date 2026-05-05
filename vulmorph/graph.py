"""LangGraph assembly for the initial VulMorph pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from .build_setup import prepare_compile_commands
from .bug_history_mine import extract_bug_fix_snippets, find_bug_fix_commits
from .embeddings import embed_functions
from .function_extraction import extract_functions_with_ccscope
from .repo_analysis import LLMClient, analyze_repo_structure
from .repos import acquire_repo
from .source_scope import select_source_scope
from .state import VulMorphState
from .similarity import search_similar_bug_fix_code

ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


def build_vulmorph_graph(
    llm_client: LLMClient | None = None,
    progress_callback: ProgressCallback | None = None,
):
    """Build the repo -> structure -> functions -> embeddings graph."""

    graph = StateGraph(VulMorphState)
    graph.add_node(
        "acquire_repo", 
        _with_progress("acquire_repo", acquire_repo, progress_callback))
    graph.add_node(
        "analyze_repo_structure",
        _with_progress(
            "analyze_repo_structure",
            lambda state: analyze_repo_structure(state, llm_client=llm_client),
            progress_callback,
        ),
    )
    graph.add_node(
        "select_source_scope", 
        _with_progress("select_source_scope", select_source_scope, progress_callback))
    graph.add_node(
        "prepare_compile_commands",
        _with_progress("prepare_compile_commands", prepare_compile_commands, progress_callback),
    )
    graph.add_node(
        "extract_functions_with_ccscope",
        _with_progress("extract_functions_with_ccscope", extract_functions_with_ccscope, progress_callback),
    )
    graph.add_node(
        "embed_functions", 
        _with_progress("embed_functions", embed_functions, progress_callback))
    graph.add_node(
        "find_bug_fix_commits",
        _with_progress("find_bug_fix_commits", find_bug_fix_commits, progress_callback),
    )
    graph.add_node(
        "extract_bug_fix_snippets",
        _with_progress("extract_bug_fix_snippets", extract_bug_fix_snippets, progress_callback),
    )
    graph.add_node(
        "search_similar_bug_fix_code",
        _with_progress("search_similar_bug_fix_code", search_similar_bug_fix_code, progress_callback),
    )

    graph.add_edge(START, "acquire_repo")
    graph.add_edge("acquire_repo", "analyze_repo_structure")
    graph.add_edge("analyze_repo_structure", "select_source_scope")
    graph.add_edge("select_source_scope", "prepare_compile_commands")
    graph.add_edge("prepare_compile_commands", "extract_functions_with_ccscope")
    graph.add_edge("extract_functions_with_ccscope", "embed_functions")
    graph.add_edge("embed_functions", "find_bug_fix_commits")
    graph.add_edge("find_bug_fix_commits", "extract_bug_fix_snippets")
    graph.add_edge("extract_bug_fix_snippets", "search_similar_bug_fix_code")
    graph.add_edge("search_similar_bug_fix_code", END)
    return graph.compile()


def run_vulmorph_pipeline(repo_url: str, **kwargs: Any) -> VulMorphState:
    """Convenience runner for scripts and notebooks."""

    llm_client = kwargs.pop("llm_client", None)
    app = build_vulmorph_graph(
        llm_client=llm_client,
        progress_callback=kwargs.pop("progress_callback", None),
    )
    initial_state: VulMorphState = {
        "repo_request": {
            "repo_url": repo_url,
            **kwargs,
        }
    }
    progress_callback = kwargs.get("progress_callback")
    if progress_callback is not None:
        initial_state["_progress_callback"] = progress_callback
    if llm_client is not None:
        initial_state["_llm_client"] = llm_client
    return app.invoke(initial_state)


def _with_progress(
    name: str,
    fn: Callable[[dict[str, Any]], dict[str, Any]],
    progress_callback: ProgressCallback | None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if progress_callback is None:
        return fn

    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        progress_callback(name, "start", None)
        state["_progress_callback"] = progress_callback
        result = fn(state)
        progress_callback(name, "end", result)
        return result

    return wrapped
