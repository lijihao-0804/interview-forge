"""Static regression checks for the P0 cockpit failure-isolation path."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CockpitP0Tests(unittest.TestCase):
    def test_service_worker_version_and_update_contract(self):
        source = (ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn('const VERSION = "hot100-v9-20260919"', source)
        self.assertIn("self.clients.claim()", source)
        self.assertIn('event.data.type === "SKIP_WAITING"', source)
        self.assertIn("caches.delete(key)", source)
        self.assertIn("cache.add(url)", source)
        self.assertNotIn("cache.addAll", source)
        self.assertIn('url.pathname.startsWith("/api/")', source)
        self.assertIn('event.request.mode === "navigate"', source)

    def test_registration_bypasses_http_cache_and_activates_waiting_worker(self):
        for name in ("index.html", "cockpit.html"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("updateViaCache", source, name)
            self.assertIn("none", source, name)
            self.assertTrue("registration.update()" in source or "reg.update()" in source, name)
            self.assertIn("SKIP_WAITING", source, name)

    def test_cockpit_loads_bootstrap_and_plan_independently(self):
        source = (ROOT / "cockpit.html").read_text(encoding="utf-8")
        self.assertIn('function loadBootstrap()', source)
        self.assertIn('function loadPlan()', source)
        self.assertIn('renderModuleError("due-list"', source)
        self.assertIn('renderModuleError("plan-list"', source)
        self.assertIn('"重新加载学习概览"', source)
        self.assertIn('"重试今日计划"', source)
        self.assertNotIn("学习服务暂时不可用，请检查网络后重试", source)
        self.assertIn('error.category === "unauthorized"', source)

    def test_cockpit_api_has_bounded_error_categories(self):
        source = (ROOT / "cockpit.html").read_text(encoding="utf-8")
        for category in ("http_error", "timeout", "network", "invalid_json", "unauthorized"):
            self.assertIn('"%s"' % category, source)
        self.assertIn("error.endpoint", source)
        self.assertIn("error.status", source)


if __name__ == "__main__":
    unittest.main()
