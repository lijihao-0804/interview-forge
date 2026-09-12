"""Built-in assistant tools are registered here as the catalog grows."""
from __future__ import annotations

from interview_forge.ai.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    return registry


__all__ = ["register_builtin_tools"]
