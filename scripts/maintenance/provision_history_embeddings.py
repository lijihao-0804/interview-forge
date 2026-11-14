"""Install or verify the pinned local history encoder. Run from the repo root with -m."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

from interview_forge.ai.embedding_spec import (
    DEFAULT_MODEL_DIR, MODEL_FILES, MODEL_ID, MODEL_REVISION, ONNX_REPOSITORY, ModelFile,
)


def _matches(path: Path, spec: ModelFile) -> bool:
    if not path.is_file() or path.stat().st_size != spec.size:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == spec.sha256


def _verify(directory: Path) -> None:
    for name, spec in MODEL_FILES.items():
        if not _matches(directory / name, spec):
            raise ValueError(f"Missing or incorrect pinned file: {directory / name}")


def provision(directory: Path, *, verify_only: bool) -> None:
    if verify_only or directory.exists():
        _verify(directory)
        return

    directory.parent.mkdir(parents=True, exist_ok=True)
    # A sibling directory keeps the final rename on one filesystem. Readers only
    # see the complete pair. A failing download does not affect an existing model.
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix=".e5-") as staging:
        candidate = Path(staging) / "model"
        candidate.mkdir()
        for name, spec in MODEL_FILES.items():
            path = candidate / name
            url = f"https://huggingface.co/{ONNX_REPOSITORY}/resolve/{MODEL_REVISION}/{spec.source_path}"
            with urllib.request.urlopen(url, timeout=60) as response, path.open("xb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
                    if target.tell() > spec.size:
                        raise ValueError(f"Unexpected download length for {name}")
        _verify(candidate)
        try:
            candidate.rename(directory)
        except OSError:
            if not directory.is_dir():
                raise
            _verify(directory)  # A concurrent provisioner may have published first.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=DEFAULT_MODEL_DIR, type=Path)
    parser.add_argument("--verify-only", action="store_true", help="Check local bytes without network access")
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        provision(directory, verify_only=args.verify_only)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Model provisioning failed: {exc}\n")
    print(json.dumps({
        "model": MODEL_ID, "revision": MODEL_REVISION, "directory": str(directory),
        "sha256": {name: spec.sha256 for name, spec in MODEL_FILES.items()},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
