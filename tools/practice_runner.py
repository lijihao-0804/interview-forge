"""Isolated practice-code runner.

This process is deliberately separate from the FastAPI web process.  It accepts
only a fixed JSON protocol on loopback, then runs user code inside a
bubblewrap sandbox with a private mount namespace, no network, no host
project directories, a non-root uid, bounded output, and CPU/wall time limits.

It never accepts an image name, shell command, mount, or network option from
the request.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_CODE_BYTES = 64 * 1024
MAX_STDIN_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
PYTHON_TIMEOUT_MS = 3000
JAVA_COMPILE_TIMEOUT_MS = 8000
JAVA_RUN_TIMEOUT_MS = 3000
MAX_MEMORY_BYTES = 512 * 1024 * 1024
JAVA_VIRTUAL_MEMORY_BYTES = 1536 * 1024 * 1024
MAX_PROCS = 64
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_BODY_BYTES = 120 * 1024

_RUN_LOCK = threading.Lock()
_JAVA_CLASS_RE = re.compile(r"\bpublic\s+(?:final\s+|abstract\s+|sealed\s+)?class\s+([A-Za-z_$][\w$]*)")
_JAVA_ANY_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")
_BWRAP = os.environ.get("PRACTICE_BWRAP", "/usr/bin/bwrap")
_VENV_PATH = Path("/opt/interview-forge/.venv")
_VENV_MOUNT = "/opt/venv"
_PYTHON = os.environ.get(
    "PRACTICE_PYTHON",
    f"{_VENV_MOUNT}/bin/python" if _VENV_PATH.exists() else "/usr/bin/python3",
)
_JAVA = os.environ.get("PRACTICE_JAVA", "/usr/bin/java")
_JAVAC = os.environ.get("PRACTICE_JAVAC", "/usr/bin/javac")


class RunnerError(Exception):
    def __init__(self, status: str, message: str = "") -> None:
        super().__init__(message or status)
        self.status = status
        self.message = message


def _set_limits(cpu_seconds: int, memory_bytes: int) -> None:
    """Set hard limits in the forked child before exec."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCS, MAX_PROCS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _bwrap_command(workdir: Path, inner: list[str], cpu_seconds: int) -> list[str]:
    """Build a fixed bubblewrap command; no request-controlled mount/network knobs."""
    optional_binds: list[str] = []
    for path in ("/etc/java-17-openjdk", "/etc/localtime"):
        if Path(path).exists():
            optional_binds += ["--ro-bind", path, path]
    if _VENV_PATH.exists():
        optional_binds += ["--ro-bind", str(_VENV_PATH), _VENV_MOUNT]
    return [
        _BWRAP,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/etc/alternatives", "/etc/alternatives",
        *optional_binds,
        "--bind", str(workdir), "/work",
        "--chdir", "/work",
        "--uid", "65534",
        "--gid", "65534",
        *inner,
    ]


