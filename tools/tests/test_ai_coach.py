import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools import ai_coach
from tools import study_server as server


def context_for(seed: str = "a") -> dict:
    evidence_id = f"evidence:test:{seed}"
    support_ref = "p1"
    return {
        "context_schema_version": "context-v1",
        "task": "learning_diagnosis",
        "snapshot_hash": (seed * 64)[:64] if len(seed) == 1 else "a" * 64,
        "data_as_of": "2026-09-07T12:00:00+08:00",
        "user_request": "",
        "profile": {},
        "summary": {
            "completed_problem_count": 3,
            "active_days": 2,
            "total_ac": 4,
            "total_wa": 5,
        },
        "diagnostic_digest": {
            "version": "diagnostic-digest-v2",
            "overview": {"completed": 3, "active_days_7": 2},
            "review_backlog": {"due_total": 0, "overdue_total": 0, "relearn_total": 0},
            "overdue_distribution": {"due_today": 0},
            "round_distribution": {"round_1": 1, "unknown": 0},
            "representative_cases": [{"ref": support_ref, "case_type": "repeat_wa", "severity": "high", "title": "测试题"}],
            "anomalies": [],
            "coverage": {"source_data_missing": {"tables": [], "schema_incompatible": False}, "context_budget_omitted": {}},
            "data_quality_notes": [],
        },
        "facts": [{"entity_type": "problem", "problem_id": 1, "title": "测试题"}],
        "signals": [
            {
                "signal_id": "signal:test",
                "signal_type": "repeat_wa",
                "evidence_ids": [evidence_id],
            }
        ],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "entity_type": "problem",
                "entity_id": "1",
                "facts": {"wa_count": 3},
            }
        ],
        "trace_map": {
            support_ref: {
                "entity_type": "problem", "entity_id": "1", "label": "测试题",
                "signal_ids": ["signal:test"], "evidence_ids": [evidence_id],
                "metric_ids": ["metric:test:1"],
                "semantic_fact": {"problem_id": 1, "title": "测试题", "wa_count": {"30d": 3}, "ever_ac": False},
            }
        },
        "data_quality": {"status": "ok", "omitted": {}},
        "selection_reasons": [],
        "omitted": {},
        "meta": {"trust_boundaries": {"future_material": "untrusted_data"}},
    }


def valid_result(context: dict) -> dict:
    support_ref = next(iter(context["trace_map"]))
    return {
        "summary": "本次数据显示已有稳定练习基础，建议优先处理重复未通过记录。",
        "strengths": ["已有连续学习记录"],
        "weaknesses": [
            {
                "id": "weakness-1",
                "title": "重复未通过需要复盘",
                "explanation": "同一组学习证据中出现多次未通过，适合先复盘错误原因。",
                "support_refs": [support_ref],
            }
        ],
        "actions": [
            {
                "title": "复盘后重做",
                "description": "先记录错误原因，再独立重做一次并观察结果。",
                "support_refs": [support_ref],
                "weakness_id": "weakness-1",
                "basis": "data",
                "confidence": "medium",
            }
        ],
        "confidence": "medium",
        "data_gaps": [],
    }


class FakeModel:
    def __init__(self, outputs=None, delay=0.0):
        self.outputs = list(outputs or [])
        self.delay = delay
        self.calls = 0
        self.schemas = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, _messages):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if not self.outputs:
            raise AssertionError("fake model ran out of outputs")
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return output


class Provider429(Exception):
    status_code = 429


class Provider500(Exception):
    status_code = 500


class RawMessage:
    def __init__(self, content):
        self.content = content


class StreamChunk:
    def __init__(self, content="", *, reasoning="", usage=None, response_metadata=None):
        self.content = content
        self.additional_kwargs = {"reasoning_content": reasoning} if reasoning else {}
        self.usage_metadata = usage or {}
        self.response_metadata = response_metadata or {}


class AICoachModelTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "AI_ENABLED": "1",
                "AI_PROVIDER": "openai-compatible",
                "AI_MODEL": "test-model",
                "AI_BASE_URL": "https://example.invalid/v1",
                "AI_API_KEY": "test-key-only-in-process",
                "AI_MAX_CONCURRENT_REQUESTS": "1",
                "AI_DAILY_LIMIT_PER_USER": "10",
                "AI_BETA_USERS": "*",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_disabled_and_missing_optional_dependencies_use_safe_fallback(self):
        context = context_for()
        with patch.dict(os.environ, {"AI_ENABLED": "0"}), patch.object(
            ai_coach, "_make_chat_model", side_effect=AssertionError("must not load model")
        ):
            with self.assertRaises(ai_coach.AIServiceError) as raised:
                ai_coach.generate_ai_insight(context)
        self.assertEqual(raised.exception.category, "disabled")
        self.assertEqual(raised.exception.fallback["source"], "rules-v2")

        with patch.object(ai_coach, "_dependencies_available", return_value=False):
            with self.assertRaises(ai_coach.AIServiceError) as raised:
                ai_coach.generate_ai_insight(context)
        self.assertEqual(raised.exception.category, "not_configured")
        self.assertNotIn("test-key", json.dumps(raised.exception.fallback, ensure_ascii=False))

    def test_structured_langchain_output_is_validated_and_uses_pydantic(self):
        context = context_for()
        fake = FakeModel([valid_result(context)])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            result = ai_coach.generate_ai_insight(context)
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(fake.calls, 1)
        self.assertTrue(fake.schemas)
        self.assertTrue(hasattr(fake.schemas[0], "model_validate"))

    def test_raw_chatmodel_fallback_still_has_one_structured_validation_path(self):
        context = context_for()

        class RawOnlyModel:
            def __init__(self):
                self.calls = 0

            def with_structured_output(self, _schema):
                raise NotImplementedError("structured output unavailable")

            def invoke(self, _messages):
                self.calls += 1
                return RawMessage(json.dumps(valid_result(context), ensure_ascii=False))

        fake = RawOnlyModel()
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            result = ai_coach.generate_ai_insight(context)
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(fake.calls, 1)

    def test_deepseek_skips_unsupported_response_format_but_keeps_local_validation(self):
        context = context_for()
        deepseek_result = valid_result(context)
        deepseek_result["weaknesses"][0]["support_refs"] = ["p1"] * 7

        class DeepSeekRawModel:
            def __init__(self):
                self.calls = 0

            def with_structured_output(self, _schema):
                raise AssertionError("DeepSeek must not receive response_format")

            def stream(self, _messages):
                self.calls += 1
                yield StreamChunk(reasoning="内部思考不能进入 JSON")
                yield StreamChunk(json.dumps(deepseek_result, ensure_ascii=False), usage={"input_tokens": 50, "output_tokens": 80})

        fake = DeepSeekRawModel()
        with patch.dict(os.environ, {"AI_BASE_URL": "https://api.deepseek.com"}), patch.object(
            ai_coach, "_dependencies_available", return_value=True
        ), patch.object(ai_coach, "_make_chat_model", return_value=fake):
            result = ai_coach.generate_ai_insight(context)
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(fake.calls, 1)
        self.assertLessEqual(len(result["weaknesses"][0]["support_refs"]), 5)

    def test_deepseek_stream_merges_chunks_times_ttft_and_normalizes_usage(self):
        payload = json.dumps(valid_result(context_for()), ensure_ascii=False)

        class StreamingModel:
            def stream(self, _messages):
                yield StreamChunk(reasoning="不要混入结果")
                yield StreamChunk(payload[:20])
                yield StreamChunk(
                    payload[20:],
                    response_metadata={"token_usage": {
                        "prompt_tokens": 101, "completion_tokens": 44,
                        "completion_tokens_details": {"reasoning_tokens": 17},
                    }},
                )

        with patch.object(ai_coach.time, "perf_counter", side_effect=[10.0, 10.4, 10.6, 11.0, 11.6]):
            raw, metrics = ai_coach._stream_deepseek_once(StreamingModel(), [])
        self.assertEqual(raw.content, payload)
        self.assertNotIn("不要混入结果", raw.content)
        self.assertEqual(metrics["chunk_count"], 3)
        self.assertEqual(metrics["transport_ttft_ms"], 400.0)
        self.assertEqual(metrics["time_to_reasoning_start_ms"], 400.0)
        self.assertEqual(metrics["reasoning_ms"], 200.0)
        self.assertEqual(metrics["time_to_first_content_token_ms"], 600.0)
        self.assertEqual(metrics["unattributed_pre_content_ms"], 200.0)
        self.assertEqual(metrics["reasoning_visibility"], "stream_content")
        self.assertEqual(metrics["ttft_ms"], 600.0)
        self.assertEqual(metrics["content_generation_ms"], 400.0)
        self.assertEqual(metrics["input_tokens"], 101)
        self.assertEqual(metrics["output_tokens"], 44)
        self.assertEqual(metrics["reasoning_tokens"], 17)
        self.assertEqual(metrics["content_tokens"], 27)
        self.assertAlmostEqual(metrics["reasoning_tokens_per_sec"], 85.0, places=3)
        self.assertAlmostEqual(metrics["content_tokens_per_sec"], 67.5, places=3)
        self.assertAlmostEqual(metrics["throughput_tokens_per_sec"], 110.0, places=3)
        self.assertEqual(metrics["reasoning_chunk_count"], 1)
        self.assertEqual(metrics["content_chunk_count"], 2)

    def test_stream_usage_can_be_unavailable_without_fabrication(self):
        class StreamingModel:
            def stream(self, _messages):
                yield StreamChunk("{}")

        raw, metrics = ai_coach._stream_deepseek_once(StreamingModel(), [])
        self.assertEqual(raw.content, "{}")
        self.assertEqual(metrics["usage_status"], "unavailable")
        self.assertNotIn("input_tokens", metrics)
        self.assertIsNone(metrics["throughput_tokens_per_sec"])
        self.assertIsNone(metrics["content_tokens_per_sec"])
        self.assertEqual(metrics["reasoning_visibility"], "unavailable")

    def test_request_config_hash_is_stable_sensitive_free_and_parameter_specific(self):
        config = ai_coach.load_ai_config()
        first, first_hash = ai_coach._request_config_summary(config, native_structured=False)
        second, second_hash = ai_coach._request_config_summary(config, native_structured=False)
        structured, structured_hash = ai_coach._request_config_summary(config, native_structured=True)
        self.assertEqual(first, second)
        self.assertEqual(first_hash, second_hash)
        self.assertNotEqual(first_hash, structured_hash)
        serialized = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("test-key-only-in-process", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("Cookie", serialized)
        self.assertTrue(first["stream"])
        self.assertEqual(structured["response_format"], "native_structured")

    def test_invalid_output_gets_one_repair_call_only(self):
        context = context_for()
        invalid = valid_result(context)
        invalid["weaknesses"][0]["support_refs"] = ["p999"]
        fake = FakeModel([invalid, valid_result(context)])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            result = ai_coach.generate_ai_insight(context)
        self.assertEqual(fake.calls, 2)
        self.assertEqual(result["weaknesses"][0]["support_refs"], ["p1"])

        always_invalid = FakeModel([invalid, invalid, valid_result(context)])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=always_invalid
        ):
            with self.assertRaises(ai_coach.AIServiceError) as raised:
                ai_coach.generate_ai_insight(context)
        self.assertEqual(raised.exception.category, "invalid_output")
        self.assertEqual(always_invalid.calls, 2)

        too_long = "{" + ("x" * 20_001)
        long_model = FakeModel([too_long, too_long])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=long_model
        ):
            with self.assertRaises(ai_coach.AIServiceError) as raised:
                ai_coach.generate_ai_insight(context)
        self.assertEqual(raised.exception.category, "invalid_output")
        self.assertEqual(long_model.calls, 2)

    def test_repair_attempts_have_stable_request_id_and_distinct_attempts(self):
        context = context_for()
        invalid = valid_result(context)
        invalid["weaknesses"][0]["support_refs"] = ["p999"]
        fake = FakeModel([invalid, valid_result(context)])
        events = []
        with patch.object(ai_coach, "debug_ai_event", side_effect=lambda event, **fields: events.append((event, fields))), patch.object(
            ai_coach, "_dependencies_available", return_value=True
        ), patch.object(ai_coach, "_make_chat_model", return_value=fake):
            ai_coach.generate_ai_insight(context, debug_id="task-stable")
        starts = [fields for event, fields in events if event == "model_request_started"]
        self.assertEqual([item["attempt"] for item in starts], [1, 2])
        self.assertEqual({item["request_id"] for item in starts}, {"task-stable"})
        self.assertEqual([item["repair"] for item in starts], [False, True])

    def test_provider_errors_are_classified_without_raw_details(self):
        context = context_for()
        for exception, category in (
            (TimeoutError("secret endpoint"), "timeout"),
            (Provider429("raw provider detail"), "rate_limited"),
            (Provider500("raw provider detail"), "provider_error"),
        ):
            fake = FakeModel([exception])
            with self.subTest(category=category), patch.object(
                ai_coach, "_dependencies_available", return_value=True
            ), patch.object(ai_coach, "_make_chat_model", return_value=fake):
                with self.assertRaises(ai_coach.AIServiceError) as raised:
                    ai_coach.generate_ai_insight(context)
            self.assertEqual(raised.exception.category, category)
            self.assertNotIn("raw provider detail", raised.exception.user_message)
            self.assertNotIn("secret endpoint", raised.exception.user_message)

    def test_evidence_and_pydantic_bounds_reject_bad_payloads(self):
        context = context_for()
        cases = []
        missing_evidence = valid_result(context)
        missing_evidence["weaknesses"][0]["support_refs"] = []
        cases.append(missing_evidence)
        unknown_field = valid_result(context)
        unknown_field["surprise"] = "x"
        cases.append(unknown_field)
        too_many_actions = valid_result(context)
        too_many_actions["actions"] = [valid_result(context)["actions"][0]] * 7
        cases.append(too_many_actions)
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises((ValueError, ai_coach._InvalidAIOutput)):
                    ai_coach.validate_insight_payload(payload, context)

    def test_xss_strings_remain_plain_validated_text(self):
        context = context_for()
        payload = valid_result(context)
        payload["summary"] = '<img src=x onerror="alert(1)">'
        result = ai_coach.validate_insight_payload(payload, context)
        self.assertEqual(result["summary"], payload["summary"])

    def test_action_basis_and_confidence_are_strict_and_data_actions_need_evidence(self):
        context = context_for()
        heuristic = valid_result(context)
        heuristic["actions"][0] = {
            "title": "保持固定节奏",
            "description": "这是不依赖当前数据的通用建议。",
            "support_refs": [],
            "weakness_id": "",
            "basis": "heuristic",
            "confidence": "low",
        }
        result = ai_coach.validate_insight_payload(heuristic, context)
        self.assertEqual(result["actions"][0]["basis"], "heuristic")
        missing = valid_result(context)
        missing["actions"][0]["support_refs"] = []
        missing["actions"][0]["basis"] = "data"
        with self.assertRaises(ai_coach._InvalidAIOutput):
            ai_coach.validate_insight_payload(missing, context)

    def test_model_projection_is_smaller_and_separates_source_distribution(self):
        context = context_for()
        context["summary"]["submission_source_distribution"] = {"sync": 100}
        context["diagnostic_digest"] = {
            "version": "diagnostic-digest-v1",
            "overview": {"completed": 3},
            "coverage": {"source_data_missing": {"tables": []}, "context_budget_omitted": {}},
        }
        context["facts"] = [
            {
                "entity_type": "problem",
                "problem_id": index,
                "title": "代表题目",
                "metric_ids": {"metric": "metric:analytics-v1:problem:1:wa_count:30d"},
                "confidence_reason": "冗余完整事实",
            }
            for index in range(1, 12)
        ]
        context["selection_reasons"] = [{"item_id": "fact:1"}] * 20
        context["omitted"] = {"facts": 20, "signals": 10}
        context["meta"] = {"trust_boundaries": {"future_material": "untrusted_data"}}
        full_chars = len(json.dumps(context, ensure_ascii=False, separators=(",", ":")))
        projected = ai_coach._context_json(context)
        self.assertLess(len(projected), full_chars)
        self.assertIn("diagnostic_digest", projected)
        self.assertIn("learning-diagnosis-context-v2", projected)
        self.assertNotIn("submission_source_distribution", projected)
        for token in ("metric:", "evidence:", "signal:", "trace_map", "selection_reasons"):
            self.assertNotIn(token, projected)

    def test_llm_context_v2_prunes_empty_values_and_aligns_dynamic_compact_facts(self):
        context = context_for()
        context["profile"] = {"learning_goal": "", "available_minutes": 0}
        projection = ai_coach._build_llm_context(context)
        self.assertEqual(projection["llm_context_version"], "learning-diagnosis-context-v2")
        self.assertNotIn("summary", projection)
        self.assertEqual(projection["profile"], {"available_minutes": 0})
        case_refs = {item["ref"] for item in projection["diagnostic_digest"]["representative_cases"]}
        fact_refs = {item["ref"] for item in projection["compact_facts"]}
        self.assertEqual(case_refs, fact_refs)
        fact = projection["compact_facts"][0]
        self.assertIn("wa_count", fact)
        self.assertNotIn("overdue_days", fact)
        self.assertFalse(projection["coverage"]["source_missing"])
        context["diagnostic_digest"]["coverage"]["source_data_missing"]["tables"] = ["submissions"]
        context["diagnostic_digest"]["coverage"]["context_budget_omitted"] = {"facts": 10}
        coverage = ai_coach._build_llm_context(context)["coverage"]
        self.assertTrue(coverage["source_missing"])
        self.assertTrue(coverage["details_sampled"])
        self.assertNotIn("facts", coverage)

    def test_support_refs_resolve_internally_but_public_result_only_has_labels(self):
        context = context_for()
        payload = valid_result(context)
        payload["actions"][0]["description"] = "请复盘 p1，不要展示短引用。"
        result = ai_coach.validate_insight_payload(payload, context)
        self.assertEqual(result["_support_trace"]["p1"]["evidence_ids"], ["evidence:test:a"])
        public = ai_coach._public_insight(result, context)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["weaknesses"][0]["support_labels"], ["测试题"])
        self.assertIn("请复盘 测试题", public["actions"][0]["description"])
        for token in ("p1", "evidence:", "signal:", "metric:", "support_refs"):
            self.assertNotIn(token, serialized)

    def test_raw_debug_contract_redacts_internal_machine_ids(self):
        safe = ai_coach._safe_raw_log({"support_refs": ["p1"]})
        blocked = ai_coach._safe_raw_log({"support_refs": ["evidence:test:a"]})
        self.assertEqual(safe, {"support_refs": ["p1"]})
        self.assertTrue(blocked["redacted"])

    def test_debug_model_prepared_has_hashes_counts_and_non_sensitive_sections(self):
        context = context_for()
        fake = FakeModel([valid_result(context)])
        events = []
        with patch.object(ai_coach, "debug_ai_event", side_effect=lambda event, **fields: events.append((event, fields))), patch.object(
            ai_coach, "_dependencies_available", return_value=True
        ), patch.object(ai_coach, "_make_chat_model", return_value=fake):
            ai_coach.generate_ai_insight(context, debug_id="debug-test")
        prepared = next(fields for event, fields in events if event == "model_prepared")
        self.assertGreater(prepared["final_context_chars"], 0)
        self.assertGreater(prepared["estimated_tokens"], 0)
        self.assertIn("compact_facts", prepared["included_sections"])
        self.assertEqual(prepared["llm_context_version"], ai_coach.LLM_CONTEXT_VERSION)
        self.assertRegex(prepared["prompt_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(prepared["context_hash"], r"^[0-9a-f]{64}$")
        self.assertIn("selection_reasons", prepared["sections_not_sent"])
        self.assertNotIn("test-key", json.dumps(prepared, ensure_ascii=False))


class AICoachPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "user" / "hot100-study.db"
        self.db.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.db)
        connection.executescript(server.SCHEMA)
        connection.commit()
        connection.close()
        self.env = patch.dict(
            os.environ,
            {
                "AI_ENABLED": "1",
                "AI_PROVIDER": "openai-compatible",
                "AI_MODEL": "test-model",
                "AI_API_KEY": "test-key-only-in-process",
                "AI_MAX_CONCURRENT_REQUESTS": "1",
                "AI_DAILY_LIMIT_PER_USER": "2",
                "AI_BETA_USERS": "alice",
            },
            clear=False,
        )
        self.env.start()
        ai_coach.reset_ai_runtime_for_tests()

    def tearDown(self):
        ai_coach.reset_ai_runtime_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def wait_for(self, task_id, expected=None):
        deadline = time.time() + 8
        while time.time() < deadline:
            task = ai_coach.get_ai_task(self.db, task_id)
            if task and (expected is None or task["status"] in expected):
                return task
            time.sleep(0.05)
        self.fail(f"task did not finish: {task_id}")

    def test_task_migration_success_cache_reuse_and_feedback(self):
        context = context_for()
        fake = FakeModel([valid_result(context)])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            created = ai_coach.create_ai_task(self.db, context, "alice", "user")
            finished = self.wait_for(created["task_id"], {"succeeded", "failed"})
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(fake.calls, 1)
        self.assertTrue(finished["insight_id"])
        with patch.object(ai_coach, "_dependencies_available", return_value=True):
            reused = ai_coach.create_ai_task(self.db, context, "alice", "user")
        self.assertTrue(reused["reused"])
        self.assertEqual(reused["task_id"], created["task_id"])
        self.assertEqual(fake.calls, 1)
        feedback = ai_coach.submit_ai_feedback(self.db, finished["insight_id"], True)
        self.assertEqual(feedback["helpful"], True)

        connection = sqlite3.connect(self.db)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_%'"
                )
            }
        finally:
            connection.close()
        self.assertEqual(tables, {"ai_tasks", "ai_insights", "ai_daily_quota"})

    def test_restart_recovery_cancel_and_running_cannot_be_falsely_cancelled(self):
        context = context_for()
        now = ai_coach._now_iso()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """INSERT INTO ai_tasks(
                   task_id, task, status, snapshot_hash, prompt_version, model_key,
                   created_at, context_preview, fallback_json
                ) VALUES (?, 'learning_diagnosis', 'queued', ?, ?, ?, ?, ?, ?)""",
                (
                    "1" * 32,
                    context["snapshot_hash"],
                    ai_coach.PROMPT_VERSION,
                    "openai-compatible:model-test",
                    now,
                    json.dumps(context, ensure_ascii=False),
                    json.dumps(ai_coach.build_rule_fallback(context), ensure_ascii=False),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        changed = ai_coach.recover_ai_tasks(self.db)
        self.assertEqual(changed, 1)
        recovered = ai_coach.get_ai_task(self.db, "1" * 32)
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["error_category"], "cancelled")

        # Keep a new task queued without starting a worker so cancellation is
        # deterministic and does not rely on timing.
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_ensure_workers", return_value=None
        ), patch.object(ai_coach._AI_QUEUE, "put_nowait", return_value=None):
            created = ai_coach.create_ai_task(self.db, context_for("b"), "alice", "user")
        cancelled = ai_coach.cancel_ai_task(self.db, created["task_id"])
        self.assertEqual(cancelled["status"], "cancelled")

        running_id = "2" * 32
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """INSERT INTO ai_tasks(
                   task_id, task, status, snapshot_hash, prompt_version, model_key,
                   created_at, started_at, context_preview, fallback_json
                ) VALUES (?, 'learning_diagnosis', 'running', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    running_id,
                    "c" * 64,
                    ai_coach.PROMPT_VERSION,
                    "openai-compatible:model-test",
                    now,
                    now,
                    json.dumps(context, ensure_ascii=False),
                    json.dumps(ai_coach.build_rule_fallback(context), ensure_ascii=False),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(ai_coach.AIServiceError) as raised:
            ai_coach.cancel_ai_task(self.db, running_id)
        self.assertEqual(raised.exception.status, 409)

    def test_partial_ai_table_migration_is_idempotent(self):
        old_db = Path(self.temp_dir.name) / "old" / "hot100-study.db"
        old_db.parent.mkdir(parents=True)
        connection = sqlite3.connect(old_db)
        try:
            connection.execute(
                """CREATE TABLE ai_tasks(
                   task_id TEXT PRIMARY KEY, task TEXT, status TEXT,
                   snapshot_hash TEXT, prompt_version TEXT, model_key TEXT,
                   created_at TEXT, context_preview TEXT, result_json TEXT
                )"""
            )
            connection.commit()
        finally:
            connection.close()
        connection = sqlite3.connect(old_db)
        try:
            ai_coach.ensure_ai_schema(connection)
            ai_coach.ensure_ai_schema(connection)
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(ai_tasks)").fetchall()
            }
        finally:
            connection.close()
        self.assertTrue({"started_at", "finished_at", "worker_id", "fallback_json", "insight_id"}.issubset(columns))

    def test_old_insight_result_without_action_metadata_is_still_readable(self):
        context = context_for()
        old_result = valid_result(context)
        old_result["actions"][0].pop("basis")
        old_result["actions"][0].pop("confidence")
        task_id = "3" * 32
        now = ai_coach._now_iso()
        connection = sqlite3.connect(self.db)
        try:
            ai_coach.ensure_ai_schema(connection)
            connection.execute(
                """INSERT INTO ai_tasks(
                   task_id, task, status, snapshot_hash, prompt_version, model_key,
                   created_at, finished_at, context_preview, result_json, fallback_json
                ) VALUES (?, 'learning_diagnosis', 'succeeded', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    context["snapshot_hash"],
                    "coach-analysis-v1",
                    "openai-compatible:model-old",
                    now,
                    now,
                    json.dumps(context, ensure_ascii=False),
                    json.dumps(old_result, ensure_ascii=False),
                    json.dumps(ai_coach.build_rule_fallback(context), ensure_ascii=False),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        current = ai_coach.get_ai_task(self.db, task_id)
        self.assertEqual(current["status"], "succeeded")
        self.assertNotIn("basis", current["result"]["actions"][0])
        public_json = json.dumps(current, ensure_ascii=False)
        self.assertNotIn("evidence:", public_json)
        self.assertNotIn("trace_map", public_json)
        self.assertNotIn("support_refs", public_json)

    def test_global_worker_limit_is_one_even_for_two_queued_users(self):
        first_context = context_for("d")
        second_context = context_for("e")

        class CountingModel:
            def __init__(self):
                self.active = 0
                self.maximum = 0
                self.lock = threading.Lock()

            def with_structured_output(self, _schema):
                return self

            def invoke(self, _messages):
                with self.lock:
                    self.active += 1
                    self.maximum = max(self.maximum, self.active)
                time.sleep(0.12)
                with self.lock:
                    self.active -= 1
                return {
                    "summary": "继续积累记录。", "strengths": [], "weaknesses": [],
                    "actions": [], "confidence": "low", "data_gaps": [],
                }

        fake = CountingModel()
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            first = ai_coach.create_ai_task(self.db, first_context, "alice", "user")
            second = ai_coach.create_ai_task(self.db, second_context, "alice", "user")
            self.assertEqual(self.wait_for(first["task_id"], {"succeeded", "failed"})["status"], "succeeded")
            self.assertEqual(self.wait_for(second["task_id"], {"succeeded", "failed"})["status"], "succeeded")
        self.assertEqual(fake.maximum, 1)

    def test_daily_quota_and_cross_user_isolation(self):
        context = context_for()
        fake = FakeModel([valid_result(context)])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            first = ai_coach.create_ai_task(self.db, context, "alice", "user")
            finished = self.wait_for(first["task_id"], {"succeeded", "failed"})
        other_db = Path(self.temp_dir.name) / "other" / "hot100-study.db"
        other_db.parent.mkdir(parents=True)
        other_connection = sqlite3.connect(other_db)
        try:
            other_connection.executescript(server.SCHEMA)
            other_connection.commit()
        finally:
            other_connection.close()
        self.assertIsNone(ai_coach.get_ai_task(other_db, first["task_id"]))
        self.assertEqual(ai_coach.get_ai_quota(self.db)["used"], 1)
        self.assertEqual(ai_coach.get_ai_quota(other_db)["used"], 0)
        with self.assertRaises(ai_coach.AIServiceError) as raised:
            ai_coach.submit_ai_feedback(other_db, finished["insight_id"], True)
        self.assertEqual(raised.exception.status, 404)

        second_context = context_for("b")
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=FakeModel([valid_result(second_context)])
        ):
            second = ai_coach.create_ai_task(self.db, second_context, "alice", "user")
            self.wait_for(second["task_id"], {"succeeded", "failed"})
        third_context = context_for("c")
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=FakeModel([valid_result(third_context)])
        ):
            third = ai_coach.create_ai_task(self.db, third_context, "alice", "user")
            self.wait_for(third["task_id"], {"succeeded", "failed"})
        with patch.object(ai_coach, "_dependencies_available", return_value=True):
            with self.assertRaises(ai_coach.AIServiceError) as raised:
                ai_coach.create_ai_task(self.db, context_for("d"), "alice", "user")
        self.assertEqual(raised.exception.category, "quota")
        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(raised.exception.details["quota"]["remaining"], 0)


class AIDailyQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "user" / "hot100-study.db"
        self.db.parent.mkdir(parents=True)
        with ai_coach.closing(sqlite3.connect(self.db)) as connection:
            connection.executescript(server.SCHEMA)
        ai_coach.reset_ai_runtime_for_tests()

    def tearDown(self):
        ai_coach.reset_ai_runtime_for_tests()
        self.temp_dir.cleanup()

    def test_atomic_reservations_allow_three_and_reject_fourth(self):
        with ai_coach.closing(ai_coach._open_ai_db(self.db)):
            pass
        barrier = threading.Barrier(4)
        outcomes = []
        lock = threading.Lock()

        def reserve(index):
            task_id = f"{index:032x}"
            try:
                barrier.wait(timeout=2)
                with ai_coach.closing(ai_coach._open_ai_db(self.db)) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        """INSERT INTO ai_tasks(task_id, task, status, snapshot_hash, prompt_version,
                           model_key, created_at, context_preview, fallback_json)
                           VALUES (?, 'learning_diagnosis', 'queued', ?, 'p', 'm', ?, '{}', '{}')""",
                        (task_id, "a" * 64, ai_coach._now_iso()),
                    )
                    ai_coach._reserve_ai_quota(connection, task_id)
                    connection.execute("COMMIT")
                value = "allowed"
            except ai_coach.AIServiceError:
                value = "quota"
            with lock:
                outcomes.append(value)

        threads = [threading.Thread(target=reserve, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(outcomes.count("allowed"), 3)
        self.assertEqual(outcomes.count("quota"), 1)
        quota = ai_coach.get_ai_quota(self.db)
        self.assertEqual(quota["remaining"], 0)
        self.assertEqual(quota["used"], 0)

    def test_shanghai_midnight_starts_a_new_window(self):
        before = datetime(2026, 9, 8, 15, 59, tzinfo=timezone.utc)
        after = before + timedelta(minutes=2)
        old_day, old_reset = ai_coach._quota_window(before)
        new_day, _ = ai_coach._quota_window(after)
        self.assertEqual(old_day, "2026-09-08")
        self.assertEqual(new_day, "2026-09-09")
        self.assertTrue(old_reset.startswith("2026-09-09T00:00:00+08:00"))
        with ai_coach.closing(ai_coach._open_ai_db(self.db)) as connection:
            connection.execute(
                "INSERT INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 3, 0, ?)",
                (old_day, ai_coach._now_iso()),
            )
            connection.commit()
        self.assertEqual(ai_coach.get_ai_quota(self.db, now=before)["remaining"], 0)
        self.assertEqual(ai_coach.get_ai_quota(self.db, now=after)["remaining"], 3)

    def test_admin_reset_clears_consumed_but_keeps_pending_reservations(self):
        day_key, _ = ai_coach._quota_window()
        with ai_coach.closing(ai_coach._open_ai_db(self.db)) as connection:
            connection.execute(
                "INSERT INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 2, 1, ?)",
                (day_key, ai_coach._now_iso()),
            )
            connection.commit()
        result = ai_coach.reset_ai_quota(self.db)
        self.assertEqual(result["before_used"], 2)
        self.assertEqual(result["quota"], {
            "limit": 3, "used": 0, "remaining": 2, "reset_at": result["quota"]["reset_at"]
        })

    def test_recent_history_is_bounded_safe_and_read_only(self):
        context = context_for("history")
        result = {"summary": "历史摘要", "strengths": [], "weaknesses": [], "actions": [],
                  "confidence": "low", "data_gaps": []}
        fallback = {"source": "rules-v2", "result": result}
        with ai_coach.closing(ai_coach._open_ai_db(self.db)) as connection:
            for index in range(11):
                connection.execute(
                    """INSERT INTO ai_tasks(task_id, task, status, snapshot_hash, prompt_version,
                       model_key, created_at, context_preview, result_json, fallback_json, insight_id)
                       VALUES (?, 'learning_diagnosis', ?, ?, 'p', 'm', ?, ?, ?, ?, ?)""",
                    (f"{index:032x}", "succeeded" if index % 3 else "failed", f"{index:064x}",
                     f"2026-09-08T{index:02d}:00:00+08:00", json.dumps(context, ensure_ascii=False),
                     json.dumps(result, ensure_ascii=False) if index % 3 else None,
                     json.dumps(fallback, ensure_ascii=False), f"{index + 20:032x}"))
            connection.commit()
        quota_before = ai_coach.get_ai_quota(self.db)
        history = ai_coach.get_recent_ai_tasks(self.db, "alice", "user")
        self.assertEqual(len(history["items"]), 10)
        self.assertTrue(history["items"][0]["is_latest"])
        self.assertFalse(any(item["is_latest"] for item in history["items"][1:]))
        encoded = json.dumps(history["items"], ensure_ascii=False)
        for forbidden in ("context_preview", "trace_map", "raw_output", "snapshot_hash", "model_key", "prompt_version"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(ai_coach.get_ai_quota(self.db), quota_before)

    def test_provider_failure_consumes_but_local_preflight_failure_releases(self):
        env = patch.dict(os.environ, {
            "AI_ENABLED": "1", "AI_PROVIDER": "openai-compatible", "AI_MODEL": "test-model",
            "AI_API_KEY": "test-key", "AI_BETA_USERS": "alice",
        }, clear=False)
        env.start()
        try:
            local_error = ai_coach.AIServiceError("not_configured", "local")
            with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
                ai_coach, "_make_chat_model", side_effect=local_error
            ):
                task = ai_coach.create_ai_task(self.db, context_for("e"), "alice", "user")
                deadline = time.time() + 4
                while time.time() < deadline and ai_coach.get_ai_task(self.db, task["task_id"])["status"] not in {"failed", "succeeded"}:
                    time.sleep(.02)
            self.assertEqual(ai_coach.get_ai_quota(self.db)["used"], 0)
            self.assertEqual(ai_coach.get_ai_quota(self.db)["remaining"], 3)

            failing = FakeModel([TimeoutError("provider timeout")])
            with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
                ai_coach, "_make_chat_model", return_value=failing
            ):
                task = ai_coach.create_ai_task(self.db, context_for("f"), "alice", "user")
                deadline = time.time() + 4
                while time.time() < deadline and ai_coach.get_ai_task(self.db, task["task_id"])["status"] not in {"failed", "succeeded"}:
                    time.sleep(.02)
            quota = ai_coach.get_ai_quota(self.db)
            self.assertEqual(quota["used"], 1)
            self.assertEqual(quota["remaining"], 2)
        finally:
            env.stop()


class AICoachPageContractTests(unittest.TestCase):
    def test_page_uses_server_capability_and_safe_text_rendering(self):
        page = Path(__file__).resolve().parents[2] / "cockpit.html"
        text = page.read_text(encoding="utf-8")
        self.assertIn("/api/coach/analyze", text)
        self.assertIn("/api/coach/insights/recent", text)
        self.assertIn("一键学习情况分析", text)
        self.assertIn("依据类型：", text)
        self.assertIn("旧结果未标注", text)
        self.assertIn("textContent", text)
        self.assertIn("@media(max-width:720px)", text)
        self.assertIn("html[data-theme=\"dark\"]", text)
        recent_start = text.index("function loadAiRecent")
        recent_end = text.index("function startAiAnalysis", recent_start)
        self.assertNotIn("/api/coach/analyze", text[recent_start:recent_end])
        # The AI renderer is required to use textContent.  The existing clock
        # has a separate static colon markup; no AI result is assigned with
        # innerHTML.
        ai_start = text.index("function renderAi")
        ai_end = text.index("function loadAi", ai_start)
        self.assertNotIn("innerHTML", text[ai_start:ai_end])

    def test_waiting_animation_and_quota_contract(self):
        page = (Path(__file__).resolve().parents[2] / "cockpit.html").read_text(encoding="utf-8")
        for text in ("正在读取学习数据", "正在比对学习进度", "正在拼接上下文", "正在调用大模型", "正在定制学习方案"):
            self.assertIn(text, page)
        self.assertIn("prefers-reduced-motion:reduce", page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn("startAiWaiting", page)
        self.assertIn("finishAiWaiting", page)
        self.assertIn("stopAiWaiting", page)
        self.assertIn('window.addEventListener("pagehide", stopAiWaiting)', page)
        self.assertIn("今日剩余 ", page)
        ai_start = page.index("var aiCapability")
        ai_end = page.index('document.querySelectorAll("[data-ai-feedback]")', ai_start)
        wait_logic = page[ai_start:ai_end]
        self.assertIn("AI_WAIT_MIN_MS = 2800", wait_logic)
        self.assertIn("AI_WAIT_CAP = 97", wait_logic)
        self.assertIn("Math.min(AI_WAIT_CAP", wait_logic)
        self.assertIn("elapsed >= AI_WAIT_MIN_MS", wait_logic)
        self.assertIn("aiWaitProgress >= 99.7", wait_logic)
        self.assertIn('state === "succeeded" && aiWaitTimer', wait_logic)
        self.assertIn("clearTimeout(aiWaitTimer)", wait_logic)
        self.assertNotIn("setInterval", wait_logic)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', wait_logic)
        self.assertIn('aria-valuenow', page)

    def test_collapsible_history_mode_contract(self):
        page = (Path(__file__).resolve().parents[2] / "cockpit.html").read_text(encoding="utf-8")
        ids = re.findall(r'\bid="([^"]+)"', page)
        self.assertEqual(len(ids), len(set(ids)))
        for text in ('id="ai-collapse"', 'aria-controls="ai-body"', 'aria-expanded="true"',
                     "forge-ai-card-collapsed", "setAiCollapsed", "restoreAiCollapsed",
                     "最近 10 次分析", "正在查看 ", "返回最新分析"):
            self.assertIn(text, page)
        collapse_start = page.index("function setAiCollapsed")
        poll_start = page.index("function pollAiTask")
        poll_end = page.index("function loadAiRecent", poll_start)
        self.assertNotIn("clearTimeout(aiPollTimer)", page[collapse_start:poll_start])
        self.assertIn("pollAiTask", page[poll_start:poll_end])
        history_start = page.index("function showAiHistory")
        history_end = page.index("function returnToLatestAi", history_start)
        self.assertNotIn("/api/coach/analyze", page[history_start:history_end])
        start_start = page.index("function startAiAnalysis")
        start_end = page.index("function applyAiCapability", start_start)
        self.assertLess(page.index("returnToLatestAi", start_start, start_end),
                        page.index('/api/coach/analyze', start_start, start_end))


class AICoachHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "site"
        self.users_dir = self.root / "data" / "users"
        self.default_db = self.root / "data" / "default.db"
        self.users = {
            "token-a": {"id": 1, "username": "alice", "role": "user", "nickname": "alice", "lang": "java"},
            "token-admin": {"id": 2, "username": "rootadmin", "role": "admin", "nickname": "rootadmin", "lang": "java"},
            "token-b": {"id": 3, "username": "bob", "role": "user", "nickname": "bob", "lang": "java"},
        }
        self.patches = [
            patch.object(server, "ROOT", self.root),
            patch.object(server, "USERS_DIR", self.users_dir),
            patch.object(server, "DB_PATH", self.default_db),
            patch.object(server, "PROBLEM_BY_ID", {1: {"id": 1, "title": "题目一", "category": "数组", "difficulty": "简单"}}),
            patch.object(server, "load_library_manifest", return_value={"modules": [], "routes": {}}),
            patch.object(server, "session_user", side_effect=lambda token: self.users.get(token)),
            patch.object(server, "QUIET", True),
        ]
        for item in self.patches:
            item.start()
        server._SCHEMA_DONE.clear()
        with server._ANALYTICS_CACHE_LOCK:
            server._ANALYTICS_CACHE.clear()
            server._ANALYTICS_CACHE_GENERATIONS.clear()
            server._ANALYTICS_GENERATION_TOUCHED.clear()
            server._ANALYTICS_CACHE_ACTIVE.clear()
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE.clear()
            server._DASH_CACHE_GENERATIONS.clear()
        self.env = patch.dict(
            os.environ,
            {
                "AI_ENABLED": "0",
                "AI_PROVIDER": "",
                "AI_MODEL": "",
                "AI_API_KEY": "",
                "AI_BETA_USERS": "",
            },
            clear=False,
        )
        self.env.start()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        ai_coach.reset_ai_runtime_for_tests()
        server._SCHEMA_DONE.clear()
        self.env.stop()
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def user_db(self, username):
        return self.users_dir / username / "hot100-study.db"

    def request(self, path, token="token-a", payload=None):
        body = None
        headers = {}
        if token:
            headers["Cookie"] = f"{server.SESSION_COOKIE}={token}"
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
            data=body,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def prepare_user_db(self, username="alice"):
        path = self.user_db(username)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.executescript(server.SCHEMA)
            connection.commit()
        finally:
            connection.close()
        return path

    def test_auth_capability_and_disabled_rule_fallback(self):
        self.prepare_user_db()
        status, body = self.request("/api/coach/insights/recent", token=None)
        self.assertEqual(status, 401)
        status, body = self.request("/api/coach/analyze", payload={"model": "not-client-controlled"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "请求参数不正确")
        self.assertNotIn("not-client-controlled", json.dumps(body, ensure_ascii=False))

        status, body = self.request("/api/coach/analyze", payload={})
        self.assertEqual(status, 503)
        self.assertEqual(body["error_category"], "disabled")
        self.assertEqual(body["fallback"]["source"], "rules-v2")
        self.assertNotIn("AI_API_KEY", json.dumps(body, ensure_ascii=False))

        status, body = self.request("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertFalse(body["capabilities"]["ai_coach"]["can_analyze"])
        quota = body["capabilities"]["ai_coach"]["quota"]
        self.assertEqual(set(quota), {"limit", "used", "remaining", "reset_at"})
        self.assertEqual((quota["limit"], quota["used"], quota["remaining"]), (3, 0, 3))

    def test_quota_error_is_http_429_with_structured_quota(self):
        self.prepare_user_db()
        error = ai_coach.AIServiceError(
            "quota", "今天的一键分析次数已用完，请明天再试。",
            status=429,
            details={"quota": {"limit": 3, "used": 3, "remaining": 0, "reset_at": "2026-09-09T00:00:00+08:00"}},
        )
        with patch.object(server, "create_ai_task", side_effect=error):
            status, body = self.request("/api/coach/analyze", payload={})
        self.assertEqual(status, 429)
        self.assertEqual(body["error_category"], "quota")
        self.assertEqual(body["quota"]["remaining"], 0)

    def test_non_beta_is_hidden_and_admin_capability_is_separate(self):
        self.prepare_user_db("alice")
        self.env.stop()
        self.env = patch.dict(
            os.environ,
            {
                "AI_ENABLED": "1",
                "AI_PROVIDER": "openai-compatible",
                "AI_MODEL": "test-model",
                "AI_API_KEY": "test-key-only-in-process",
                "AI_BETA_USERS": "",
            },
            clear=False,
        )
        self.env.start()
        with patch.object(ai_coach, "_dependencies_available", return_value=True):
            status, body = self.request("/api/coach/capability", token="token-a")
            self.assertEqual(status, 200)
            self.assertEqual(body["ai_coach"]["status"], "not_allowed")
            self.assertFalse(body["ai_coach"]["visible"])
            status, body = self.request("/api/coach/analyze", token="token-a", payload={})
            self.assertEqual(status, 403)
            self.assertEqual(body["error_category"], "not_allowed")

            self.prepare_user_db("rootadmin")
            status, body = self.request("/api/coach/capability", token="token-admin")
            self.assertEqual(status, 200)
            self.assertTrue(body["ai_coach"]["allowed"])

    def test_enabled_fake_model_creates_task_and_other_user_cannot_read_it(self):
        self.prepare_user_db("alice")
        self.prepare_user_db("bob")
        self.env.stop()
        self.env = patch.dict(
            os.environ,
            {
                "AI_ENABLED": "1",
                "AI_PROVIDER": "openai-compatible",
                "AI_MODEL": "test-model",
                "AI_API_KEY": "test-key-only-in-process",
                "AI_BETA_USERS": "alice",
            },
            clear=False,
        )
        self.env.start()
        empty_result = {
            "summary": "数据较少，建议继续学习并记录结果。",
            "strengths": [], "weaknesses": [], "actions": [],
            "confidence": "low", "data_gaps": ["当前数据量有限"],
        }
        fake = FakeModel([empty_result])
        with patch.object(ai_coach, "_dependencies_available", return_value=True), patch.object(
            ai_coach, "_make_chat_model", return_value=fake
        ):
            status, body = self.request("/api/coach/analyze", token="token-a", payload={})
            self.assertEqual(status, 201, body)
            self.assertRegex(body["task_id"], r"^[0-9a-f]{32}$")
            task_id = body["task_id"]
            deadline = time.time() + 8
            while time.time() < deadline:
                status, current = self.request("/api/coach/tasks/" + task_id, token="token-a")
                if current.get("status") in {"succeeded", "failed"}:
                    break
                time.sleep(0.05)
            self.assertEqual(current["status"], "succeeded")
            self.assertEqual(current["result"]["confidence"], "low")
            self.assertEqual(fake.calls, 1)

        status, body = self.request("/api/coach/tasks/" + task_id, token="token-b")
        self.assertEqual(status, 404)
        status, body = self.request("/api/coach/insights/recent", token="token-b")
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [])
