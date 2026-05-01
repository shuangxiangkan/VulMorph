"""LangGraph-friendly collector node primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


CollectorFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class CollectorNode:
    """A small adapter from a collector function to a LangGraph node."""

    name: str
    input_key: str
    output_key: str
    collect: CollectorFn

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state.get(self.input_key, state)
        return {self.output_key: self.collect(request)}

    __call__ = run
