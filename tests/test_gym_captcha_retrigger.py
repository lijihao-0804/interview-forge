"""验证码重新触发（A）与支付核验轮询上限（C）的回归测试。"""
from unittest import TestCase
from unittest.mock import Mock, patch
import inspect

from interview_forge.services import gym_automation


class CaptchaRetriggerTests(TestCase):
    def test_retrigger_reopens_captcha_when_no_confirmation_page(self) -> None:
        """弹窗关闭但确认页不存在时，应重新点「提交」让验证码重现。"""
        page = Mock()
        page.context.pages = []
        btn = Mock()
        btn.count.return_value = 1
        btn.is_visible.return_value = True
        page.get_by_text.return_value.first = btn
        page.evaluate.return_value = {"src": "x", "prompt": "甲 乙"}
        with patch.object(gym_automation, "_confirmation_page", return_value=None), \
                patch("time.sleep"):
            self.assertTrue(gym_automation._retrigger_captcha(page))
        btn.click.assert_called()

    def test_retrigger_refuses_when_confirmation_page_exists(self) -> None:
        """确认页已存在（其实已成功）时绝不能重新提交，避免重复下单。"""
        page = Mock()
        with patch.object(gym_automation, "_confirmation_page", return_value=Mock()), \
                patch("time.sleep"):
            self.assertFalse(gym_automation._retrigger_captcha(page))
        page.get_by_text.assert_not_called()


class PaymentVerificationPollingTests(TestCase):
    def test_wait_for_matching_order_default_cap_is_7s(self) -> None:
        sig = inspect.signature(gym_automation._wait_for_matching_order)
        self.assertEqual(sig.parameters["timeout_ms"].default, 7000,
                         "支付后轮询上限应为 7 秒，订单通常 2~3 秒出现")


class SlotCapacityParseTests(TestCase):
    """从选中块文本解析「本时段已约 N/总 M」，用于记录本次是第几个。"""

    def test_parses_common_capacity_text(self) -> None:
        self.assertEqual(
            gym_automation._parse_slot_capacity("16:00-17:00（11/50）"), (11, 50))
        self.assertEqual(
            gym_automation._parse_slot_capacity("15:00-16:00 (3/50)"), (3, 50))

    def test_returns_none_when_no_capacity(self) -> None:
        for text in ("", None, "16:00-17:00", "已满"):
            self.assertIsNone(gym_automation._parse_slot_capacity(text))
