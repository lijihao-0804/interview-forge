"""Per-application ToolSpec registry with no mutable global tool catalog."""
from __future__ import annotations

from collections.abc import Iterable

from interview_forge.ai.tools.contracts import ToolSpec


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(str(name))

    def list_specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    def model_schemas(self) -> list[dict[str, object]]:
        from interview_forge.ai.tools.langchain_adapter import tool_spec_schema

        return [tool_spec_schema(spec) for spec in self._specs.values()]

    def __len__(self) -> int:
        return len(self._specs)


def build_default_tool_registry() -> ToolRegistry:
    """Build a fresh registry; builtins are imported only when requested."""
    registry = ToolRegistry()
    from interview_forge.ai.tools.builtins import register_builtin_tools

    register_builtin_tools(registry)
    return registry


__all__ = ["ToolRegistry", "build_default_tool_registry"]
