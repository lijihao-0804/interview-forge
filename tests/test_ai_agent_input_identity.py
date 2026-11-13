import asyncio
import copy
import json
import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.chat.context_builder import (
    ContextBuilder,
    prepared_context_sha256,
)
from interview_forge.ai.chat.prompts import CHAT_SYSTEM_PROMPT
from interview_forge.ai.chat.service import (
    MAX_CHAT_MESSAGE_CHARS,
    ChatService,
    _runtime_config_fingerprint,
    normalize_message,
)
from interview_forge.ai.chat.token_budget import (
    ChatTokenBudget,
    ConservativeTokenEstimator,
    DEFAULT_CHAT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ESTIMATOR,
    budget_for_context_window,
)
from interview_forge.ai.config import AIConfig
from interview_forge.ai.tools.contracts import ToolSpec
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder


def _config(
    *,
    api_key: str = "config-api-key-secret",
    base_url: str = "https://url-user:url-password@private.invalid/v1?token=url-secret",
    actor_authorization: str = "actor-authorization-secret",
    reasoning_effort: str = "high",
    thinking_enabled: bool = True,
) -> AIConfig:
    return AIConfig(
        enabled=True,
        provider="openai-compatible",
        model="test-model",
        base_url=base_url,
        api_key=api_key,
        wire_api="chat_completions",
        actor_authorization=actor_authorization,
        reasoning_effort=reasoning_effort,
        thinking_enabled=thinking_enabled,
        request_timeout_seconds=45.0,
        max_concurrent_requests=2,
        daily_limit_per_user=3,
        beta_users="*",
        reasoning_mode="effort",
        reasoning_budget=None,
    )


def _runtime(
    config: AIConfig,
    *,
    provider_id: str | None = "provider-record-1",
    vendor: str = "vendor-a",
    capability_catalog_version: str = "catalog-v1",
) -> SimpleNamespace:
    return SimpleNamespace(
        config=config,
        provider_id=provider_id,
        provider_name="Provider Display Name",
        model=config.model,
        protocol=config.wire_api,
        secret=config.api_key,
        vendor=vendor,
        config_source="db" if provider_id else "env",
        capabilities={
            "streaming": True,
            "tools": True,
            "structured_output": True,
            "reasoning": True,
            "reasoning_modes": ["auto", "effort"],
            "reasoning_efforts": ["low", "high"],
            "reasoning_budget": False,
            "context_window": 32768,
        },
        capability_source="catalog",
        capability_profile="test_profile",
        canonical_model="canonical-test-model",
        capability_verified_at="2026-11-13T00:00:00Z",
        capability_catalog_version=capability_catalog_version,
        reasoning_policy=SimpleNamespace(mode="effort", effort="high", budget_tokens=None),
        headers={"Authorization": "header-secret"},
        cookies={"session": "cookie-secret"},
        credential_url="https://credential-secret.invalid",
    )


def _tool_schema(description: str = "Read a test value") -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "probe",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    }


def _fingerprint(
    config: AIConfig,
    runtime: SimpleNamespace,
    *,
    tool_policy: ToolPolicy | None = None,
    tool_schemas=None,
    system_prompt: str = CHAT_SYSTEM_PROMPT,
    prompt_estimator=DEFAULT_TOKEN_ESTIMATOR,
) -> str:
    return _runtime_config_fingerprint(
        config,
        runtime,
        context_budget=DEFAULT_CHAT_TOKEN_BUDGET,
        tool_policy=tool_policy or ToolPolicy(),
        tool_schemas=tool_schemas if tool_schemas is not None else [_tool_schema()],
        system_prompt=system_prompt,
        prompt_estimator=prompt_estimator,
    )


class _RuntimeDBTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        server_runtime.bind_provider(lambda: default_runtime)

    def tearDown(self) -> None:
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def database(
        self,
        relative_path: str,
        *,
        session_id: str,
        messages: list[tuple[str, str]] = (),
    ) -> Path:
        db = self.root / relative_path
        db.parent.mkdir(parents=True, exist_ok=True)
        connection = server_runtime.connect(db)
        try:
            connection.execute(
                "INSERT INTO chat_sessions(id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, "identity", "2026-11-13T00:00:00+00:00", "2026-11-13T00:00:00+00:00"),
            )
            for role, content in messages:
                connection.execute(
                    "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
                    "VALUES (?, ?, ?, '{}', ?)",
                    (session_id, role, content, "2026-11-13T00:00:00+00:00"),
                )
            connection.commit()
        finally:
            connection.close()
        return db


