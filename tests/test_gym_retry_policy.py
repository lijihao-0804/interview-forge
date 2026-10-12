"""健身房同日订单、放号时间与瞬时重试策略测试。"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from interview_forge.services import gym, gym_automation


class GymAutomationOrderPolicyTests(unittest.TestCase):
    def test_same_day_booking_only_blocks_the_exact_selected_slot(self) -> None:
        rows = [
            "健身房预约 2026-10-12 17:00-18:00 已支付 正常",
        ]
        state = gym_automation._summarize_order_rows(rows, date(2026, 10, 12))

        self.assertEqual(state["booked"], rows)
        self.assertEqual(
            gym_automation._slots_not_already_booked(
                ["17:00-18:00", "16:00-17:00"], state["booked"]),
            ["16:00-17:00"],
        )
        self.assertEqual(
            gym_automation._slots_not_already_booked(["17:00-18:00"], state["booked"]),
            [],
        )

    def test_unpaid_order_is_not_classified_as_valid_booking(self) -> None:
        state = gym_automation._summarize_order_rows(
            ["健身房预约 2026-10-12 17:00-18:00 待支付"], date(2026, 10, 12))
        self.assertEqual(state["booked"], [])
        self.assertEqual(len(state["pending"]), 1)

    def test_daily_limit_message_is_detected_without_whitespace_sensitivity(self) -> None:
        self.assertEqual(
            gym_automation._daily_limit_message("您今天已预约过，每天只能预约一次"),
            "每天只能",
        )

    def test_daily_limit_response_mentions_existing_valid_booking(self) -> None:
        row = "健身房预约 2026-10-12 17:00-18:00 已支付 正常 订单号: PRIVATE-ORDER-ID"

        class Page:
            def evaluate(self, _script: str) -> str:
                return "您当天已有预约，每天只能预约一次"

        with patch.object(gym_automation, "check_existing_orders", return_value={
            "booked": [row], "pending": [], "relevant": [row],
        }):
            result = gym_automation._result_without_confirmation(
                Page(), date(2026, 10, 12), "16:00-17:00", [row])

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["retryable"])
        self.assertIn("每天只能", result["detail"])
        self.assertIn("17:00-18:00", result["detail"])
        self.assertNotIn("PRIVATE-ORDER-ID", result["detail"])

    def test_booking_flow_waits_until_release_even_when_started_early(self) -> None:
        tz = timezone(timedelta(hours=8))
        self.assertEqual(
            gym_automation._booking_release_delay_seconds(
                datetime(2026, 10, 12, 7, 0, 0, tzinfo=tz)),
            60 * 60 + 20,
        )
        self.assertEqual(
            gym_automation._booking_release_delay_seconds(
                datetime(2026, 10, 12, 8, 0, 20, tzinfo=tz)),
            0,
        )


class GymSchedulerRetryPolicyTests(unittest.TestCase):
    def test_scheduler_does_not_start_before_0800(self) -> None:
        self.assertEqual(gym.RUN_EARLIEST, (8, 0))

    def test_retry_waits_until_three_minute_deadline(self) -> None:
        now = datetime(2026, 10, 12, 8, 0, tzinfo=gym.SHANGHAI)
        self.assertFalse(gym._retry_is_due(
            {"retry_after": (now + timedelta(minutes=3)).isoformat()}, now))
        self.assertTrue(gym._retry_is_due(
            {"retry_after": (now + timedelta(minutes=3)).isoformat()},
            now + timedelta(minutes=3),
        ))

    def test_only_explicitly_retryable_failed_jobs_are_deferred(self) -> None:
        job = {"id": 91, "result": {}}
        result = {"detail": "场次页暂时未渲染", "retryable": True}
        with patch.object(gym, "_finish_job") as finish:
            deferred = gym._defer_transient_retry(job, "failed", result)

        self.assertTrue(deferred)
        finish.assert_called_once()
        self.assertEqual(finish.call_args.args[1], "pending")
        stored = finish.call_args.args[2]
        self.assertEqual(stored["attempt"], 2)
        self.assertIn("retry_after", stored)

    def test_ambiguous_results_are_never_retried_blindly(self) -> None:
        with patch.object(gym, "_finish_job") as finish:
            deferred = gym._defer_transient_retry(
                {"id": 92, "result": {}},
                "ambiguous",
                {"detail": "订单状态无法核验", "retryable": True},
            )
        self.assertFalse(deferred)
        finish.assert_not_called()

    def test_transient_failure_stops_after_three_total_attempts(self) -> None:
        result = {"detail": "页面仍未渲染", "retryable": True}
        with patch.object(gym, "_finish_job") as finish:
            deferred = gym._defer_transient_retry(
                {"id": 93, "result": {"attempt": gym.JOB_MAX_ATTEMPTS}},
                "failed",
                result,
            )

        self.assertFalse(deferred)
        finish.assert_not_called()
        self.assertTrue(result["retry_exhausted"])
        self.assertFalse(result["retryable"])
        self.assertIn("3 次", result["detail"])


if __name__ == "__main__":
    unittest.main()
