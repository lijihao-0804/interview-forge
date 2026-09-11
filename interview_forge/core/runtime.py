"""Small composition-root runtime registry.

The application is intentionally not coupled to a dependency-injection
framework.  The server assembly binds its process-local dependencies once at
startup; domain modules consume this registry without importing the HTTP
server.  A provider is retained only for compatibility with the existing
test-facing server symbols, so changing a symbol on the composition root is
observed by the next call without creating a second singleton.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class RuntimeBindings:
    """Late-bound application dependencies owned by the composition root."""

    def __init__(self) -> None:
        self._provider: Callable[[], Any] | None = None
        self._values: dict[str, Any] = {}

    def bind_provider(self, provider: Callable[[], Any]) -> None:
        self._provider = provider

    def bind(self, **values: Any) -> None:
        self._values.update(values)

    def clear(self) -> None:
        self._provider = None
        self._values.clear()

    def get(self, name: str, default: Any = None) -> Any:
        if name in self._values:
            return self._values[name]
        if self._provider is not None:
            owner = self._provider()
            if owner is not None and hasattr(owner, name):
                return getattr(owner, name)
        else:
            # FastAPI can be imported directly by Uvicorn/TestClient without
            # first importing the legacy command module.  Use the small core
            # defaults composition root in that case; the legacy server still
            # binds itself explicitly and therefore keeps all test patch
            # points unchanged.
            from interview_forge.core import default_runtime
            if hasattr(default_runtime, name):
                return getattr(default_runtime, name)
        if default is not None:
            return default
        raise AttributeError(name)

    def __getattr__(self, name: str) -> Any:
        return self.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Keep assignments to legacy patch points (for example _AUTH_READY)
        # on the composition-root owner rather than shadowing them on this
        # registry object.  Internal registry fields remain local.
        if name in {"_provider", "_values"} or name in type(self).__dict__:
            object.__setattr__(self, name, value)
            return
        if self._provider is not None:
            owner = self._provider()
            if owner is not None:
                setattr(owner, name, value)
                return
        self._values[name] = value


# One process-local binding set.  The server is the composition root and binds
# this object before any request can call a service.
server_runtime = RuntimeBindings()
