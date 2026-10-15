"""健身房同日订单、放号时间与瞬时重试策略测试。"""
from __future__ import annotations

import json
import tempfile
import contextlib
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from interview_forge.services import gym, gym_automation


class GymAutomationOrderPolicyTests(unittest.TestCase):
    def test_any_same_day_valid_booking_stops_the_job_before_alternate_slots(self) -> None:
        rows = [
            "健身房预约 2026-10-12 17:00-18:00 已支付 正常",
        ]
        state = gym_automation._summarize_order_rows(rows, date(2026, 10, 12))

        self.assertEqual(state["booked"], rows)
        result = gym_automation._existing_booking_failure(state["booked"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["existing_bookings"], ["17:00-18:00"])
        self.assertIn("本次任务已停止", result["detail"])
        self.assertIn("17:00-18:00", result["detail"])

    def test_selected_venue_ignores_an_explicit_booking_on_the_other_floor(self) -> None:
        rows = [
            "健身房预约 一楼 2026-10-12 17:00-18:00 已支付 正常",
            "健身房预约 负一楼 2026-10-12 18:00-19:00 已支付 正常",
        ]
        first_floor = gym_automation._summarize_order_rows(
            rows, date(2026, 10, 12), venue="129")
        basement = gym_automation._summarize_order_rows(
            rows, date(2026, 10, 12), venue="162")

        self.assertEqual(first_floor["booked"], [rows[0]])
        self.assertEqual(basement["booked"], [rows[1]])

    def test_screenshot_shaped_paid_basement_order_matches_precheck(self) -> None:
        row = (
            "[在线预约] D261012001505 仙林校区仙林校区方笙体育馆负一层健身房 "
            "2026-10-12 健身房 16:00-17:00 已支付 正常 0元"
        )
        state = gym_automation._summarize_order_rows(
            [row], date(2026, 10, 12), venue="162")

        self.assertEqual(state["booked"], [row])

    def test_post_submit_missing_confirmation_is_ambiguous_not_retryable(self) -> None:
        class Page:
            def evaluate(self, _script: str) -> str:
                return ""

        with patch.object(gym_automation, "check_existing_orders", return_value={
            "booked": [], "pending": [], "relevant": [],
        }):
            result = gym_automation._result_without_confirmation(
                Page(), date(2026, 10, 12), "16:00-17:00")

        self.assertEqual(result["status"], "ambiguous")
        self.assertFalse(result["retryable"])
        self.assertTrue(result["needs_manual_check"])
        self.assertIn("停止自动重试", result["detail"])

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

    def test_order_page_empty_dom_is_not_treated_as_a_confirmed_empty_list(self) -> None:
        class Page:
            def wait_for_function(self, script: str, *, timeout: int) -> None:
                self.script = script
                self.timeout = timeout
                raise TimeoutError("order list never rendered")

        with self.assertRaises(gym_automation.OrderPageNotReady):
            gym_automation._wait_order_list_ready(Page(), timeout_ms=100)

    def test_explicit_empty_marker_or_rows_are_the_only_order_list_ready_signal(self) -> None:
        class Page:
            def __init__(self) -> None:
                self.waited = False

            def wait_for_function(self, script: str, *, timeout: int) -> None:
                self.waited = "暂无订单" in script

            def evaluate(self, script: str):
                self.extraction = "table tbody tr" in script
                return []

        page = Page()
        self.assertEqual(gym_automation._wait_order_list_ready(page), [])
        self.assertTrue(page.waited)
        self.assertTrue(page.extraction)

    def test_order_list_readiness_ignores_pagination_and_requires_record_signature(self) -> None:
        for script in (gym_automation._ORDER_LIST_READY_JS, gym_automation._ORDER_ROWS_JS):
            self.assertNotIn(".order-list li", script)
            self.assertIn(r"D\d{8,}", script)
            self.assertIn(r"\d{4}[-/.]\d{1,2}", script)
        self.assertIn("Date.now() - previous.since >= 1500",
                      gym_automation._ORDER_LIST_READY_JS)

    def test_order_log_summary_does_not_include_personal_order_fields(self) -> None:
        summary = gym_automation._safe_order_log_label(
            "健身房 2026-10-12 李同学 17:00-18:00 已支付 正常 订单号 PRIVATE-123"
        )
        self.assertIn("17:00-18:00", summary)
        self.assertIn("已支付", summary)
        self.assertNotIn("李同学", summary)
        self.assertNotIn("PRIVATE-123", summary)


class GymNavigationTimeoutTests(unittest.TestCase):
    """放号瞬间站点很慢：导航不能沿用 8 秒默认超时。"""

    def test_navigation_gets_a_wider_timeout_than_the_page_default(self) -> None:
        page = Mock()
        gym_automation.robust_goto(page, "https://example.invalid/venue/1")
        self.assertEqual(page.goto.call_args.kwargs["timeout"],
                         gym_automation.PAGE_NAV_TIMEOUT_MS)
        self.assertGreater(gym_automation.PAGE_NAV_TIMEOUT_MS, 8000,
                           "必须比页面默认的 8 秒宽，否则放号那波还是全倒在加载上")

    def test_interrupted_navigation_still_retries_and_times_out_eventually(self) -> None:
        page = Mock()
        page.goto.side_effect = RuntimeError("Navigation interrupted by another one")
        with patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                gym_automation.robust_goto(page, "https://example.invalid/x", attempts=3)
        self.assertEqual(page.goto.call_count, 3)


class GymSchedulerRetryPolicyTests(unittest.TestCase):
    def test_scheduler_does_not_start_before_0800(self) -> None:
        self.assertEqual(gym.RUN_EARLIEST, (8, 0))

    def test_pre_submission_network_errors_are_retryable_but_credential_errors_are_not(self) -> None:
        self.assertTrue(gym_automation._retryable_before_submission(
            RuntimeError("navigation timeout while loading venue")))
        self.assertFalse(gym_automation._retryable_before_submission(
            RuntimeError("南大账号或密码不正确")))

    def test_retry_backoff_grows_so_the_last_attempt_misses_the_0800_rush(self) -> None:
        self.assertEqual(gym.JOB_RETRY_DELAYS_SECONDS, (5 * 60, 10 * 60))
        now = datetime(2026, 10, 12, 8, 0, tzinfo=gym.SHANGHAI)

        for attempt, minutes in ((1, 5), (2, 10)):
            with self.subTest(attempt=attempt):
                job = {"id": 90, "result": ({} if attempt == 1 else {"attempt": attempt})}
                with patch.object(gym, "_finish_job") as finish, \
                        patch.object(gym, "datetime") as fake:
                    fake.now.return_value = now
                    self.assertTrue(gym._defer_transient_retry(
                        job, "failed", {"detail": "页面导航超时", "retryable": True}))
                stored = finish.call_args.args[2]
                self.assertEqual(
                    stored["retry_after"],
                    (now + timedelta(minutes=minutes)).isoformat(timespec="seconds"))

    def test_retry_deadline_is_respected(self) -> None:
        now = datetime(2026, 10, 12, 8, 0, tzinfo=gym.SHANGHAI)
        self.assertFalse(gym._retry_is_due(
            {"retry_after": (now + timedelta(minutes=5)).isoformat()}, now))
        self.assertTrue(gym._retry_is_due(
            {"retry_after": (now + timedelta(minutes=5)).isoformat()},
            now + timedelta(minutes=5),
        ))

    def test_no_slot_checks_are_spaced_five_minutes_apart(self) -> None:
        self.assertEqual(gym_automation.NO_SLOT_RECHECK_DELAY_SECONDS, 5 * 60)
        self.assertEqual(gym_automation.NO_SLOT_MAX_CHECKS, 7)

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


class GymSerialExecutionTests(unittest.TestCase):
    """到点任务串行执行，并按创建时间先来先跑。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(gym, "GYM_DB_PATH", Path(self.tmp.name) / "gym.db")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.today = datetime.now(gym.SHANGHAI).date().isoformat()

    def _insert_pending(self, created_at: str) -> int:
        conn = gym.connect()
        try:
            cur = conn.execute(
                "INSERT INTO gym_jobs (target_date, slots, venue, status, created_by,"
                " created_at, updated_at, result)"
                " VALUES (?, ?, ?, 'pending', ?, ?, ?, '{}')",
                (self.today, '["17:00-18:00"]', "129", "someone", created_at, created_at),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _claim_at_9am(self) -> list[dict]:
        # 领取有个 08:00 的门，测试不能依赖运行时刻，把“现在”固定下来。
        fixed_now = datetime(2026, 10, 14, 9, 0, tzinfo=gym.SHANGHAI)
        with patch.object(gym, "datetime") as fake:
            fake.now.return_value = fixed_now
            return gym._claim_due_jobs(self.today)

    def test_due_jobs_are_claimed_earliest_created_first(self) -> None:
        later = self._insert_pending(f"{self.today}T09:30:00+08:00")
        earlier = self._insert_pending(f"{self.today}T09:10:00+08:00")  # id 更大、创建更早
        self.assertGreater(earlier, later, "前提：先插入的那条 id 更小")
        self.assertEqual([j["id"] for j in self._claim_at_9am()], [earlier, later])

    def test_batch_skips_when_another_worker_holds_the_execution_lock(self) -> None:
        with patch.object(gym, "_run_due_jobs") as run, \
                patch.object(gym, "mutex", side_effect=TimeoutError("busy")):
            self.assertEqual(gym._run_scheduled_batch(self.today), -1)
        run.assert_not_called()

    def test_batch_runs_the_due_jobs_when_the_lock_is_free(self) -> None:
        with patch.object(gym, "mutex", return_value=contextlib.nullcontext()), \
                patch.object(gym, "_run_due_jobs", return_value=2) as run:
            self.assertEqual(gym._run_scheduled_batch(self.today), 2)
        run.assert_called_once_with(self.today)

    def test_a_timeout_inside_the_run_is_not_mistaken_for_a_busy_lock(self) -> None:
        with patch.object(gym, "mutex", return_value=contextlib.nullcontext()), \
                patch.object(gym, "_run_due_jobs", side_effect=TimeoutError("site slow")):
            with self.assertRaises(TimeoutError):
                gym._run_scheduled_batch(self.today)


class GymInterruptedJobRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(gym, "GYM_DB_PATH", Path(self.tmp.name) / "gym.db")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _insert_job(self, status: str, updated_at: str, target_date="2026-10-12") -> int:
        conn = gym.connect()
        try:
            cur = conn.execute(
                "INSERT INTO gym_jobs (target_date, slots, venue, status, created_by, "
                "created_at, updated_at, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (target_date, '["17:00-18:00"]', "129", status, "admin01",
                 updated_at, updated_at, "{}"),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def test_stale_running_job_becomes_ambiguous_and_is_not_retried(self) -> None:
        now = datetime(2026, 10, 12, 9, 0, tzinfo=gym.SHANGHAI)
        old = now - timedelta(
            seconds=gym.JOB_SUBPROCESS_TIMEOUT_SECONDS
            + gym.JOB_RUNNING_STALE_GRACE_SECONDS + 1
        )
        job_id = self._insert_job("running", old.isoformat(timespec="seconds"))

        with patch.object(gym, "notify_job_result") as notify:
            recovered = gym._recover_stale_running_jobs(now)

        self.assertEqual(recovered, 1)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[1], "ambiguous")
        conn = gym.connect()
        try:
            row = conn.execute("SELECT status, result FROM gym_jobs WHERE id=?", (job_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "ambiguous")
        self.assertTrue(json.loads(row["result"])["needs_manual_check"])

    def test_ambiguous_date_is_blocked_until_admin_explicitly_resolves_it(self) -> None:
        now = datetime.now(gym.SHANGHAI)
        target_date = now.date().isoformat()
        job_id = self._insert_job("ambiguous", now.isoformat(timespec="seconds"), target_date)
        with patch.object(gym, "credentials_status", return_value={"configured": True}):
            with self.assertRaisesRegex(gym.GymServiceError, "结果待核"):
                gym.create_job(target_date, ["17:00-18:00"], "admin01")

            resolved = gym.resolve_job_for_retry(job_id, "admin01", True)
            self.assertEqual(resolved["status"], "failed")
            self.assertEqual(resolved["result"]["resolved_by"], "admin01")
            new_job = gym.create_job(target_date, ["17:00-18:00"], "admin01")
        self.assertEqual(new_job["status"], "pending")

    def test_same_date_jobs_can_target_different_venues(self) -> None:
        now = datetime.now(gym.SHANGHAI)
        target_date = now.date().isoformat()
        self._insert_job("pending", now.isoformat(timespec="seconds"), target_date)

        with patch.object(gym, "credentials_status", return_value={"configured": True}):
            job = gym.create_job(target_date, ["18:00-19:00"], "admin01", venue="162")

        self.assertEqual(job["venue"], "162")
        self.assertEqual(job["status"], "pending")

    def test_job_rejects_unsupported_venue_id(self) -> None:
        target_date = (datetime.now(gym.SHANGHAI).date() + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(gym.GymServiceError, "支持的一楼或负一楼"):
            gym.create_job(target_date, ["17:00-18:00"], "admin01", venue="999")

    def test_resolution_requires_explicit_no_order_confirmation(self) -> None:
        now = datetime.now(gym.SHANGHAI)
        job_id = self._insert_job("ambiguous", now.isoformat(timespec="seconds"))
        with self.assertRaisesRegex(gym.GymServiceError, "明确确认"):
            gym.resolve_job_for_retry(job_id, "admin01", False)


if __name__ == "__main__":
    unittest.main()