class PreparedContextIdentityTests(_RuntimeDBTestCase):
    def test_prepared_hash_is_canonical_and_excludes_storage_identity(self) -> None:
        first_db = self.database(
            "alice/hot100-study.db",
            session_id="session-alice",
            messages=[("user", "解释 Redis"), ("assistant", "RDB 与 AOF")],
        )
        second_db = self.database(
            "bob/archive.db",
            session_id="session-bob",
            messages=[("user", "解释 Redis"), ("assistant", "RDB 与 AOF")],
        )
        first_builder = ContextBuilder(system_prompt="stable system")
        second_builder = ContextBuilder(system_prompt="stable system")
        first_messages = first_builder.build(
            session_id="session-alice",
            current_message="解释 TCP 三次握手",
            user_db=first_db,
        )
        second_messages = second_builder.build(
            session_id="session-bob",
            current_message="解释 TCP 三次握手",
            user_db=second_db,
        )

        self.assertEqual(first_messages, second_messages)
        self.assertEqual(
            first_builder.last_build["prepared_context_hash"],
            second_builder.last_build["prepared_context_hash"],
        )
        self.assertEqual(
            first_builder.last_build["prepared_context_hash"],
            prepared_context_sha256(first_messages),
        )
        reordered = [
            {"content": message["content"], "role": message["role"]}
            for message in first_messages
        ]
        self.assertEqual(
            prepared_context_sha256(first_messages),
            prepared_context_sha256(reordered),
        )

        changed_question = ContextBuilder(system_prompt="stable system")
        changed_question.build(
            session_id="session-alice",
            current_message="解释 TCP 为什么需要四次挥手",
            user_db=first_db,
        )
        changed_system = ContextBuilder(system_prompt="replacement system")
        changed_system.build(
            session_id="session-alice",
            current_message="解释 TCP 三次握手",
            user_db=first_db,
        )
        self.assertNotEqual(
            first_builder.last_build["prepared_context_hash"],
            changed_question.last_build["prepared_context_hash"],
        )
        self.assertNotEqual(
            first_builder.last_build["prepared_context_hash"],
            changed_system.last_build["prepared_context_hash"],
        )

    def test_current_task_keeps_trailing_constraints_without_silent_clipping(self) -> None:
        db = self.database("user/hot100-study.db", session_id="long-task")
        current = (
            "请根据以下约束完成总结："
            + "保留完整任务背景。" * 220
            + "末尾硬约束：不得删除本句，也不得反转前面的否定条件。"
        )
        self.assertLessEqual(len(current), MAX_CHAT_MESSAGE_CHARS)
        builder = ContextBuilder(
            system_prompt="system",
            budget=ChatTokenBudget(
                summary_tokens=10,
                recent_tokens=10,
                system_tokens=100,
                current_tokens=10,
                output_tokens=10,
            ),
        )
        messages = builder.build(
            session_id="long-task",
            current_message=current,
            user_db=db,
        )

        self.assertEqual(messages[-1], {"role": "user", "content": current})
        self.assertIn("末尾硬约束：不得删除本句", messages[-1]["content"])
        self.assertGreater(
            builder.last_build["estimated_prompt_tokens"],
            builder.budget.current_tokens,
        )
        self.assertEqual(normalize_message(current), current)
        with self.assertRaises(ValueError):
            normalize_message("x" * (MAX_CHAT_MESSAGE_CHARS + 1))

    def test_prepared_hash_remains_independent_of_estimator_identity(self) -> None:
        db = self.database("estimator-user/hot100-study.db", session_id="estimator")
        first_estimator = ConservativeTokenEstimator()
        second_estimator = ConservativeTokenEstimator()
        second_estimator.name = "same-behavior-different-identity"
        first_builder = ContextBuilder(
            system_prompt="same system", estimator=first_estimator
        )
        second_builder = ContextBuilder(
            system_prompt="same system", estimator=second_estimator
        )
        first_messages = first_builder.build(
            session_id="estimator", current_message="same question", user_db=db
        )
        second_messages = second_builder.build(
            session_id="estimator", current_message="same question", user_db=db
        )

        self.assertEqual(first_messages, second_messages)
        self.assertEqual(
            first_builder.last_build["prepared_context_hash"],
            second_builder.last_build["prepared_context_hash"],
        )


