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


class DateMarksTests(TestCase):
    """目标日期的各种写法都要覆盖，否则订单行/日期条会漏匹配。"""

    def test_covers_padded_and_unpadded_forms(self) -> None:
        marks = gym_automation.date_marks(date(2026, 1, 1))
        for expected in ("2026-01-01", "01-01", "1月1日", "1月01日", "01月01日"):
            self.assertIn(expected, marks, f"缺少日期写法 {expected}")

    def test_covers_double_digit_day(self) -> None:
        marks = gym_automation.date_marks(date(2026, 11, 15))
        for expected in ("2026-11-15", "11-15", "11月15日", "11月15日", "11月15日"):
            self.assertIn(expected, marks, f"缺少日期写法 {expected}")


class OrderTextNormalizeTests(TestCase):
    """订单行文本里的全角冒号、波浪号、各种连字符都要能归一。"""

    def test_fullwidth_colon_and_dash(self) -> None:
        self.assertEqual(
            gym_automation._normalize_order_text("17：00－18：00"), "17:00-18:00")

    def test_wave_dash(self) -> None:
        self.assertEqual(
            gym_automation._normalize_order_text("17:00~18:00"), "17:00-18:00")
        self.assertEqual(
            gym_automation._normalize_order_text("17:00～18:00"), "17:00-18:00")

    def test_whitespace_and_en_dash(self) -> None:
        self.assertEqual(
            gym_automation._normalize_order_text("17:00 – 18:00"), "17:00-18:00")

    def test_slot_matching_tolerates_formatting(self) -> None:
        row = "2026-11-01 健身房 17：00－18：00 已支付"
        self.assertTrue(gym_automation._row_matches_slot(row, "17:00-18:00"))
