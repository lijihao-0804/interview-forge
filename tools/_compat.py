"""Compatibility loader for the historical tools/*.py command paths."""
from __future__ import annotations

import importlib
import inspect
import runpy
import sys
from pathlib import Path
from types import ModuleType


def expose(public_name: str, target_name: str) -> ModuleType | None:
    """Expose a moved module at its old import path or run it as a script."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if public_name == "__main__":
        runpy.run_module(target_name, run_name="__main__")
        return None
    module = importlib.import_module(target_name)
    sys.modules[public_name] = module
    # Some existing tests load a tools entrypoint with
    # importlib.util.spec_from_file_location rather than as a package module.
    # Populate that executing module too, while preserving its loader
    # metadata, so both invocation styles expose the same public surface.
    caller_globals = inspect.currentframe().f_back.f_globals
    hidden = {"__name__", "__loader__", "__package__", "__spec__", "__file__", "__cached__"}
    caller_globals.update({
        key: value for key, value in module.__dict__.items() if key not in hidden
    })
    return module