class RuntimeConfigIdentityTests(unittest.TestCase):
    def test_fingerprint_tracks_binding_and_policy_but_not_secrets_or_endpoint_text(self) -> None:
        first_config = _config()
        first_runtime = _runtime(first_config)
        baseline = _fingerprint(first_config, first_runtime)

        changed_secrets = _config(
            api_key="different-api-key-secret",
            base_url="https://different:password@other.invalid/v1?token=other-secret",
            actor_authorization="different-actor-secret",
        )
        changed_secret_runtime = _runtime(changed_secrets)
        changed_secret_runtime.headers = {"Authorization": "different-header-secret"}
        changed_secret_runtime.cookies = {"session": "different-cookie-secret"}
        self.assertEqual(
            baseline,
            _fingerprint(changed_secrets, changed_secret_runtime),
        )
        self.assertNotIn(first_config.api_key, baseline)
        self.assertNotIn(first_config.base_url, baseline)
        self.assertRegex(baseline, re.compile(r"^[0-9a-f]{64}$"))

        provider_changed = _fingerprint(
            first_config, _runtime(first_config, provider_id="provider-record-2")
        )
        vendor_changed = _fingerprint(
            first_config, _runtime(first_config, vendor="vendor-b")
        )
        capability_changed = _fingerprint(
            first_config,
            _runtime(first_config, capability_catalog_version="catalog-v2"),
        )
        policy_changed = _fingerprint(
            first_config,
            first_runtime,
            tool_policy=ToolPolicy(max_rounds=4),
        )
        schema_changed = _fingerprint(
            first_config,
            first_runtime,
            tool_schemas=[_tool_schema("Read a different value")],
        )
        reasoning_config = _config(
            reasoning_effort="low",
            thinking_enabled=False,
        )
        reasoning_runtime = _runtime(reasoning_config)
        reasoning_runtime.reasoning_policy = SimpleNamespace(
            mode="effort", effort="low", budget_tokens=None
        )
        reasoning_changed = _fingerprint(reasoning_config, reasoning_runtime)
        for changed in (
            provider_changed,
            vendor_changed,
            capability_changed,
            policy_changed,
            schema_changed,
            reasoning_changed,
        ):
            self.assertNotEqual(baseline, changed)

        schema_a = _tool_schema()
        schema_b = copy.deepcopy(schema_a)
        schema_b["function"]["parameters"]["properties"] = {
            "limit": {"type": "integer"},
            "value": {"type": "string"},
        }
        self.assertEqual(
            _fingerprint(first_config, first_runtime, tool_schemas=[schema_a]),
            _fingerprint(first_config, first_runtime, tool_schemas=[schema_b]),
        )

        env_config = _config()
        env_fingerprint = _fingerprint(
            env_config,
            _runtime(env_config, provider_id=None),
            tool_schemas=[schema_a],
        )
        self.assertNotEqual(baseline, env_fingerprint)

    def test_same_version_prompt_content_and_estimator_change_config_identity(self) -> None:
        config = _config()
        runtime = _runtime(config)
        with patch(
            "interview_forge.ai.chat.service.CHAT_PROMPT_POLICY_VERSION",
            "fixed-prompt-policy-version",
        ):
            baseline = _fingerprint(config, runtime)
            prompt_changed = _fingerprint(
                config,
                runtime,
                system_prompt=CHAT_SYSTEM_PROMPT + "\n同版本正文变更。",
            )
        self.assertNotEqual(baseline, prompt_changed)

        renamed_estimator = ConservativeTokenEstimator()
        renamed_estimator.name = "multilingual-character-fallback-v3-test"
        estimator_changed = _fingerprint(
            config,
            runtime,
            prompt_estimator=renamed_estimator,
        )
        self.assertNotEqual(baseline, estimator_changed)


