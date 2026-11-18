"""Exercise stdin/stdout on unseen inputs and check the published Java tie rule."""
import json
import shutil

import pytest

from interview_forge.services.native_acm import problem
from scripts.check.check_native_acm_references import published_sources, verify


@pytest.mark.parametrize("language", ["python", "java"])
@pytest.mark.parametrize(("key", "argument", "expected"), [
    ("hot100-5", "civicXradar", "civic"),
    ("hot200-271", ["a\tb", '"\\', "\b\f"], '3/a\tb2/"\\2/\b\f'),
])
def test_published_program_reads_fresh_input(key, argument, expected, language):
    if language == "java" and not (shutil.which("java") and shutil.which("javac")):
        pytest.skip("JDK 17+ required")
    row = dict(problem(key))
    row["samples"] = [{"name": "unseen stdin", "input": json.dumps(argument) + "\n",
                       "expected": json.dumps(expected)}]
    result, = verify((row, language, published_sources(row)[language], "local"))
    assert result["verdict"] == "pass", result
