"""Shared file-discovery scope for published site content checks.

The release checks inspect generated pages, public assets, and maintenance
documents. Development environments and acceptance artifacts can contain their
own HTML/Markdown with links that intentionally have no relation to this site;
those files must never enter the release corpus.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


# Directories whose files are shipped or intentionally maintained as release
# documentation. Root-level HTML/Markdown is handled separately below.
RELEASE_CONTENT_ROOTS = frozenset({
    "assets",
    "books",
    "docs",
    "library",
    "pages",
})

ROOT_RELEASE_DOCUMENT_SUFFIXES = frozenset({".html", ".md"})

_ARTIFACT_DIRECTORY_NAMES = frozenset({
    "__fixtures__",
    "__pycache__",
    "__tests__",
    "artifacts",
    "coverage",
    "fixtures",
    "htmlcov",
    "logs",
    "node_modules",
    "output",
    "site-packages",
    "temp",
    "test-data",
    "test_data",
    "test-fixtures",
    "test_fixtures",
    "testdata",
    "tests",
    "tmp",
})


def _is_development_artifact_directory(part: str) -> bool:
    """Return whether one path component is a known non-release directory."""

    name = part.casefold()
    if name.startswith("."):
        # Covers .git, .venv*, .cache, .pytest_cache, .ruff_cache, etc.
        return True
    if name in _ARTIFACT_DIRECTORY_NAMES:
        return True
    return name in {"cache", "caches"} or name.endswith((".cache", "-cache", "_cache"))


def is_release_content_path(path: Path, root: Path) -> bool:
    """Return whether ``path`` belongs to the site's release-check corpus.

    Paths outside ``root`` are not release files. Hidden directories, local
    environments, dependency installations, logs, browser output, caches, and
    test fixtures are excluded inside otherwise valid release roots as well.
    """

    root = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        return False

    if not relative.parts:
        return False
    if any(_is_development_artifact_directory(part) for part in relative.parts):
        return False
    if len(relative.parts) == 1:
        return relative.suffix.casefold() in ROOT_RELEASE_DOCUMENT_SUFFIXES
    return relative.parts[0].casefold() in RELEASE_CONTENT_ROOTS


def iter_release_content_files(root: Path, suffixes: Iterable[str]) -> tuple[Path, ...]:
    """Discover files through the same release-content predicate used by checks."""

    root = Path(root).resolve()
    wanted_suffixes = {
        suffix.casefold() if suffix.startswith(".") else f".{suffix.casefold()}"
        for suffix in suffixes
    }
    candidates = {path for path in root.iterdir() if path.is_file()}
    for directory_name in RELEASE_CONTENT_ROOTS:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        candidates.update(path for path in directory.rglob("*") if path.is_file())

    return tuple(sorted(
        path
        for path in candidates
        if path.suffix.casefold() in wanted_suffixes and is_release_content_path(path, root)
    ))