class TraceWhitelistTests(_RuntimeDBTestCase):
    def test_only_declared_metadata_survives_and_trace_contains_no_bodies_or_secrets(self) -> None:
        db = self.database("trace-user/hot100-study.db", session_id="trace-session")
        allowed = {
            "context_budget_policy_version": "budget-vX",
            "request_fingerprint": "1" * 64,
            "prepared_context_hash": "2" * 64,
            "config_fingerprint": "3" * 64,
            "prompt_estimator": "estimator-vX",
            "admitted_prompt_tokens": 321,
            "omitted_exchange_count": 2,
            "context_window": 32768,
            "reserved_output_tokens": 1200,
            "stop_reason": "history_omitted",
        }
        forbidden = {
            "prompt": "PRIVATE PROMPT BODY",
            "messages": [{"role": "user", "content": "PRIVATE MESSAGE BODY"}],
            "content": "PRIVATE CONTENT BODY",
            "summary": "PRIVATE SUMMARY BODY",
            "db_path": str(db),
            "base_url": "https://url-user:url-password@private.invalid",
            "api_key": "api-key-secret",
            "headers": {"Authorization": "header-secret"},
            "cookies": {"session": "cookie-secret"},
        }
        recorder = TraceRecorder(
            user_db=db,
            trace_id="trace-identity",
            session_id="trace-session",
            provider="openai-compatible",
            model="test-model",
        )
        recorder.record(
            event_type="context",
            name="context_selection",
            status="success",
            metadata={**forbidden, **allowed},
        )

        connection = server_runtime.connect(db)
        try:
            rows = connection.execute(
                "SELECT metadata_json FROM ai_trace_events WHERE trace_id = ?",
                ("trace-identity",),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(rows), 1)
        metadata = json.loads(rows[0]["metadata_json"])
        for key, value in allowed.items():
            self.assertEqual(metadata[key], value)
        for key in forbidden:
            self.assertNotIn(key, metadata)
        serialized = json.dumps(dict(rows[0]), ensure_ascii=False)
        for value in forbidden.values():
            if isinstance(value, str):
                self.assertNotIn(value, serialized)


class _FakeChunk:
    def __init__(self, content: str = "", *, tool_calls: list[dict[str, object]] | None = None) -> None:
        self.content = content
        self.tool_calls = list(tool_calls or [])
        self.tool_call_chunks = []
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 2}
        self.response_metadata = {}
        self.additional_kwargs = {}


class _ToolCallingProvider:
    def __init__(self) -> None:
        self.seen: list[list[dict[str, object]]] = []
        self.bound_schemas: list[dict[str, object]] = []

    def bind_tools(self, schemas: list[dict[str, object]]) -> "_ToolCallingProvider":
        self.bound_schemas = copy.deepcopy(schemas)
        return self

    async def astream(self, messages):
        self.seen.append(copy.deepcopy(messages))
        has_tool_result = any(
            isinstance(item, dict) and item.get("role") == "tool"
            for item in messages
        )
        if not has_tool_result:
            yield _FakeChunk(
                tool_calls=[{"id": "probe-call", "name": "probe", "args": {"value": "x", "limit": 1}}]
            )
            return
        yield _FakeChunk("处理完成")


class _NoToolCallProvider:
    def __init__(self) -> None:
        self.bound_schemas: list[dict[str, object]] = []
        self.seen = []

    def bind_tools(self, schemas: list[dict[str, object]]) -> "_NoToolCallProvider":
        self.bound_schemas = copy.deepcopy(schemas)
        return self

    async def astream(self, messages):
        self.seen.append(copy.deepcopy(messages))
        yield _FakeChunk("无需工具")


class _ProbeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    limit: int = 1


async def _collect(iterator):
    return [item async for item in iterator]


