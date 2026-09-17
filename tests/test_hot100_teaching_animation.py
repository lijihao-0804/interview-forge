import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "books" / "hot100" / "05-可视化"


class Hot100TeachingAnimationTests(unittest.TestCase):
    def read(self, name):
        return (VISUAL / name).read_text(encoding="utf-8-sig")

    def test_shared_phase_contract_and_animation_states(self):
        kit = self.read("assets/demo-kit.js")
        css = self.read("assets/demo-teaching.css")
        for phase in (
            "compare", "swap_prepare", "swap_move", "swap_done", "pointer_move",
            "visit", "enqueue", "dequeue", "recursive_enter", "recursive_return", "done",
        ):
            self.assertIn('"' + phase + '"', kit)
        self.assertIn("phase: m.phase || \"update\"", kit)
        self.assertIn("Math.max(speeds[speedIdx][0] * 900, Number(current.duration || 0))", kit)
        self.assertIn(".is-current", css)
        self.assertIn(".is-compare", css)
        self.assertIn(".is-moving", css)
        self.assertIn(".is-visited", css)
        self.assertIn(".is-target", css)
        self.assertIn("swap-moving", css)

    def test_array_swap_is_split_and_has_real_motion(self):
        source = self.read("排序算法可视化.html")
        self.assertIn("phase: 'swap_prepare'", source)
        self.assertIn("phase: 'swap_move'", source)
        self.assertIn("phase: 'swap_done'", source)
        self.assertIn("duration: 420", source)
        self.assertIn("--swap-from", source)
        self.assertIn("@keyframes teachingBarSwap", source)
        self.assertIn("const delay = Math.max(Math.max(20, 120 - speed * 10), Number(step.duration || 0))", source)

    def test_two_pointer_swap_and_pointer_move_are_atomic(self):
        source = self.read("02.双指针.html")
        for phase in ("compare", "swap_prepare", "swap_move", "swap_done", "pointer_move"):
            self.assertIn("phase: '" + phase + "'", source)
        self.assertIn("pair: [left, right]", source)
        self.assertIn("wrapper.classList.add('swap-moving')", source)

    def test_linked_list_exposes_saved_next_and_edge_rewire(self):
        source = self.read("链表指针实验室.html")
        for phase in ("save_next", "swap_prepare", "swap_move", "pointer_move", "done"):
            self.assertIn('"' + phase + '"', source)
        self.assertIn('id="linkMap"', source)
        self.assertIn("current.next 从原来的后继改为 prev", source)
        self.assertIn("edge-changing", source)

    def test_pairwise_linked_list_exposes_each_next_assignment(self):
        source = self.read("链表演示.html")
        for assignment in (
            "first = prev.next", "second = first.next", "next = second.next",
            "first.next = next", "second.next = first", "prev.next = second", "prev = first",
        ):
            self.assertIn('"' + assignment + '"', source)
        for phase in ("save_next", "swap_prepare", "swap_move", "swap_done", "pointer_move", "done"):
            self.assertIn('ctx.phase("' + phase + '"', source)
        self.assertIn("pointerView", source)
        self.assertIn("当前 next 指向", source)

    def test_native_labs_share_the_same_visual_control_flow(self):
        build = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8-sig")
        self.assertIn("原生实验室也统一成", build)
        self.assertIn("body > main.shell > .panel", build)
        self.assertIn("body > main.shell > .toolbar", build)
        for name in (
            "动态规划状态转移.html", "单调栈实验室.html", "滑动窗口与前缀和.html",
            "网格搜索实验室.html", "困难题核心状态实验室.html", "链表指针实验室.html",
        ):
            self.assertIn('class="toolbar"', self.read(name), name)

    def test_tree_dfs_and_bfs_steps_are_phase_explicit(self):
        source = self.read("二叉树演示.html")
        self.assertIn('ctx.phase("recursive_enter"', source)
        self.assertIn('ctx.phase("recursive_return"', source)
        self.assertIn('ctx.phase("visit"', source)
        self.assertIn('ctx.phase("dequeue"', source)
        self.assertIn('ctx.phase("enqueue"', source)
        self.assertIn('ctx.phase("done"', source)
        self.assertIn("调用栈", source)

    def test_dp_shows_compare_dependency_formula_and_write(self):
        source = self.read("动态规划状态转移.html")
        for phase in ("compare", "dependency", "formula", "write", "done"):
            self.assertIn('"' + phase + '"', source)
        self.assertIn("s.pending.deps", source)
        self.assertIn('"dependency"', source)
        self.assertIn("把结果", source)
        self.assertIn("setTimeout", source)


if __name__ == "__main__":
    unittest.main()
