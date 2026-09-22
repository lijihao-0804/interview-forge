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
        """链表指针实验室迁到 DemoKit 后，仍要讲清「先存 next、再改边、最后移指针」。"""
        source = self.read("链表指针实验室.html")
        self.assertIn("DemoKit.mount(", source)
        for phase in ("save_next", "swap_prepare", "swap_move", "pointer_move", "done"):
            self.assertIn('ctx.phase("' + phase + '"', source)
        # next 字段表取代了旧的 linkMap，本步改写的那条边仍要标出来。
        self.assertIn("next 字段表", source)
        self.assertIn("edge-changing", source)
        self.assertIn("current.next 从原来的后继改为 prev", source)
        # 三道题（206 / 92 / 25）都要有多语言代码面板与不变量。
        for no in ('no: "206"', 'no: "92"', 'no: "25"'):
            self.assertIn(no, source)
        self.assertEqual(3, source.count("invariants: ["))
        self.assertEqual(3, source.count("langs: {"))

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

    def test_native_lab_skeleton_is_still_normalized_by_the_builder(self):
        """05-可视化 下已无原生 toolbar 实验室，但站点构建仍要负责统一其余原生页的骨架。"""
        build = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8-sig")
        self.assertIn("原生实验室也统一成", build)
        self.assertIn("body > main.shell > .panel", build)
        self.assertIn("body > main.shell > .toolbar", build)

    def test_hard_state_lab_is_demokit_with_seven_distinct_problems(self):
        """困难题核心状态实验室迁到 DemoKit 后，七道题各自的核心状态都要看得见。"""
        source = self.read("困难题核心状态实验室.html")
        self.assertIn("DemoKit.mount(", source)
        self.assertNotIn('class="toolbar"', source)
        # 只保留别处没讲过的七道硬题（25/76/84/72 已分别在其它页里讲过）。
        for no in ('no: "239"', 'no: "295"', 'no: "41"', 'no: "32"',
                   'no: "23"', 'no: "124"', 'no: "4"'):
            self.assertIn(no, source)
        for gone in ('no: "25"', 'no: "76"', 'no: "84"', 'no: "72"'):
            self.assertNotIn(gone, source)
        # 每道题都要有多语言代码面板与不变量。
        self.assertEqual(7, source.count("invariants: ["))
        self.assertEqual(7, source.count("langs: {"))
        # 单调队列的两次出队、对顶堆的搬运、后序递归的进出栈都要用统一的相位词。
        for phase in ("compare", "enqueue", "dequeue", "swap_move",
                      "recursive_enter", "recursive_return", "done"):
            self.assertIn('ctx.phase("' + phase + '"', source)
        self.assertIn("调用栈", source)

    def test_tree_dfs_and_bfs_steps_are_phase_explicit(self):
        source = self.read("二叉树演示.html")
        self.assertIn('ctx.phase("recursive_enter"', source)
        self.assertIn('ctx.phase("recursive_return"', source)
        self.assertIn('ctx.phase("visit"', source)
        self.assertIn('ctx.phase("dequeue"', source)
        self.assertIn('ctx.phase("enqueue"', source)
        self.assertIn('ctx.phase("done"', source)
        self.assertIn("调用栈", source)

    def test_dp_shows_dependency_then_write(self):
        """二维 DP 页迁到 DemoKit 后，仍要保留「先亮依赖格、再写入当前格」这两拍。"""
        source = self.read("动态规划状态转移.html")
        self.assertIn("DemoKit.mount(", source)
        # 依赖格用 cmp 高亮，当前格写入时用 write 高亮。
        self.assertIn('st[d[0]][d[1]] = "cmp"', source)
        self.assertIn('"write"', source)
        self.assertIn('ctx.step("写入 dp[', source)
        # 三道题都要有状态转移方程、对照代码与不变量。
        for formula in (
            "dp[i][j] = 相同 ? 左上+1 : max(上, 左)",
            "dp[i][j] = 1 + min(左上, 上, 左)",
            "dp[i][j] = dp[i-1][j] + dp[i][j-1]",
        ):
            self.assertIn(formula, source)
        self.assertEqual(3, source.count("invariants: ["))
        self.assertEqual(3, source.count("langs: {"))


if __name__ == "__main__":
    unittest.main()
