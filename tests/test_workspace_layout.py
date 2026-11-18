"""Keep generated reading styles and source layouts in sync."""
from pathlib import Path
import unittest
from scripts.build.build_html_site import SITE_CSS
from scripts.build.build_library import LIBRARY_CSS

ROOT=Path(__file__).resolve().parents[1]

class WorkspaceLayoutTests(unittest.TestCase):
    def test_shared_layout_survives_both_generators(self):
        css=(ROOT/'assets/workspace-layout.css').read_text().strip()
        for source,output in [(SITE_CSS,'assets/site.css'),(LIBRARY_CSS,'library/assets/library.css')]:
            self.assertIn(css,source)
            self.assertEqual(source.strip(),(ROOT/output).read_text().strip())

    def test_all_workspace_pages_load_scoped_layout(self):
        paths=['cockpit.html','index.html','tools/templates/dashboard.tpl']
        paths += ['pages/'+name+'.html' for name in ['account','forgot-password','admin','ai-assistant','favorites','history','leetcode-connect','login','notices','quiz','register','tools','tools/nju-booking']]
        for path in paths:
            with self.subTest(path=path):
                text=(ROOT/path).read_text()
                self.assertIn('data-forge-page=',text)
                self.assertIn('assets/workspace-layout.css',text)

    def test_private_archive_stays_out_of_service_worker_cache(self):
        sw=(ROOT/'service-worker.js').read_text()
        self.assertIn('url.pathname.startsWith("/api/")',sw)
        self.assertLess(sw.index('url.pathname.startsWith("/api/")'),sw.index('event.respondWith('))
