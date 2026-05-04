"""VulMorph pipeline package."""

from typing import Any

__all__ = ["build_vulmorph_graph"]


def __getattr__(name: str) -> Any:
    if name == "build_vulmorph_graph":
        from .graph import build_vulmorph_graph

        return build_vulmorph_graph
    raise AttributeError(name)
