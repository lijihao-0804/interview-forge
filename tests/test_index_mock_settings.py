"""守住 index.html 的模拟考试设置与自测联动，防止被整页覆盖时再次回退。

背景：2026-10-31 一次 glossary 改动误用旧版 index.html 覆盖，把题数/时长/
抽题范围设置和 ?selftest=1 联动一起删掉了。这组测试专门盯着这些不变量。
"""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]


class IndexMockSettingsTests(TestCase):
    def setUp(self) -> None:
        self.source = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_setup_controls_exist(self) -> None:
        for control in ("mockCount", "mockMinutes", "mockScope"):
            self.assertIn(f'id="{control}"', self.source, f"缺少模拟考试设置控件 #{control}")

    def test_defaults_are_five_questions_sixty_minutes(self) -> None:
        self.assertIn('<option value="5" selected>', self.source, "题数默认应为 5")
        self.assertIn('<option value="60" selected>', self.source, "时长默认应为 60 分钟")

    def test_scope_options_present(self) -> None:
        for scope in ("all", "today", "recent", "recent7", "stale", "unseen"):
            self.assertIn(f'value="{scope}"', self.source, f"缺少抽题范围选项 {scope}")

    def test_mock_links_carry_selftest_flag(self) -> None:
        self.assertIn("selftest=1", self.source, "模拟考试题解链接必须带 ?selftest=1")
        self.assertIn("mockHref", self.source, "缺少生成自测链接的 mockHref 逻辑")

    def test_scope_maps_to_backend_params(self) -> None:
        # 抽题范围需要映射成后端的 scope + days 两个参数
        self.assertIn("scopeMap", self.source, "缺少 scope → (scope, days) 的映射")
        self.assertRegex(self.source, r"/api/mock\?[^\n]*scope=")


class SelfTestScopeTests(TestCase):
    """自测模式只能由考试链接（?selftest=1）或当前页手动开启，不得跨页持久化。"""

    def setUp(self) -> None:
        self.build = (ROOT / "scripts/build/build_html_site.py").read_text(encoding="utf-8")

    def test_selftest_reads_url_param(self) -> None:
        self.assertIn('params.get("selftest") === "1"', self.build)

    def test_selftest_clears_url_after_read(self) -> None:
        # 读后立刻从地址栏移除，刷新/分享不再重复触发
        self.assertIn("replaceState", self.build)

    def test_selftest_not_persisted_to_localstorage(self) -> None:
        # 不能把手动开启写进 localStorage，否则从书架/搜索进任何题解页都会变自测
        self.assertNotIn("localStorage.setItem(KEY", self.build)
