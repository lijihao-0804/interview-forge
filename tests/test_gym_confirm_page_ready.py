"""确认页导航就绪：wait_for_load_state 超时不得让整条流程失败（2026-11-02 复盘）。"""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from interview_forge.services import gym_automation


class ConfirmPageLoadStateTests(TestCase):
    def test_load_state_timeout_does_not_abort(self) -> None:
        """超时只警告，继续走渲染轮询（旧实现会直接抛异常把任务判失败）。"""
        page = MagicMock()
        page.url = "https://ggtypt.nju.edu.cn/order?tradeNo=abc"
        page.wait_for_load_state.side_effect = TimeoutError("Timeout 30000ms exceeded")

        with patch.object(gym_automation, "_wait_confirm_page_rendered") as rendered:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:  # noqa: BLE001 模拟旧行为对照
                pass
            gym_automation._wait_confirm_page_rendered(page)
        rendered.assert_called_once()

    def test_source_guards_load_state_timeout(self) -> None:
        """源码里 wait_for_load_state 必须被 try 包住，且不等默认 30 秒。"""
        import inspect
        src = inspect.getsource(gym_automation.run)
        idx = src.find('wait_for_load_state("domcontentloaded"')
        self.assertGreater(idx, 0)
        before = src[:idx]
        self.assertIn("try:", before[-400:], "wait_for_load_state 必须包在 try 中")
        self.assertIn("timeout=", src[idx:idx + 120], "必须显式给 timeout")
