import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "deepseek_reasoning_benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark_deepseek_reasoning", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class DeepSeekBenchmarkTests(unittest.TestCase):
    def test_nearest_rank_and_aggregation(self):
        samples = [
            {"timing": {"model_total_ms": value}, "validation": {"succeeded": value != 3, "failure_category": "schema" if value == 3 else None}}
            for value in (1, 2, 3, 4, 5)
        ]
        result = benchmark.aggregate_group(samples)
        self.assertEqual(result["metrics"]["model_total_ms"], {"min": 1.0, "median": 3.0, "mean": 3.0, "p90": 5.0, "max": 5.0})
        self.assertEqual(result["validation_success_rate"], 0.8)
        self.assertEqual(result["failure_categories"], {"schema": 1})

    def test_slot_is_single_call_without_repair_and_keeps_context_fixed(self):
        context = {"trace_map": {"p1": {"label": "题目"}}}
        payload = {
            "summary": "总结", "strengths": [],
            "weaknesses": [{"id": "w1", "title": "复习", "explanation": "说明", "support_refs": ["p1"]}],
            "actions": [{"title": "复习", "description": "执行", "support_refs": ["p1"], "weakness_id": "w1", "basis": "data", "confidence": "high"}],
            "confidence": "high", "data_gaps": [],
        }
        raw = benchmark.ai_coach._StreamEnvelope(benchmark.canonical_json(payload), {})
        timing = {"model_total_ms": 1}
        config = benchmark.ai_coach.AIConfig(True, "openai-compatible", "deepseek-v4-flash", "https://api.deepseek.com", "secret", "chat_completions", "", "high", True, 120, 2, 10, "*")
        with patch.object(benchmark.ai_coach, "_make_chat_model", return_value=object()) as make, patch.object(
            benchmark.ai_coach, "_stream_deepseek_once", return_value=(raw, timing)
        ) as stream, patch.object(benchmark.ai_coach, "debug_ai_event"):
            sample = benchmark.run_slot(
                benchmark_id="bench", slot=2, group="B", context=context,
                context_json='{"fixed":true}', context_hash="same", config=config,
            )
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(make.call_args.kwargs["thinking_mode"], "disabled")
        self.assertTrue(sample["validation"]["succeeded"])
        self.assertEqual(sample["context_hash"], "same")

    def test_quality_summary_is_deterministic(self):
        payload = {
            "summary": "复习积压", "strengths": ["完成较多"],
            "weaknesses": [{"title": "逾期复习", "support_refs": ["p1"]}],
            "actions": [{"title": "逾期复习", "description": "今天执行", "basis": "data", "confidence": "high", "support_refs": ["p1"]}],
            "data_gaps": ["缺少近期数据"],
        }
        result = benchmark.quality_summary(payload, {"p1"}, 321)
        self.assertEqual(result["support_refs"]["valid_rate"], 1.0)
        self.assertEqual(result["action_required_fields_complete_rate"], 1.0)
        self.assertEqual(result["exact_title_duplicates"], 1)
        self.assertTrue(result["theme_coverage"]["review_backlog"])

        aggregate = benchmark.aggregate_quality([{"quality": result}])
        self.assertEqual(aggregate["support_ref_valid_rate"], 1.0)
        self.assertEqual(aggregate["action_required_fields_complete_rate"], 1.0)

    def test_config_override_is_isolated(self):
        config = benchmark.ai_coach.AIConfig(True, "openai-compatible", "deepseek-v4-flash", "https://api.deepseek.com", "secret", "chat_completions", "", "high", True, 120, 2, 10, "*")
        original, original_hash = benchmark.ai_coach._request_config_summary(config, native_structured=False)
        disabled, disabled_hash = benchmark.ai_coach._request_config_summary(config, native_structured=False, thinking_mode="disabled")
        again, again_hash = benchmark.ai_coach._request_config_summary(config, native_structured=False)
        self.assertEqual((original, original_hash), (again, again_hash))
        self.assertNotEqual(original_hash, disabled_hash)
        self.assertTrue(original["reasoning_enabled"])
        self.assertFalse(disabled["reasoning_enabled"])
        self.assertEqual(config.thinking_enabled, True)


if __name__ == "__main__":
    unittest.main()
