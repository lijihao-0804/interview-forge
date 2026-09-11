"""Compatibility discovery adapter for the historical ``tools/tests`` path.

The maintained test files live in the project-level ``tests/`` directory;
this adapter keeps the old unittest discovery command working without a
second copy of the suite.
"""
from __future__ import annotations

from pathlib import Path
import unittest


def load_tests(loader: unittest.TestLoader, _tests: unittest.TestSuite, pattern: str | None):
    project_tests = Path(__file__).resolve().parents[2] / "tests"
    return loader.discover(
        str(project_tests),
        pattern=pattern or "test*.py",
        top_level_dir=str(project_tests.parent),
    )
