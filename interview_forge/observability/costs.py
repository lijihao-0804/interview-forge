"""Optional model pricing configuration with safe, nullable estimates."""
from __future__ import annotations

import json
import os
from typing import Any


def load_pricing() -> dict[str, dict[str, float]]:
    raw = os.environ.get("AI_MODEL_PRICING_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, dict[str, float]] = {}
    for model, value in parsed.items():
        if not isinstance(model, str) or not isinstance(value, dict):
            continue
        try:
            input_price = float(value.get("input_per_1m"))
            output_price = float(value.get("output_per_1m"))
        except (TypeError, ValueError):
            continue
        if input_price < 0 or output_price < 0:
            continue
        result[model[:128]] = {"input_per_1m": input_price, "output_per_1m": output_price}
    return result


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    pricing = load_pricing().get(str(model or ""))
    if pricing is None:
        return None
    return round(
        (max(0, int(input_tokens)) * pricing["input_per_1m"]
         + max(0, int(output_tokens)) * pricing["output_per_1m"]) / 1_000_000,
        8,
    )


__all__ = ["estimate_cost", "load_pricing"]
