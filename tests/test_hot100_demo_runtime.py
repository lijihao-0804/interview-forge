import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISUAL_DIR = ROOT / "books" / "hot100" / "05-可视化"


class Hot100DemoRuntimeTests(unittest.TestCase):
    def test_all_visual_pages_reference_one_shared_embed_runtime(self):
        pages = sorted(VISUAL_DIR.glob("*.html"))
        self.assertEqual(len(pages), 25)
        for page in pages:
            text = page.read_text(encoding="utf-8-sig")
            self.assertEqual(text.count('id="hot100-a11y"'), 1, page.name)
            self.assertIn('<script id="hot100-a11y" src="assets/embed-runtime.js"></script>', text, page.name)
            self.assertNotIn("setInterval(reportHeight", text, page.name)
            self.assertNotIn("setInterval(", text, page.name)
            self.assertNotIn("clearInterval(", text, page.name)
            self.assertNotIn("new ResizeObserver(reportHeight)", text, page.name)
            self.assertNotIn("new MutationObserver(reportHeight)", text, page.name)

    def test_shared_runtime_has_only_event_driven_height_measurement(self):
        runtime = (VISUAL_DIR / "assets" / "embed-runtime.js").read_text(encoding="utf-8-sig")
        self.assertIn("scheduleEmbeddedMeasure", runtime)
        self.assertIn("measureFrame", runtime)
        for trigger in ("'load'", "'resize'", "'fonts'", "'panel-change'", "'mode-change'", "'demo-rebuild'"):
            self.assertIn(trigger, runtime)
        self.assertNotIn("new ResizeObserver(reportHeight)", runtime)
        self.assertNotIn("new MutationObserver(reportHeight)", runtime)
        self.assertNotIn("setInterval(reportHeight", runtime)

    def test_demo_kit_uses_fixed_layout_and_single_timeout_lifecycle(self):
        source = (VISUAL_DIR / "assets" / "demo-kit.js").read_text(encoding="utf-8-sig")
        self.assertIn("--dk-stage-height,320px", source)
        self.assertIn("stageHeight", source)
        self.assertIn("height:68px;min-height:68px", source)
        self.assertIn("height:40px;min-height:40px", source)
        self.assertIn("flex-wrap:nowrap", source)
        self.assertIn("overflow-y:hidden", source)
        self.assertIn("function scheduleNext()", source)
        self.assertIn("timer = setTimeout", source)
        self.assertIn("clearTimeout(timer)", source)
        self.assertIn("resetBtn.onclick = rebuild", source)
        self.assertIn('window.addEventListener("pagehide", stop)', source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("clearInterval", source)

    def test_binary_tree_renderer_keeps_edges_in_svg_namespace(self):
        source = (VISUAL_DIR / "二叉树演示.html").read_text(encoding="utf-8-sig")
        self.assertIn('var edges = document.createElementNS(svgNS, "g");', source)
        self.assertNotIn('var edges = el("g");', source)

    def test_binary_tree_demos_use_identity_stable_node_ids(self):
        source = (VISUAL_DIR / "二叉树演示.html").read_text(encoding="utf-8-sig")
        # 节点 id 一旦按值生成，重复值就会让 FLIP 认错身份；改用自增序号。
        self.assertNotIn("nodeIdByValue", source)
        self.assertIn('id: "s" + (seq++)', source)
        self.assertIn('id: "b" + (seq++)', source)

    def test_demo_kit_pages_pass_headless_structure_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "test_hot100_demo_pages.js")],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALL OK", result.stdout)

    def test_native_visual_pages_use_single_timeout_and_pagehide_cleanup(self):
        native_pages = (
            "01-哈希表.html",
            "02.双指针.html",
            "10-回溯.html",
            "TCP握手挥手可视化.html",
            "排序算法可视化.html",
            "数据结构操作可视化.html",
            "树形查找算法可视化.html",
            "查找算法可视化.html",
            "锁升级可视化.html",
        )
        for name in native_pages:
            source = (VISUAL_DIR / name).read_text(encoding="utf-8-sig")
            self.assertIn("setTimeout", source, name)
            self.assertNotIn("setInterval(", source, name)
            self.assertNotIn("clearInterval(", source, name)
            self.assertIn("pagehide", source, name)

    def test_parent_visual_height_messages_are_raf_merged(self):
        source = (ROOT / "assets" / "site.js").read_text(encoding="utf-8-sig")
        self.assertIn("pendingVisualHeights", source)
        self.assertIn("requestAnimationFrame(flushVisualHeights)", source)
        self.assertNotIn("frame.style.height = `${nextHeight}px`", source.split("const pendingVisualHeights", 1)[0])


if __name__ == "__main__":
    unittest.main()
