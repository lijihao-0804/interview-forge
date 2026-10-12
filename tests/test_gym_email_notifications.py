"""用户可读的健身房预约邮件文案测试。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from interview_forge.services import gym

JOB = {
    "id": 27,
    "created_by": "student01",
    "target_date": "2026-10-12",
    "slots": ["17:00-18:00", "18:00-19:00"],
    "venue": "129",
}


class GymEmailNotificationTests(unittest.TestCase):
    def _mail(self, status: str, result: dict) -> tuple[str, str]:
        with patch.object(gym, "send_mail") as send_mail:
            gym.notify_job_result(JOB, status, result)
        send_mail.assert_called_once()
        return send_mail.call_args.args[1], send_mail.call_args.args[2]

    def test_success_email_says_booking_was_verified_in_plain_language(self) -> None:
        subject, body = self._mail("succeeded", {
            "actual_slot": "17:00-18:00",
            "detail": "订单核验通过：内部订单行 ...",
        })

        self.assertIn("预约成功", subject)
        self.assertIn("已经在南大场馆订单记录中核实到一条有效预约", body)
        self.assertIn("2026年10月12日（星期一）", body)
        self.assertIn("南大健身房（一层）", body)
        self.assertNotIn("内部订单行", body)
        self.assertNotIn("succeeded", body)

    def test_existing_booking_is_explained_as_duplicate_protection_not_failure(self) -> None:
        subject, body = self._mail("failed", {
            "existing_bookings": ["17:00-18:00"],
            "detail": "当天已存在有效预约（17:00-18:00），本次任务已停止，未尝试其他时段。",
        })

        self.assertIn("已避免重复提交", subject)
        self.assertIn("当天已经有预约", body)
        self.assertIn("17:00-18:00", body)
        self.assertIn("没有再尝试其他时段", body)
        self.assertIn("已有预约被保留", body)

    def test_no_slot_email_says_what_happened_and_what_user_can_do(self) -> None:
        subject, body = self._mail("no_slot", {"detail": "多次查询均无空位（15 次，约 30 分钟）"})

        self.assertIn("暂时没有空位", subject)
        self.assertIn("约半小时", body)
        self.assertIn("没有等到可预约名额", body)
        self.assertIn("换一个日期", body)

    def test_pending_order_email_tells_user_to_check_before_retrying(self) -> None:
        _subject, body = self._mail("ambiguous", {
            "detail": "当天存在未支付订单，避免重复下单，请人工确认：17:00-18:00",
        })

        self.assertIn("已经生成了 17:00-18:00 的订单", body)
        self.assertIn("没有继续提交", body)
        self.assertIn("请先打开南大场馆订单页查看状态", body)

    def test_nonzero_price_email_explains_the_safety_stop(self) -> None:
        _subject, body = self._mail("failed", {
            "detail": "订单金额为 10.0 元（非 0），按安全规则停止",
        })

        self.assertIn("金额需要确认", body)
        self.assertIn("10.0 元", body)
        self.assertIn("避免意外扣费", body)
        self.assertIn("没有由自动流程完成支付", body)

    def test_retry_exhaustion_translates_executor_error_and_hides_raw_detail(self) -> None:
        _subject, body = self._mail("failed", {
            "retry_exhausted": True,
            "attempt": 3,
            "detail": "已连续尝试 3 次，停止自动重试。最后结果：异常：场次页未渲染出时段表格/日期条",
            "last_attempt_detail": "异常：场次页未渲染出时段表格/日期条",
        })

        self.assertIn("预约页面暂时没有正常加载", body)
        self.assertIn("已尝试 3 次", body)
        self.assertNotIn("异常：", body)
        self.assertNotIn("日期条", body)

    def test_unrecognized_exception_is_not_dumped_as_technical_code(self) -> None:
        _subject, body = self._mail("failed", {
            "detail": "RuntimeError: secret internal stack trace",
        })

        self.assertIn("预约没有完成，需要检查一下", body)
        self.assertIn("请先到南大订单页确认", body)
        self.assertNotIn("RuntimeError", body)
        self.assertNotIn("secret internal stack trace", body)

    def test_test_email_has_a_friendly_explanation(self) -> None:
        with patch.object(gym, "send_mail") as send_mail, \
             patch.object(gym, "notify_status", return_value={"configured": True}):
            gym.send_test_email("student01")

        body = send_mail.call_args.args[2]
        self.assertIn("收到它，说明收件邮箱和全局发件配置已经连通", body)
        self.assertIn("祝预约顺利", body)


if __name__ == "__main__":
    unittest.main()
