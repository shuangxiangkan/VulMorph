"""Shared LangGraph state types for the VulMorph MVP pipeline."""

from __future__ import annotations

from typing import Any, TypedDict


class VulMorphState(TypedDict, total=False):
    repo_request: dict[str, Any]
    repo_result: dict[str, Any]
    structure_analysis: dict[str, Any]
    source_scope: dict[str, Any]
    build_setup: dict[str, Any]
    function_extraction: dict[str, Any]
    embedding_result: dict[str, Any]
    errors: list[str]
