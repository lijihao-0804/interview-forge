"""Portable, best-effort process and host measurements for Admin System."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from interview_forge.core.paths import DATA_DIR
from interview_forge.observability.logging import log_paths
from interview_forge.observability.store import observability_db_path


def _size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _directory_size(root: Path) -> int:
    total = 0
    try:
        for path in root.rglob("*"):
            if path.is_file():
                total += _size(path)
    except OSError:
        pass
    return total


def runtime_metrics() -> dict[str, Any]:
    payload: dict[str, Any] = {"cpu": {"available": False}, "memory": {"available": False}, "process": {"rss_bytes": None}}
    try:
        import psutil  # type: ignore
        payload["cpu"] = {"available": True, "percent": psutil.cpu_percent(interval=None), "logical_cpus": psutil.cpu_count()}
        memory = psutil.virtual_memory()
        payload["memory"] = {"available": True, "total_bytes": memory.total, "used_bytes": memory.used, "free_bytes": memory.available, "percent": memory.percent}
        payload["process"] = {"rss_bytes": psutil.Process(os.getpid()).memory_info().rss}
    except Exception:
        # ``/proc`` keeps Linux/VPS useful without making psutil mandatory.
        try:
            if sys.platform.startswith("linux"):
                values = {}
                for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                    name, raw = line.split(":", 1)
                    values[name] = int(raw.strip().split()[0]) * 1024
                total = values.get("MemTotal")
                available = values.get("MemAvailable")
                if total is not None and available is not None:
                    payload["memory"] = {"available": True, "total_bytes": total, "free_bytes": available, "used_bytes": total - available, "percent": round((total - available) / total * 100, 2)}
                statm = Path(f"/proc/{os.getpid()}/statm").read_text(encoding="utf-8").split()
                if statm:
                    payload["process"] = {"rss_bytes": int(statm[1]) * os.sysconf("SC_PAGE_SIZE")}
            if hasattr(os, "getloadavg"):
                payload["cpu"] = {"available": True, "load_1m": round(os.getloadavg()[0], 2), "logical_cpus": os.cpu_count()}
        except Exception:
            pass
    payload["storage"] = {
        "user_db_bytes": _directory_size(DATA_DIR / "users"),
        "observability_db_bytes": _size(observability_db_path()),
        "log_bytes": sum(_size(path) for path in log_paths()),
    }
    return payload


__all__ = ["runtime_metrics"]
