import tempfile
import unittest
from pathlib import Path

from scripts.check.release_content_scope import (
    is_release_content_path,
    iter_release_content_files,
)


class ReleaseContentScopeTests(unittest.TestCase):
    def test_release_checks_include_delivery_pages_and_exclude_artifacts(self):
        release_paths = (
            "books/hot100/03-题解/broken.html",
            "books/hot100/03-题解/broken.md",
            "library/langchain/chapter-01.html",
            "pages/login.html",
            "assets/visual/broken.html",
            "docs/release-notes.md",
            "README.md",
            "MAINTENANCE.md",
            "maintenance.html",
        )
        artifact_paths = (
            ".venv-tools/Lib/site-packages/pkg/broken.html",
            ".venv-ai/lib/python3.11/site-packages/pkg/broken.html",
            "logs/check-final/broken.html",
            "output/playwright/npm-cache/broken.html",
            "node_modules/pkg/broken.html",
            "tests/fixtures/broken.html",
            "scripts/generated-fixture.html",
            "books/hot100/fixtures/broken.html",
            "library/langchain/node_modules/broken.html",
            "docs/.pytest_cache/broken.html",
            "pages/temp/broken.html",
        )
        release_script_paths = (
            "assets/site.js",
            "library/assets/library-mermaid.js",
        )
        artifact_script_paths = (
            "assets/node_modules/pkg/broken.js",
            "library/assets/.venv/broken.js",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative in (
                *release_paths,
                *artifact_paths,
                *release_script_paths,
                *artifact_script_paths,
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("<html><body>scope probe</body></html>", encoding="utf-8")

            discovered = {
                path.relative_to(root).as_posix()
                for path in iter_release_content_files(root, {".html", ".md"})
            }

            self.assertTrue(set(release_paths).issubset(discovered))
            self.assertTrue(set(artifact_paths).isdisjoint(discovered))
            discovered_scripts = {
                path.relative_to(root).as_posix()
                for path in iter_release_content_files(root, {"js"})
            }
            self.assertTrue(set(release_script_paths).issubset(discovered_scripts))
            self.assertTrue(set(artifact_script_paths).isdisjoint(discovered_scripts))
            self.assertTrue(is_release_content_path(root / release_paths[0], root))
            self.assertFalse(is_release_content_path(root / artifact_paths[0], root))


if __name__ == "__main__":
    unittest.main()
