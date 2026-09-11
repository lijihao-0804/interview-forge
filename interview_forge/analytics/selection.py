"""Budgeted atomic selection builder for the context compiler.

The builder is stateful by design, but its rules remain the compiler's rules;
helper lookups resolve through the facade at call time to preserve patch points.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any

from interview_forge.analytics.context_models import *


def _runtime():
    from interview_forge.analytics import context_compiler
    return context_compiler


def _serialize(value):
    return _runtime()._serialize(value)


def _hash_value(value):
    return _runtime()._hash_value(value)


def _fact_id(value):
    return _runtime()._fact_id(value)


def _build_trace_map(*args, **kwargs):
    return _runtime()._build_trace_map(*args, **kwargs)


def _diagnostic_representative_cases(*args, **kwargs):
    return _runtime()._diagnostic_representative_cases(*args, **kwargs)


def _diagnostic_anomalies(*args, **kwargs):
    return _runtime()._diagnostic_anomalies(*args, **kwargs)

class _SelectionBuilder:
    """Build and budget-check atomic context groups."""

    def __init__(
        self,
        *,
        task: str,
        tier: str,
        user_request: str,
        profile: dict[str, Any],
        summary: dict[str, Any],
        data_quality: dict[str, Any],
        data_as_of: str | None,
        strategy: str,
        input_omitted: dict[str, Any],
        analytics_text_truncated_chars: int,
        candidate_counts: dict[str, Any],
        diagnostic_digest: dict[str, Any] | None = None,
        diagnostic_problem_facts: list[dict[str, Any]] | None = None,
        diagnostic_content_facts: list[dict[str, Any]] | None = None,
        diagnostic_all_signals: list[dict[str, Any]] | None = None,
        diagnostic_data_as_of: str | None = None,
    ) -> None:
        self.task = task
        self.tier = tier
        self.user_request = user_request
        self.profile = profile
        self.summary = summary
        self.data_quality = data_quality
        self.data_as_of = data_as_of
        self.strategy = strategy
        self.input_omitted = input_omitted
        self.analytics_text_truncated_chars = analytics_text_truncated_chars
        self.candidate_counts = candidate_counts
        self.diagnostic_digest = diagnostic_digest
        self.trace_map: dict[str, dict[str, Any]] = {}
        self._diagnostic_problem_facts = diagnostic_problem_facts or []
        self._diagnostic_content_facts = diagnostic_content_facts or []
        self._diagnostic_all_signals = diagnostic_all_signals or []
        self._diagnostic_data_as_of = diagnostic_data_as_of
        self.facts: list[dict[str, Any]] = []
        self.signals: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.selection_reasons: list[dict[str, Any]] = []
        self._fact_ids: set[str] = set()
        self._signal_ids: set[str] = set()
        self._evidence_ids: set[str] = set()
        self._groups: list[dict[str, Any]] = []
        self.budget_pruned_items = 0
        self.profile_budget_omitted_fields = 0
        self.summary_budget_omitted_fields = 0
        self.snapshot_hash = "0" * 64
        self.meta: dict[str, Any] = {
            "compiler_version": COMPILER_VERSION,
            "deterministic": True,
            "read_only": True,
            "model_calls": 0,
            "writes_triggered": False,
            "selection_strategy": strategy,
            "budget": {
                "tier": tier,
                "target_tokens": BUDGET_TIERS[tier]["target_tokens"],
                "hard_max_tokens": BUDGET_TIERS[tier]["max_tokens"],
                "hard_max_chars": BUDGET_TIERS[tier]["max_chars"],
                "estimated_tokens": 0,
            },
            "trust_boundaries": dict(_TRUST_BOUNDARIES),
        }

    @property
    def limits(self) -> Mapping[str, int]:
        return BUDGET_TIERS[self.tier]["max_items"]

    def _reason(self, item_type: str, item_id: str, code: str, rank: int) -> dict[str, Any]:
        return {
            "reason_id": f"reason:{item_type}:{hashlib.sha256(item_id.encode('utf-8')).hexdigest()[:12]}",
            "item_type": item_type,
            "item_id": item_id,
            "reason_code": code,
            "rank": rank,
        }

    def _refresh_omitted(self) -> dict[str, Any]:
        counts = self.candidate_counts
        selected_by_type = {
            "problem_facts": sum(1 for item in self.facts if item.get("entity_type") == "problem"),
            "module_facts": sum(1 for item in self.facts if item.get("entity_type") == "module"),
            "content_facts": sum(1 for item in self.facts if item.get("entity_type") == "content"),
        }
        self.omitted = {
            "facts": max(0, int(counts.get("facts", 0)) - len(self.facts)),
            "signals": max(0, int(counts.get("signals", 0)) - len(self.signals)),
            "evidence": max(0, int(counts.get("evidence", 0)) - len(self.evidence)),
            "selection_reasons": max(
                0,
                int(counts.get("selection_reasons", 0)) - len(self.selection_reasons),
            ),
            "by_category": {
                key: max(0, int(counts.get(key, 0)) - selected_by_type.get(key, 0))
                for key in ("problem_facts", "module_facts", "content_facts")
            },
            "user_request": {
                "truncated_chars": int(self.input_omitted.get("user_request_chars", 0)),
            },
            "profile": {
                "unknown_fields": int(self.input_omitted.get("profile_unknown_fields", 0)),
                "invalid_fields": int(self.input_omitted.get("profile_invalid_fields", 0)),
                "truncated_chars": int(self.input_omitted.get("profile_truncated_chars", 0)),
                "budget_omitted_fields": self.profile_budget_omitted_fields,
            },
            "analytics_text_truncated_chars": int(self.analytics_text_truncated_chars),
            "budget": {
                "pruned_items": self.budget_pruned_items,
                "hard_limit_applied": True,
            },
        }
        return self.omitted

    def payload(self, *, snapshot_hash: str | None = None) -> dict[str, Any]:
        self._refresh_omitted()
        result: dict[str, Any] = {
            "context_schema_version": CONTEXT_SCHEMA_VERSION,
            "task": self.task,
            "user_request": self.user_request,
            "profile": self.profile,
            "summary": self.summary,
            "diagnostic_digest": self.diagnostic_digest,
            "trace_map": self.trace_map,
            "facts": self.facts,
            "signals": self.signals,
            "evidence": self.evidence,
            "data_quality": self.data_quality,
            "selection_reasons": self.selection_reasons,
            "omitted": self.omitted,
            "data_as_of": self.data_as_of,
            "snapshot_hash": self.snapshot_hash if snapshot_hash is None else snapshot_hash,
            "meta": self.meta,
        }
        return result

    def _refresh_diagnostic_digest(self) -> None:
        if self.diagnostic_digest is None:
            return
        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in self.evidence
            if isinstance(item, Mapping) and item.get("evidence_id")
        }
        diagnostic_facts = self._diagnostic_problem_facts + self._diagnostic_content_facts
        self.trace_map = _build_trace_map(self.signals, diagnostic_facts)
        self.diagnostic_digest["representative_cases"] = _diagnostic_representative_cases(
            self.signals,
            evidence_by_id,
            diagnostic_facts,
            self.trace_map,
        )
        self.diagnostic_digest["anomalies"] = _diagnostic_anomalies(
            self._diagnostic_problem_facts,
            self._diagnostic_data_as_of,
            self.signals,
            self.trace_map,
        )
        self.diagnostic_digest["coverage"]["context_budget_omitted"] = {
            "facts": int(self.omitted.get("facts", 0)),
            "signals": int(self.omitted.get("signals", 0)),
            "evidence": int(self.omitted.get("evidence", 0)),
            "selection_reasons": int(self.omitted.get("selection_reasons", 0)),
            "analytics_text_truncated_chars": int(
                self.omitted.get("analytics_text_truncated_chars", 0)
            ),
        }

    def _fits(self) -> bool:
        return len(_serialize(self.payload())) <= int(BUDGET_TIERS[self.tier]["max_chars"])

    def _append_reason(self, reason: dict[str, Any]) -> None:
        self.selection_reasons.append(reason)

    def try_add_fact(
        self,
        fact: dict[str, Any],
        *,
        reason_code: str,
        rank: int,
        mandatory: bool = False,
    ) -> bool:
        fact_id = _fact_id(fact)
        if fact_id in self._fact_ids:
            return False
        entity_type = str(fact.get("entity_type"))
        category_key = f"{entity_type}_facts"
        if len(self.facts) >= int(self.limits["facts"]):
            return False
        if category_key in self.limits and sum(
            1 for item in self.facts if item.get("entity_type") == entity_type
        ) >= int(self.limits[category_key]):
            return False
        if len(self.selection_reasons) >= int(self.limits["selection_reasons"]):
            return False
        reason = self._reason("fact", fact_id, reason_code, rank)
        self.facts.append(fact)
        self._fact_ids.add(fact_id)
        self._append_reason(reason)
        group = {
            "kind": "fact",
            "fact_id": fact_id,
            "reason_id": reason["reason_id"],
            "mandatory": mandatory,
        }
        self._groups.append(group)
        if not self._fits():
            self._groups.pop()
            self.facts.pop()
            self._fact_ids.remove(fact_id)
            self.selection_reasons.pop()
            if not mandatory:
                self.budget_pruned_items += 1
            return False
        return True

    def force_add_fact(self, fact: dict[str, Any], *, reason_code: str, rank: int) -> None:
        """Add a required fact after normal checks; the finalizer still verifies size."""
        fact_id = _fact_id(fact)
        if fact_id in self._fact_ids:
            return
        reason = self._reason("fact", fact_id, reason_code, rank)
        self.facts.append(fact)
        self._fact_ids.add(fact_id)
        self.selection_reasons.append(reason)
        self._groups.append(
            {
                "kind": "fact",
                "fact_id": fact_id,
                "reason_id": reason["reason_id"],
                "mandatory": True,
            }
        )

    def try_add_signal(
        self,
        signal: dict[str, Any],
        evidence_by_id: Mapping[str, dict[str, Any]],
        *,
        reason_code: str,
        rank: int,
        mandatory: bool = False,
    ) -> bool:
        signal_id = str(signal["signal_id"])
        if signal_id in self._signal_ids:
            return False
        evidence_ids = [str(item) for item in signal.get("evidence_ids", [])]
        new_evidence_ids = [item for item in evidence_ids if item not in self._evidence_ids]
        if len(self.signals) >= int(self.limits["signals"]):
            return False
        if len(self.evidence) + len(new_evidence_ids) > int(self.limits["evidence"]):
            return False
        if len(self.selection_reasons) >= int(self.limits["selection_reasons"]):
            return False
        evidence_items = [evidence_by_id[item] for item in new_evidence_ids]
        reason = self._reason("signal", signal_id, reason_code, rank)
        self.signals.append(signal)
        self._signal_ids.add(signal_id)
        self.evidence.extend(evidence_items)
        self._evidence_ids.update(new_evidence_ids)
        self.selection_reasons.append(reason)
        group = {
            "kind": "signal",
            "signal_id": signal_id,
            "evidence_ids": new_evidence_ids,
            "reason_id": reason["reason_id"],
            "mandatory": mandatory,
        }
        self._groups.append(group)
        if not self._fits():
            self._groups.pop()
            self.signals.pop()
            self._signal_ids.remove(signal_id)
            self.selection_reasons.pop()
            for item in evidence_items:
                self.evidence.remove(item)
            for item in new_evidence_ids:
                self._evidence_ids.remove(item)
            if not mandatory:
                self.budget_pruned_items += 1
            return False
        return True

    def add_protocol_reason(self) -> None:
        if len(self.selection_reasons) >= int(self.limits["selection_reasons"]):
            return
        reason = self._reason(
            "protocol",
            "learning_route",
            "no_course_retrieval",
            1,
        )
        self.selection_reasons.append(reason)
        self._groups.append(
            {
                "kind": "protocol",
                "reason_id": reason["reason_id"],
                "mandatory": True,
            }
        )

    def _remove_group(self, index: int) -> None:
        group = self._groups.pop(index)
        reason_id = group.get("reason_id")
        self.selection_reasons = [
            item for item in self.selection_reasons if item.get("reason_id") != reason_id
        ]
        if group["kind"] == "fact":
            fact_id = group["fact_id"]
            self.facts = [item for item in self.facts if _fact_id(item) != fact_id]
            self._fact_ids.discard(fact_id)
            return
        if group["kind"] != "signal":
            return
        signal_id = group["signal_id"]
        self.signals = [item for item in self.signals if item.get("signal_id") != signal_id]
        self._signal_ids.discard(signal_id)
        referenced: set[str] = {
            evidence_id
            for item in self.signals
            for evidence_id in item.get("evidence_ids", [])
        }
        removable = [
            evidence_id
            for evidence_id in group.get("evidence_ids", [])
            if evidence_id not in referenced
        ]
        self.evidence = [
            item for item in self.evidence if item.get("evidence_id") not in removable
        ]
        for evidence_id in removable:
            self._evidence_ids.discard(evidence_id)

    def _drop_last_optional(self) -> bool:
        for index in range(len(self._groups) - 1, -1, -1):
            if not self._groups[index].get("mandatory"):
                self._remove_group(index)
                self.budget_pruned_items += 1
                return True
        return False

    def _shrink_user_request(self) -> bool:
        if not self.user_request:
            return False
        remove = max(1, min(len(self.user_request), max(64, len(self.user_request) // 4)))
        self.user_request = self.user_request[: len(self.user_request) - remove]
        self.input_omitted["user_request_chars"] = (
            int(self.input_omitted.get("user_request_chars", 0)) + remove
        )
        self.budget_pruned_items += 1
        return True

    def _drop_profile_field(self) -> bool:
        if not self.profile:
            return False
        key = sorted(self.profile)[-1]
        self.profile.pop(key, None)
        self.profile_budget_omitted_fields += 1
        self.budget_pruned_items += 1
        return True

    def _hash_core(self) -> str:
        payload = self.payload(snapshot_hash="")
        core = {
            key: payload[key]
            for key in (
                "context_schema_version",
                "task",
                "user_request",
                "profile",
                "summary",
                "diagnostic_digest",
                "trace_map",
                "facts",
                "signals",
                "evidence",
                "data_quality",
                "selection_reasons",
                "omitted",
                "data_as_of",
            )
        }
        return _hash_value(core)

    def finalize(self) -> dict[str, Any]:
        for _attempt in range(96):
            self._refresh_omitted()
            self._refresh_diagnostic_digest()
            self.snapshot_hash = self._hash_core()
            payload = self.payload(snapshot_hash=self.snapshot_hash)
            provisional = _serialize(payload)
            estimated_tokens = max(1, math.ceil(len(provisional) / 4))
            self.meta["budget"]["estimated_tokens"] = estimated_tokens
            serialized = _serialize(self.payload(snapshot_hash=self.snapshot_hash))
            if len(serialized) <= int(BUDGET_TIERS[self.tier]["max_chars"]):
                return self.payload(snapshot_hash=self.snapshot_hash)
            if self._drop_last_optional():
                continue
            if self._shrink_user_request():
                continue
            if self._drop_profile_field():
                continue
            # All source fields are bounded, so reaching this point would mean
            # an implementation regression in the mandatory envelope.  Keep
            # the required schema and return the smallest safe representation.
            self.facts = [item for item in self.facts if item.get("entity_type") == "problem"][:1]
            self.signals = []
            self.evidence = []
            self.selection_reasons = [
                item for item in self.selection_reasons if item.get("item_type") == "fact"
            ][:1]
            self._fact_ids = {_fact_id(item) for item in self.facts}
            self._signal_ids.clear()
            self._evidence_ids.clear()
        raise ContextCompilerError("context budget could not be satisfied")

