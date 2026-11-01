"""日期比较回归：站点在每月 1~9 号会把日号补零，不能因此误判失败。"""
from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from interview_forge.services import gym_automation


def _page_with(active_text: str) -> Mock:
    page = Mock()
    page.evaluate.return_value = active_text
    return page


class TargetDateCompareTests(TestCase):
    def test_zero_padded_day_is_accepted(self) -> None:
        """页面显示「星期日11月01日」，目标是 11 月 1 日 —— 必须通过。"""
        with patch.object(gym_automation.time, "sleep"):
            gym_automation.ensure_target_date(_page_with("星期日11月01日"), date(2026, 11, 1))

    def test_two_digit_day_still_accepted(self) -> None:
        with patch.object(gym_automation.time, "sleep"):
            gym_automation.ensure_target_date(_page_with("星期五10月31日"), date(2026, 10, 31))

    def test_mismatched_day_is_rejected(self) -> None:
        with patch.object(gym_automation.time, "sleep"):
            with self.assertRaises(RuntimeError):
                gym_automation.ensure_target_date(_page_with("星期五10月30日"), date(2026, 10, 31))

    def test_mismatched_month_is_rejected(self) -> None:
        with patch.object(gym_automation.time, "sleep"):
            with self.assertRaises(RuntimeError):
                gym_automation.ensure_target_date(_page_with("星期日11月01日"), date(2026, 12, 1))

    def test_empty_active_date_is_rejected(self) -> None:
        with patch.object(gym_automation.time, "sleep"):
            with self.assertRaises(RuntimeError):
                gym_automation.ensure_target_date(_page_with(""), date(2026, 11, 1))
