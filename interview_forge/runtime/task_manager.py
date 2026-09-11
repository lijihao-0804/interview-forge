"""Small backend-neutral task facade.

Product services keep ownership of their existing persistent/in-process state;
this registry only gives API callers one submit/query/cancel vocabulary.  It
therefore cannot create a second source of truth or alter task lifecycle rules.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskBackend:
    submit: Callable[..., Any]
    query: Callable[..., Any] | None = None
    cancel: Callable[..., Any] | None = None


class TaskManager:
    def __init__(self) -> None:
        self._backends: dict[str, TaskBackend] = {}

    def register(self, kind: str, backend: TaskBackend) -> None:
        key = str(kind).strip()
        if not key:
            raise ValueError("task backend already registered")
        if key in self._backends:
            return
        self._backends[key] = backend

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))

    def submit(self, kind: str, *args: Any, **kwargs: Any) -> Any:
        return self._backend(kind).submit(*args, **kwargs)

    def query(self, kind: str, *args: Any, **kwargs: Any) -> Any:
        backend = self._backend(kind)
        if backend.query is None:
            raise NotImplementedError("task backend does not support query")
        return backend.query(*args, **kwargs)

    def cancel(self, kind: str, *args: Any, **kwargs: Any) -> Any:
        backend = self._backend(kind)
        if backend.cancel is None:
            raise NotImplementedError("task backend does not support cancel")
        return backend.cancel(*args, **kwargs)

    def _backend(self, kind: str) -> TaskBackend:
        try:
            return self._backends[str(kind)]
        except KeyError as exc:
            raise ValueError("unknown task backend") from exc


# One registry, no task rows or worker state are stored here.
task_manager = TaskManager()