def _bounded_run(
    command: list[str],
    *,
    stdin_text: str,
    timeout_seconds: float,
    cpu_seconds: int,
    workdir: Path,
    memory_bytes: int = MAX_MEMORY_BYTES,
) -> dict:
    """Run a command, bounding both wall time and output while it is captured."""
    started = time.perf_counter()
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(workdir),
        start_new_session=True,
        preexec_fn=lambda: _set_limits(cpu_seconds, memory_bytes),
    )
    result = {
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "timed_out": False,
        "output_truncated": False,
        "wall_time_ms": 0,
    }
    output_lock = threading.Lock()
    output_bytes = 0
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    stop = threading.Event()

    def kill_group() -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    timer = threading.Timer(timeout_seconds, lambda: (result.__setitem__("timed_out", True), kill_group()))
    timer.daemon = True
    timer.start()

    def read_stream(name: str, stream) -> None:
        nonlocal output_bytes
        try:
            while not stop.is_set():
                chunk = stream.read(4096)
                if not chunk:
                    break
                with output_lock:
                    remaining = MAX_OUTPUT_BYTES - output_bytes
                    if remaining <= 0:
                        result["output_truncated"] = True
                        stop.set()
                        kill_group()
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                        result["output_truncated"] = True
                        stop.set()
                        kill_group()
                    chunks[name].extend(chunk)
                    output_bytes += len(chunk)
        except (OSError, ValueError):
            pass

    threads = [
        threading.Thread(target=read_stream, args=("stdout", proc.stdout), daemon=True),
        threading.Thread(target=read_stream, args=("stderr", proc.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        if stdin_text:
            proc.stdin.write(stdin_text.encode("utf-8", "replace"))
        proc.stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        pass

    try:
        proc.wait(timeout=max(0.1, timeout_seconds + 1.0))
    except subprocess.TimeoutExpired:
        result["timed_out"] = True
        kill_group()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    timer.cancel()
    stop.set()
    for thread in threads:
        thread.join(timeout=2)

    result["stdout"] = bytes(chunks["stdout"]).decode("utf-8", "replace")
    result["stderr"] = bytes(chunks["stderr"]).decode("utf-8", "replace")
    result["exit_code"] = proc.returncode
    result["wall_time_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def _java_class_name(code: str) -> tuple[str, str]:
    match = _JAVA_CLASS_RE.search(code) or _JAVA_ANY_CLASS_RE.search(code)
    if not match:
        raise RunnerError("unsupported_java", "Java 代码需要包含可识别的 class（如 public class Main）")
    return match.group(1), f"{match.group(1)}.java"


def _python_run(workdir: Path) -> dict:
    return _bounded_run(
        _bwrap_command(workdir, [_PYTHON, "/work/main.py"], 3),
        stdin_text="",
        timeout_seconds=3,
        cpu_seconds=3,
        workdir=workdir,
    )


def run_code(language: str, code: str, stdin_text: str) -> dict:
    if not _RUN_LOCK.acquire(blocking=False):
        raise RunnerError("busy", "当前已有一次执行，请稍后再试")
    workdir = Path(tempfile.mkdtemp(prefix="if-practice-"))
    try:
        os.chmod(workdir, 0o777)
        if language == "python":
            (workdir / "main.py").write_text(code, encoding="utf-8")
            os.chmod(workdir / "main.py", 0o644)
            result = _bounded_run(
                _bwrap_command(workdir, [_PYTHON, "/work/main.py"], 3),
                stdin_text=stdin_text,
                timeout_seconds=3,
                cpu_seconds=3,
                workdir=workdir,
            )
            if result["timed_out"]:
                status = "timeout"
            elif result["output_truncated"]:
                status = "output_limit"
            elif result["exit_code"] != 0:
                status = "runtime_error"
            else:
                status = "ok"
            return {
                "status": status,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"],
                "compile_time_ms": 0,
                "run_time_ms": result["wall_time_ms"],
                "timed_out": result["timed_out"],
                "output_truncated": result["output_truncated"],
            }

        if language == "java":
            class_name, filename = _java_class_name(code)
            source = workdir / filename
            source.write_text(code, encoding="utf-8")
            os.chmod(source, 0o644)
            compile_result = _bounded_run(
                _bwrap_command(
                    workdir,
                    [_JAVAC, "-J-Xmx256m", "-J-XX:CompressedClassSpaceSize=128m", "-encoding", "UTF-8", "-d", "/work/classes", f"/work/{filename}"],
                    8,
                ),
                stdin_text="",
                timeout_seconds=8,
                cpu_seconds=8,
                workdir=workdir,
                memory_bytes=JAVA_VIRTUAL_MEMORY_BYTES,
            )
            if compile_result["timed_out"]:
                return {
                    "status": "compile_error",
                    "stdout": compile_result["stdout"],
                    "stderr": "编译超时\n" + compile_result["stderr"],
                    "exit_code": compile_result["exit_code"],
                    "compile_time_ms": compile_result["wall_time_ms"],
                    "run_time_ms": 0,
                    "timed_out": True,
                    "output_truncated": compile_result["output_truncated"],
                }
            if compile_result["output_truncated"]:
                return {
                    "status": "compile_error",
                    "stdout": compile_result["stdout"],
                    "stderr": "编译输出过大\n" + compile_result["stderr"],
                    "exit_code": compile_result["exit_code"],
                    "compile_time_ms": compile_result["wall_time_ms"],
                    "run_time_ms": 0,
                    "timed_out": False,
                    "output_truncated": True,
                }
            if compile_result["exit_code"] != 0:
                return {
                    "status": "compile_error",
                    "stdout": compile_result["stdout"],
                    "stderr": compile_result["stderr"],
                    "exit_code": compile_result["exit_code"],
                    "compile_time_ms": compile_result["wall_time_ms"],
                    "run_time_ms": 0,
                    "timed_out": False,
                    "output_truncated": False,
                }

            run_result = _bounded_run(
                _bwrap_command(
                    workdir,
                    [_JAVA, "-Xmx256m", "-XX:CompressedClassSpaceSize=128m", "-XX:MaxMetaspaceSize=128m", "-cp", "/work/classes", class_name],
                    3,
                ),
                stdin_text=stdin_text,
                timeout_seconds=3,
                cpu_seconds=3,
                workdir=workdir,
                memory_bytes=JAVA_VIRTUAL_MEMORY_BYTES,
            )
            if run_result["timed_out"]:
                status = "timeout"
            elif run_result["output_truncated"]:
                status = "output_limit"
            elif run_result["exit_code"] != 0:
                status = "runtime_error"
            else:
                status = "ok"
            return {
                "status": status,
                "stdout": run_result["stdout"],
                "stderr": run_result["stderr"],
                "exit_code": run_result["exit_code"],
                "compile_time_ms": compile_result["wall_time_ms"],
                "run_time_ms": run_result["wall_time_ms"],
                "timed_out": run_result["timed_out"],
                "output_truncated": run_result["output_truncated"],
            }

        raise RunnerError("invalid_language", "只支持 python 和 java")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        _RUN_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "InterviewForgePracticeRunner/1"
    token = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            self._json(404, {"error": "not found"})
            return
        if not self.token or self.headers.get("X-Practice-Token", "") != self.token:
            self._json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY_BYTES:
                raise RunnerError("invalid_request", "request too large")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise RunnerError("invalid_request", "body must be an object")
            language = str(payload.get("language", ""))
            code = payload.get("code")
            stdin_text = payload.get("stdin", "")
            if not isinstance(code, str) or not isinstance(stdin_text, str):
                raise RunnerError("invalid_request", "code/stdin must be strings")
            code_bytes = len(code.encode("utf-8"))
            stdin_bytes = len(stdin_text.encode("utf-8"))
            if code_bytes > MAX_CODE_BYTES:
                raise RunnerError("invalid_request", "code too large")
            if stdin_bytes > MAX_STDIN_BYTES:
                raise RunnerError("invalid_request", "stdin too large")
            if language not in {"python", "java"}:
                raise RunnerError("invalid_language", "only python and java are supported")
            result = run_code(language, code, stdin_text)
            self._json(200, result)
        except RunnerError as exc:
            self._json(429 if exc.status == "busy" else 400, {"status": exc.status, "error": exc.message})
        except Exception:  # never leak sandbox/system details
            self._json(500, {"status": "internal_error", "error": "执行服务暂时不可用"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--token-file", default="/etc/interview-forge/practice-runner.token")
    args = parser.parse_args()
    token_file = Path(args.token_file)
    Handler.token = token_file.read_text(encoding="utf-8").strip() if token_file.exists() else ""
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