class ChatServiceIdentityIntegrationTests(_RuntimeDBTestCase):
    def test_explicit_empty_registry_is_preserved_and_hashed_as_empty(self) -> None:
        db = self.root / "empty-tools-user" / "hot100-study.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        config = _config()
        runtime = _runtime(config)
        empty_registry = ToolRegistry()
        policy = ToolPolicy()
        provider = _NoToolCallProvider()
        service = ChatService(
            runtime_loader=lambda _business: runtime,
            model_factory=lambda _config: provider,
            tool_registry=empty_registry,
            tool_policy=policy,
        )

        self.assertIs(service.tool_registry, empty_registry)
        self.assertEqual(service.tool_registry.model_schemas(), [])
        service_with_defaults = ChatService(
            runtime_loader=lambda _business: runtime,
            model_factory=lambda _config: provider,
        )
        self.assertGreater(len(service_with_defaults.tool_registry), 0)

        session = service.create_session(user_db=db)
        events = asyncio.run(
            _collect(
                service.stream_reply(
                    user_db=db,
                    session_id=session["id"],
                    message="请直接回答，不需要工具",
                )
            )
        )
        self.assertEqual(events[-1]["event"], "message.done")
        self.assertEqual(provider.bound_schemas, [])

        context_budget = budget_for_context_window(32768)
        expected_empty_fingerprint = _runtime_config_fingerprint(
            config,
            runtime,
            context_budget=context_budget,
            tool_policy=policy,
            tool_schemas=[],
            system_prompt=CHAT_SYSTEM_PROMPT,
            prompt_estimator=DEFAULT_TOKEN_ESTIMATOR,
        )
        connection = server_runtime.connect(db)
        try:
            row = connection.execute(
                "SELECT metadata_json FROM ai_trace_events "
                "WHERE name = 'context_selection' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
        metadata = json.loads(row["metadata_json"])
        self.assertEqual(metadata["config_fingerprint"], expected_empty_fingerprint)

    def test_real_orchestrator_receives_window_budget_and_untrimmed_current_task(self) -> None:
        db = self.root / "service-user" / "hot100-study.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        config = replace(_config(), reasoning_mode="budget", reasoning_budget=1536, reasoning_effort="")
        runtime = _runtime(config)
        runtime.reasoning_policy = SimpleNamespace(mode="budget", effort=None, budget_tokens=1536)
        runtime.capabilities.update(reasoning_modes=["auto", "budget"], reasoning_budget=True)
        provider = _ToolCallingProvider()
        seen_artifacts = {}

        def probe(context, _args):
            seen_artifacts.update(copy.deepcopy(context.artifacts))
            return {"value": "received"}

        registry = ToolRegistry([
            ToolSpec(
                name="probe",
                display_name="Probe",
                description="Read a test value",
                args_model=_ProbeArgs,
                handler=probe,
            )
        ])
        policy = ToolPolicy(max_rounds=2)
        service = ChatService(
            runtime_loader=lambda _business: runtime,
            model_factory=lambda _config: provider,
            tool_registry=registry,
            tool_policy=policy,
        )
        session = service.create_session(user_db=db)
        current = "请检查当前请求的完整性。" + "背景约束不得丢失。" * 350 + "末尾否定：不得省略此约束。"
        self.assertLessEqual(len(current), MAX_CHAT_MESSAGE_CHARS)
        events = asyncio.run(
            _collect(
                service.stream_reply(
                    user_db=db,
                    session_id=session["id"],
                    message=current,
                    request_id="identity-request",
                )
            )
        )

        self.assertEqual(events[-1]["event"], "message.done")
        self.assertEqual(provider.seen[0][-1], {"role": "user", "content": current})
        self.assertEqual(seen_artifacts["model_context_window"], 32768)
        self.assertEqual(
            seen_artifacts["reserved_output_tokens"],
            DEFAULT_CHAT_TOKEN_BUDGET.output_tokens + 1536,
        )

        connection = server_runtime.connect(db)
        try:
            row = connection.execute(
                "SELECT provider, model, metadata_json FROM ai_trace_events "
                "WHERE name = 'context_selection' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            all_trace_rows = connection.execute(
                "SELECT provider, model, metadata_json FROM ai_trace_events"
            ).fetchall()
        finally:
            connection.close()
        self.assertIsNotNone(row)
        metadata = json.loads(row["metadata_json"])
        self.assertRegex(metadata["prepared_context_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(metadata["config_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(metadata["context_window"], 32768)
        self.assertEqual(
            metadata["reserved_output_tokens"],
            DEFAULT_CHAT_TOKEN_BUDGET.output_tokens + 1536,
        )
        self.assertEqual(
            metadata["prepared_context_hash"],
            prepared_context_sha256(provider.seen[0]),
        )
        trace_text = json.dumps([dict(item) for item in all_trace_rows], ensure_ascii=False)
        self.assertNotIn(current, trace_text)
        self.assertNotIn(str(db), trace_text)
        for forbidden in (
            config.api_key,
            config.base_url,
            config.actor_authorization,
            "header-secret",
            "cookie-secret",
            "credential-secret",
        ):
            self.assertNotIn(forbidden, trace_text)


if __name__ == "__main__":
    unittest.main()
