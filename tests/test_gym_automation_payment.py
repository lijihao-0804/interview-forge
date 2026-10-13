"""健身房确认页金额判定与支付安全门测试。"""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from interview_forge.services import gym_automation
from interview_forge.services.gym_automation import parse_order_amount, pay_and_verify


class GymPaymentAmountTests(unittest.TestCase):
    def test_parses_common_explicit_amount_labels(self) -> None:
        for text in (
            "订单金额：¥0.00",
            "应付金额 ￥ 0.00 元",
            "实付金额 0 元",
            "金额: 人民币 0.00",
            "待支付：0.00元",
            "请您支付：\n¥\n0\n元",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_order_amount(text), 0.0)

    def test_unknown_or_conflicting_amount_stays_unknown(self) -> None:
        self.assertIsNone(parse_order_amount("确认订单\n请在 5 分钟内完成支付"))
        self.assertIsNone(parse_order_amount("订单金额：0 元\n应付金额：10 元"))

    def test_known_nonzero_amount_is_never_clicked(self) -> None:
        class Page:
            def evaluate(self, _script: str) -> str:
                return "应付金额：￥10.00 元"

            def locator(self, *_args, **_kwargs):
                raise AssertionError("known nonzero amount must stop before button lookup")

        status, detail = pay_and_verify(Page(), date(2026, 10, 12), "17:00-18:00")
        self.assertEqual(status, "failed")
        self.assertIn("10.0 元", detail)

    def test_conflicting_amount_labels_are_never_clicked(self) -> None:
        class Page:
            def evaluate(self, _script: str) -> str:
                return "订单金额：0 元\n应付金额：10 元"

            def locator(self, *_args, **_kwargs):
                raise AssertionError("conflicting amounts must stop before button lookup")

        status, detail = pay_and_verify(Page(), date(2026, 10, 12), "17:00-18:00")
        self.assertEqual(status, "failed")
        self.assertIn("数值冲突", detail)

    def test_unknown_amount_does_not_persist_page_screenshot_or_diagnostics(self) -> None:
        class EmptyLocator:
            def filter(self, **_kwargs):
                return self

            def count(self) -> int:
                return 0

        class Page:
            def __init__(self) -> None:
                self.screenshots: list[str] = []

            def evaluate(self, script: str):
                if "document.body.innerText" in script:
                    return "订单确认\n待支付\n请在 5 分钟内完成"
                if "document.querySelectorAll" in script:
                    return []
                raise AssertionError(f"unexpected page evaluation: {script}")

            def screenshot(self, *, path: str) -> None:
                self.screenshots.append(path)

            def locator(self, *_args, **_kwargs):
                return EmptyLocator()

            def get_by_text(self, *_args, **_kwargs):
                return EmptyLocator()

        page = Page()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                gym_automation, "click_first_visible", return_value=False
            ) as fallback:
                status, detail = pay_and_verify(
                    page, date(2026, 10, 12), "17:00-18:00", Path(tmp))
            fallback.assert_not_called()
            self.assertEqual(status, "ambiguous")
            self.assertIn("未点击支付", detail)
            self.assertEqual(page.screenshots, [])
            self.assertFalse((Path(tmp) / "pay-inspect.json").exists())

    def test_unknown_amount_never_clicks_even_when_payment_button_is_visible(self) -> None:
        class Page:
            def __init__(self) -> None:
                self.clicked = False
                self.screenshots = []

            def evaluate(self, script: str):
                if "document.body.innerText" in script:
                    return "订单确认\n请完成支付"
                if "const candidates" in script:
                    return []
                if "querySelectorAll" in script:
                    return [{"tag": "BUTTON", "cls": "pay", "text": "支付",
                             "rect": [1, 2, 3, 4], "disabled": False}]
                raise AssertionError(f"unexpected page evaluation: {script}")

            def locator(self, *_args, **_kwargs):
                raise AssertionError("unknown confirmation amount must stop before button lookup")

            def screenshot(self, *, path: str) -> None:
                self.screenshots.append(path)

        page = Page()
        with patch.object(gym_automation.time, "sleep"):
            status, detail = pay_and_verify(page, date(2026, 10, 12), "17:00-18:00")
        self.assertFalse(page.clicked)
        self.assertEqual(status, "ambiguous")
        self.assertIn("未点击支付", detail)
        self.assertEqual(page.screenshots, [])

    def test_explicit_zero_amount_clicks_and_returns_redacted_verified_result(self) -> None:
        class Button:
            def __init__(self, page) -> None:
                self.page = page

            def is_visible(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def inner_text(self) -> str:
                return "支付（57s）"

            def click(self) -> None:
                self.page.clicked = True

        class Buttons:
            def __init__(self, page, selector: str) -> None:
                self.page = page
                self.selector = selector
                self.text = ""

            def filter(self, *, has_text: str):
                self.text = has_text
                return self

            def count(self) -> int:
                return int(self.selector == ".btn" and self.text == "支付")

            def nth(self, _index: int) -> Button:
                return Button(self.page)

        class Page:
            url = "https://ggtypt.nju.edu.cn/venue/orders"

            def __init__(self) -> None:
                self.clicked = False

            def evaluate(self, script: str):
                if "document.body.innerText" in script:
                    return "订单金额：¥0.00"
                if "const candidates" in script:
                    return ["健身房预约 2026-10-12 17:00-18:00 已支付 正常 PRIVATE-ORDER-ID"]
                raise AssertionError(f"unexpected page evaluation: {script}")

            def locator(self, selector: str) -> Buttons:
                return Buttons(self, selector)

        page = Page()
        with patch.object(gym_automation.time, "sleep"), \
             patch.object(gym_automation, "confirm_if_popped", return_value=False):
            status, detail = pay_and_verify(page, date(2026, 10, 12), "17:00-18:00")
        self.assertTrue(page.clicked)
        self.assertEqual(status, "succeeded")
        self.assertIn("17:00-18:00", detail)
        self.assertNotIn("PRIVATE-ORDER-ID", detail)

    def test_confirmation_page_is_waited_for_before_reading_the_amount(self) -> None:
        """确认页由站点 JS 渲染：刚拿到标签页时正文为空，不能当成「金额不可识别」。

        2026-10-13 线上 08:01 就是这样拒绝支付的：日志里「支付页可见控件」为空。
        """

        class Button:
            def __init__(self, page) -> None:
                self.page = page

            def is_visible(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def inner_text(self) -> str:
                return "支付 （57s）"

            def click(self) -> None:
                self.page.clicked = True

        class Buttons:
            def __init__(self, page, selector: str) -> None:
                self.page = page
                self.selector = selector
                self.text = ""

            def filter(self, *, has_text: str):
                self.text = has_text
                return self

            def count(self) -> int:
                return int(self.selector == ".btn" and self.text == "支付")

            def nth(self, _index: int) -> Button:
                return Button(self.page)

        class Page:
            url = "https://ggtypt.nju.edu.cn/venue/orders"

            def __init__(self, empty_reads: int, amount_text: str) -> None:
                self.clicked = False
                self.reads = 0
                self.empty_reads = empty_reads
                self.amount_text = amount_text

            def evaluate(self, script: str):
                if "document.body.innerText" in script:
                    self.reads += 1
                    return "" if self.reads <= self.empty_reads else self.amount_text
                if "const candidates" in script:
                    return ["健身房预约 2026-10-13 17:00-18:00 已支付 正常"]
                raise AssertionError(f"unexpected page evaluation: {script}")

            def locator(self, selector: str) -> Buttons:
                return Buttons(self, selector)

        cases = (
            (2, "请您支付：\n¥\n0\n元", True, "succeeded"),
            (2, "请您支付：\n¥\n10\n元", False, "failed"),
        )
        for empty_reads, amount_text, should_click, expected in cases:
            with self.subTest(amount_text=amount_text, empty_reads=empty_reads):
                page = Page(empty_reads, amount_text)
                with patch.object(gym_automation.time, "sleep"), \
                     patch.object(gym_automation, "confirm_if_popped", return_value=False):
                    status, _detail = pay_and_verify(page, date(2026, 10, 13), "17:00-18:00")
                self.assertEqual(page.clicked, should_click)
                self.assertEqual(status, expected)
                self.assertGreater(page.reads, empty_reads)

    def test_blank_confirmation_page_is_captured_without_personal_data(self) -> None:
        """空确认页没有姓名/订单信息，留一张图正好补上线上那次“页面没渲染”的盲区。"""

        class EmptyLocator:
            def filter(self, **_kwargs):
                return self

            def count(self) -> int:
                return 0

        class Page:
            def __init__(self) -> None:
                self.screenshots: list[str] = []

            def evaluate(self, script: str):
                if "document.body.innerText" in script:
                    return ""
                if "querySelectorAll" in script:
                    return []
                if "const candidates" in script:
                    return []
                raise AssertionError(f"unexpected page evaluation: {script}")

            def screenshot(self, *, path: str) -> None:
                self.screenshots.append(path)
                Path(path).write_bytes(b"fake-png")

            def locator(self, *_args, **_kwargs):
                return EmptyLocator()

            def get_by_text(self, *_args, **_kwargs):
                return EmptyLocator()

        page = Page()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gym_automation.time, "sleep"):
                status, detail = pay_and_verify(page, date(2026, 10, 13), "17:00-18:00", Path(tmp))
            self.assertEqual(status, "ambiguous")
            self.assertIn("未点击支付", detail)
            self.assertEqual([Path(p).name for p in page.screenshots],
                             ["confirm-page-blank.png"])
            self.assertTrue((Path(tmp) / "confirm-page-blank.png").exists())

    def test_manual_captcha_mode_accepts_confirmation_tab_without_ocr(self) -> None:
        class Page:
            url = "https://ggtypt.nju.edu.cn/venue/confirm?tradeNo=example"

            context = object()

        page = Page()
        self.assertIs(
            gym_automation.solve_click_captcha(page, None, manual_only=True),
            page,
        )


class GymCaptureDirTests(unittest.TestCase):
    def test_capture_dirs_keep_only_the_newest_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("20261001-010101", "20261002-020202", "20261003-030303"):
                (root / name).mkdir()
                (root / name / "captcha-attempt1.png").write_bytes(b"x")
            (root / "not-a-run").mkdir()
            (root / "pay-inspect.json").write_text("{}", encoding="utf-8")

            gym_automation._prune_capture_dirs(root, keep=2)

            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             ["20261002-020202", "20261003-030303", "not-a-run",
                              "pay-inspect.json"])


if __name__ == "__main__":
    unittest.main()
