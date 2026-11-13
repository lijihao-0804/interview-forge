from __future__ import annotations

import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from interview_forge.ai.chat.request_budget import (
    REASON_FITS,
    REASON_HISTORY_OMITTED,
    REASON_MANDATORY_OVERFLOW,
    REASON_RESERVED_OUTPUT,
    REASON_TOOL_RESULTS_REDUCED,
    admit_request,
    estimate_json_tokens,
)
from interview_forge.ai.chat.token_budget import DEFAULT_CHAT_TOKEN_BUDGET
from interview_forge.ai.token_counting import (
    DEFAULT_TOKEN_ESTIMATOR,
    estimate_text_tokens,
    trim_text_to_tokens,
)


class CharacterEstimator:
    """A transparent estimator that makes request-boundary behavior observable."""

    def estimate_text(self, text: str) -> int:
        return len(text)


def read_batch(tool: str, call_id: str, text: str) -> list[dict]:
    return [
        {"role": "assistant", "content": "", "tool_calls": [{"id": call_id, "name": tool, "args": {"q": call_id}}]},
        {"role": "tool", "tool_call_id": call_id,
         "content": json.dumps({"ok": True, "tool": tool, "data": {"text": text}}, ensure_ascii=False)},
    ]


class RequestBudgetTests(unittest.TestCase):
    def setUp(self):
        self.estimator = CharacterEstimator()

    def _cost(self, messages, *, tools=()):
        admission = admit_request(
            messages,
            tool_schemas=tools,
            estimator=self.estimator,
        )
        self.assertTrue(admission.fits)
        return admission.estimated_prompt_tokens

    def test_trim_at_zero_one_and_two_tokens_never_exceeds_its_budget(self):
        fits_without_changes = [
            ("abc", 1),
            (" a ", 1),
            ("中", 2),
        ]
        for original, budget in fits_without_changes:
            self.assertEqual(
                trim_text_to_tokens(original, budget, DEFAULT_TOKEN_ESTIMATOR),
                original,
            )

        expected = [
            ("abc", 0, ""),
            ("中文", 0, ""),
            ("abcd", 1, "abc"),
            ("中文", 1, ""),
            ("abcdefg", 2, "a…"),
            ("中文", 2, "…"),
            ("a中b", 2, "a…"),
        ]
        for original, budget, wanted in expected:
            clipped = trim_text_to_tokens(original, budget, DEFAULT_TOKEN_ESTIMATOR)
            self.assertEqual(clipped, wanted)
            self.assertLessEqual(
                estimate_text_tokens(clipped, DEFAULT_TOKEN_ESTIMATOR),
                budget,
            )

        for original in ("abcd", "中文", "a中b"):
            for budget in (0, 1, 2):
                clipped = trim_text_to_tokens(original, budget, DEFAULT_TOKEN_ESTIMATOR)
                self.assertLessEqual(
                    estimate_text_tokens(clipped, DEFAULT_TOKEN_ESTIMATOR),
                    budget,
                )

    def test_current_task_and_tail_constraints_are_never_clipped_on_overflow(self):
        current = (
            "请完整分析下面这个必须保留的长任务。" + "背景资料。" * 2500
            + "但是不得删除末尾的限制：只有用户明确输入“确认执行”时才可继续；"
            + "除非出现新的书面授权，否则保持不变。"
        )
        messages = [
            {"role": "system", "content": "服务端规则必须全部保留"},
            {"role": "user", "content": current},
        ]
        schema = {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "查询资料",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        unrestricted = admit_request(
            messages,
            tool_schemas=[schema],
            estimator=self.estimator,
        )
        reserved = 17
        admission = admit_request(
            messages,
            tool_schemas=[schema],
            context_window=unrestricted.estimated_prompt_tokens + reserved - 1,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )

        self.assertFalse(admission.fits)
        self.assertEqual(admission.reason, REASON_MANDATORY_OVERFLOW)
        self.assertEqual(admission.messages[1]["content"], current)
        self.assertTrue(admission.messages[1]["content"].endswith("否则保持不变。"))
        self.assertEqual(admission.request_fingerprint, unrestricted.request_fingerprint)
        self.assertEqual(admission.omitted_exchange_count, 0)

    def test_history_is_evicted_in_complete_user_turn_suffix(self):
        system = {"role": "system", "content": "system"}
        old_user = {"role": "user", "content": "旧任务" * 200}
        old_answer = {"role": "assistant", "content": "旧结论"}
        recent_user = {"role": "user", "content": "较新的历史问题"}
        recent_answer = {"role": "assistant", "content": "较新的历史回答"}
        current = {"role": "user", "content": "当前问题：保留我"}
        all_messages = [
            system, old_user, old_answer, recent_user, recent_answer, current,
        ]
        without_oldest = [system, recent_user, recent_answer, current]
        reserved = 11
        expected_cost = self._cost(without_oldest)

        admission = admit_request(
            all_messages,
            context_window=expected_cost + reserved,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )

        self.assertTrue(admission.fits)
        self.assertEqual(admission.reason, REASON_HISTORY_OMITTED)
        self.assertEqual(admission.omitted_exchange_count, 1)
        self.assertEqual(admission.messages, without_oldest)

    def test_assistant_tool_call_and_results_are_one_atomic_history_turn(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "旧查询"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-old", "name": "lookup", "args": {"q": "x"}}],
            },
            {
                "role": "tool",
                "tool_call_id": "call-old",
                "content": '{"ok":true,"tool":"lookup","data":{"answer":"旧资料"}}',
            },
            {"role": "assistant", "content": "旧查询的结论"},
            {"role": "user", "content": "当前必须回答的新问题"},
        ]
        mandatory = [messages[0], messages[-1]]
        reserved = 9
        mandatory_cost = self._cost(mandatory)

        admission = admit_request(
            messages,
            context_window=mandatory_cost + reserved,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )

        self.assertTrue(admission.fits)
        self.assertEqual(admission.omitted_exchange_count, 1)
        self.assertEqual(admission.messages, mandatory)
        self.assertNotIn("tool", [message["role"] for message in admission.messages])

    def test_tool_exchange_after_current_user_stays_complete(self):
        current_user = {"role": "user", "content": "当前任务原文"}
        current_call = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "current-call", "name": "lookup", "args": {"q": "now"}}],
        }
        current_result = {
            "role": "tool",
            "tool_call_id": "current-call",
            "content": '{"ok":true,"tool":"lookup","data":{"answer":"当前结果"}}',
        }
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "已经过期的历史"},
            {"role": "assistant", "content": "过期回答"},
            current_user,
            current_call,
            current_result,
        ]
        reserved = 13
        mandatory_cost = self._cost([messages[0], current_user, current_call, current_result])

        admission = admit_request(
            messages,
            context_window=mandatory_cost + reserved,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )

        self.assertTrue(admission.fits)
        self.assertEqual(admission.omitted_exchange_count, 1)
        self.assertEqual(
            [message["role"] for message in admission.messages],
            ["system", "user", "assistant", "tool"],
        )
        self.assertEqual(admission.messages[1]["content"], "当前任务原文")
        self.assertEqual(admission.messages[2]["tool_calls"][0]["id"], "current-call")
        self.assertEqual(admission.messages[3]["tool_call_id"], "current-call")

    def test_tool_call_arguments_and_complete_result_content_affect_cost(self):
        def request(arguments, result):
            return [
                {"role": "user", "content": "当前任务"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call-1", "name": "lookup", "args": arguments}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "content": result,
                },
            ]

        small = request(
            {"query": "a"},
            '{"ok":true,"tool":"lookup","data":{"value":"a"}}',
        )
        large = request(
            {"query": "a" * 200},
            '{"ok":true,"tool":"lookup","data":{"value":"' + "b" * 200 + '"}}',
        )

        self.assertGreater(self._cost(large), self._cost(small))
        schema = {"name": "lookup", "parameters": {"type": "object", "properties": {}}}
        self.assertGreater(
            self._cost([{"role": "user", "content": "当前任务"}], tools=[schema]),
            self._cost([{"role": "user", "content": "当前任务"}]),
        )
        self.assertEqual(
            estimate_json_tokens({"value": "中文"}, estimator=self.estimator),
            len('{"value":"中文"}'),
        )

    def test_known_window_subtracts_reserved_output_and_unknown_uses_prompt_default(self):
        messages = [{"role": "user", "content": "short current task"}]
        required = self._cost(messages)
        reserved = 23

        exact = admit_request(
            messages,
            context_window=required + reserved,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )
        too_small = admit_request(
            messages,
            context_window=required + reserved - 1,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )
        impossible_output = admit_request(
            messages,
            context_window=reserved - 1,
            reserved_output_tokens=reserved,
            estimator=self.estimator,
        )
        unknown_too_large = admit_request(
            [{"role": "user", "content": "x" * (DEFAULT_CHAT_TOKEN_BUDGET.max_prompt_tokens + 10)}],
            estimator=self.estimator,
        )

        self.assertTrue(exact.fits)
        self.assertEqual(exact.reason, REASON_FITS)
        self.assertFalse(too_small.fits)
        self.assertEqual(too_small.reason, REASON_MANDATORY_OVERFLOW)
        self.assertFalse(impossible_output.fits)
        self.assertEqual(impossible_output.reason, REASON_RESERVED_OUTPUT)
        self.assertFalse(unknown_too_large.fits)
        unknown_with_thinking = admit_request(
            messages, reserved_output_tokens=DEFAULT_CHAT_TOKEN_BUDGET.max_request_tokens - required + 1,
            estimator=self.estimator,
        )
        self.assertFalse(unknown_with_thinking.fits)

    def test_langchain_messages_are_normalized_without_losing_tool_data(self):
        current = "当前 LangChain 任务：保留末尾否定条件"
        messages = [
            SystemMessage(content="全部 system 指令"),
            HumanMessage(content="旧问题"),
            AIMessage(
                content="查询",
                tool_calls=[{"id": "lc-call", "name": "lookup", "args": {"q": "中文"}}],
            ),
            ToolMessage(
                content='{"ok":true,"tool":"lookup","data":{"answer":"结果"}}',
                tool_call_id="lc-call",
            ),
            AIMessage(content="旧答案"),
            HumanMessage(content=current),
        ]

        admission = admit_request(messages, estimator=self.estimator)

        self.assertTrue(admission.fits)
        self.assertEqual(admission.messages[-1], {"role": "user", "content": current})
        self.assertEqual(admission.messages[2]["tool_calls"][0]["args"], {"q": "中文"})
        self.assertEqual(admission.messages[3]["role"], "tool")
        self.assertEqual(admission.messages[3]["tool_call_id"], "lc-call")

    def test_fingerprint_is_canonical_and_ignores_external_metadata(self):
        first = [
            {"role": "system", "content": "system", "id": "m-1"},
            {"role": "user", "content": "current", "created_at": "2026-01-01"},
        ]
        second = [
            {"content": "system", "role": "system", "response_metadata": {"provider": "x"}},
            {"type": "human", "content": "current", "usage_metadata": {"total_tokens": 7}},
        ]
        tools_a = [{"name": "lookup", "parameters": {"type": "object", "properties": {}}}]
        tools_b = [json.loads(json.dumps(tools_a[0], ensure_ascii=False))]

        a = admit_request(first, tool_schemas=tools_a, context_window=20_000, estimator=self.estimator)
        b = admit_request(second, tool_schemas=tools_b, context_window=2_000, estimator=self.estimator)
        self.assertEqual(a.messages, b.messages)
        self.assertEqual(a.request_fingerprint, b.request_fingerprint)

    def test_unsupported_message_and_orphan_tool_fail_explicitly(self):
        with self.assertRaises(TypeError):
            admit_request([object()], estimator=self.estimator)
        with self.assertRaisesRegex(ValueError, "orphan tool"):
            admit_request(
                [
                    {"role": "user", "content": "current"},
                    {"role": "tool", "tool_call_id": "missing", "content": "{}"},
                ],
                estimator=self.estimator,
            )

    def test_pressure_masks_before_eviction_preserving_newest_parallel_results(self):
        first = read_batch("lookup", "old", "第一份资料" * 100)
        latest = read_batch("lookup", "next", "第二份资料")
        parallel = read_batch("lookup", "parallel", "第三份资料")
        latest[0]["tool_calls"].extend(parallel[0]["tool_calls"])
        latest.append(parallel[1])
        messages = [
            {"role": "system", "content": "系统规则"},
            {"role": "user", "content": "早先相关的问题"}, {"role": "assistant", "content": "要用队列。"},
            {"role": "user", "content": "请比较两份资料，末尾保留队列的适用条件。"},
            *first, *latest,
        ]
        tools = [{"name": "lookup", "parameters": {"type": "object"}}]
        options = {"tool_schemas": tools, "read_tools": {"lookup"}, "reserved_output_tokens": 37, "estimator": self.estimator}
        original = self._cost(messages, tools=tools)
        full = admit_request(messages, context_window=original * 2, **options)
        self.assertEqual(full.messages, messages)
        self.assertEqual((full.masked_tool_result_count, full.tool_result_tokens_saved), (0, 0))
        for prompt_limit in (original - 10, original + 10):
            with self.subTest(prompt_limit=prompt_limit):
                admission = admit_request(messages, context_window=prompt_limit + 37, **options)
                self.assertTrue(admission.fits)
                self.assertEqual(admission.reason, REASON_TOOL_RESULTS_REDUCED)
                self.assertEqual(admission.omitted_exchange_count, 0)
                self.assertEqual(admission.messages[:5], messages[:5])
                self.assertEqual(admission.messages[6:], latest)
                self.assertEqual(admission.messages[5]["tool_call_id"], "old")
                self.assertEqual(json.loads(admission.messages[5]["content"]), {"omitted": "earlier_read_result"})
                self.assertEqual(admission.original_prompt_tokens, original)
                self.assertEqual(admission.original_prompt_tokens - admission.estimated_prompt_tokens,
                                 admission.tool_result_tokens_saved)
                self.assertEqual(admission.masked_tool_result_count, 1)
                self.assertEqual(admission.budget_rejected_tool_result_count, 0)
                self.assertEqual(admission.visible_tool_message_indices, {7, 8})
                self.assertNotEqual(admission.request_fingerprint, full.request_fingerprint)
        self.assertEqual(admit_request(messages, context_window=original * 2, **options).messages, full.messages)

    def test_mixed_failed_and_unrecognized_batches_and_last_success_stay_intact(self):
        good = read_batch("lookup", "old", "很旧的只读资料" * 100)
        wrong_tool = read_batch("action", "action-1", "这个工具类型不是只读")
        mixed = read_batch("lookup", "mixed-read", "同批次包含待确认操作" * 20)
        confirm = read_batch("save", "pending", "")
        confirm[1]["content"] = '{"ok":false,"tool":"save","error":{"code":"confirmation_required"},"action_id":"keep-me"}'
        mixed[0]["tool_calls"].extend(confirm[0]["tool_calls"])
        mixed.append(confirm[1])
        failure = read_batch("lookup", "error", "")
        failure[1]["content"] = '{"ok":false,"tool":"lookup","error":{"code":"timeout"}}'
        unrecognized = read_batch("lookup", "unknown", "")
        unrecognized[1]["content"] = '{"ok":true,"tool":"other","data":{"text":"different called name"}}'
        latest = read_batch("lookup", "latest", "最后一次实际读到的证据。")
        messages = [{"role": "user", "content": "查询资料"}, *good, *wrong_tool, *mixed, *unrecognized, *latest, *failure]
        limit = self._cost(messages) - 10
        admission = admit_request(messages, context_window=limit, reserved_output_tokens=0,
                                  read_tools={"lookup"}, estimator=self.estimator)
        self.assertTrue(admission.fits)
        self.assertEqual(admission.masked_tool_result_count, 1)
        self.assertNotEqual(admission.messages[2], messages[2])
        self.assertEqual(admission.messages[3:], messages[3:])
        without_allowlist = admit_request(messages, context_window=limit, reserved_output_tokens=0, estimator=self.estimator)
        self.assertFalse(without_allowlist.fits)
        self.assertEqual(without_allowlist.messages, messages)

    def test_clears_only_as_many_older_parallel_reads_as_needed(self):
        early = read_batch("lookup", "a", "过期的清单" * 100)
        second = read_batch("lookup", "b", "更短的可用线索")
        early[0]["tool_calls"].extend(second[0]["tool_calls"])
        early.append(second[1])
        latest = read_batch("lookup", "c", "新线索")
        messages = [{"role": "user", "content": "整合查询"}, *early, *latest]
        limit = self._cost(messages) - 40
        admission = admit_request(messages, context_window=limit, reserved_output_tokens=0,
                                  read_tools={"lookup"}, estimator=self.estimator)
        self.assertTrue(admission.fits)
        self.assertEqual(admission.masked_tool_result_count, 1)
        self.assertEqual(admission.messages[3:], messages[3:])

    def test_protected_current_task_and_latest_read_can_still_exceed_window(self):
        current = "完整的问题" * 35 + "只用给出的材料。"
        messages = [{"role": "developer", "content": "规则"}, {"role": "user", "content": current},
                    *read_batch("read", "previous", "首份资料" * 80), *read_batch("read", "latest", "当前资料" * 80)]
        admission = admit_request(messages, context_window=200, reserved_output_tokens=40,
                                  read_tools={"read"}, estimator=self.estimator)
        self.assertFalse(admission.fits)
        self.assertEqual(admission.reason, REASON_MANDATORY_OVERFLOW)
        self.assertEqual(admission.masked_tool_result_count, 1)
        self.assertEqual(admission.messages[:3], messages[:3])
        self.assertEqual(admission.messages[-2:], messages[-2:])


if __name__ == "__main__":
    unittest.main()
