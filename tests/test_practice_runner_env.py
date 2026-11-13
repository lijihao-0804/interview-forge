import os
from unittest.mock import patch

import pytest

from tools import practice_runner


def test_numeric_threads_are_bounded_without_mutating_parent_environment():
    with patch.dict(os.environ, {"OPENBLAS_NUM_THREADS": "128", "OMP_NUM_THREADS": "32", "FORGE_QA_SENTINEL": "preserved"}):
        environment = practice_runner._sandbox_environment()
        for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
            assert environment[name] == "1"
        assert environment["FORGE_QA_SENTINEL"] == "preserved"
        assert os.environ["OPENBLAS_NUM_THREADS"] == "128"
        assert os.environ["OMP_NUM_THREADS"] == "32"


def test_bounded_process_receives_fixed_thread_environment(tmp_path):
    class CaptureOnly(Exception):
        pass

    with patch.object(practice_runner.subprocess, "Popen", side_effect=CaptureOnly) as process:
        with pytest.raises(CaptureOnly):
            practice_runner._bounded_run(["not-executed"], stdin_text="", timeout_seconds=3, cpu_seconds=3, workdir=tmp_path)
        assert process.call_args.kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
        assert process.call_args.kwargs["start_new_session"] is True
        assert callable(process.call_args.kwargs["preexec_fn"])
    assert practice_runner.PYTHON_TIMEOUT_MS == 3000
    assert practice_runner.JAVA_RUN_TIMEOUT_MS == 3000
