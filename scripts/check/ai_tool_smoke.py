"""Manual real-provider smoke checklist for AI Assistant M4.

This file is intentionally never imported by the application or automated
build. Run it manually in an environment with the existing AI configuration:

    python scripts/check/ai_tool_smoke.py

Then use the AI Assistant page and verify one turn at a time:

1. ``你好`` — no tool event.
2. ``146 是什么题`` — one ``get_problem`` call and a streamed final answer.
3. ``南京今天天气`` — one ``get_weather`` call and a streamed final answer.
4. ``我最近学得怎么样`` — use the preloaded learning context without a duplicate
   learning tool call.

In browser/network logs, the expected chain is:

    bind_tools -> tool.start/tool chunks -> ToolMessage -> second model round
    -> message.delta/message.done

The script only reads the existing AI configuration and prints this checklist;
it never contains or requests an API key and never sends a provider request by
itself. The actual provider smoke is an explicit human action.
"""
from __future__ import annotations

from interview_forge.ai.generation import load_ai_config


def main() -> int:
    config = load_ai_config()
    endpoint = getattr(config, "base_url", "") or "provider default"
    print("AI provider:", getattr(config, "provider", "unknown"))
    print("AI model:", getattr(config, "model", "unknown"))
    print("AI endpoint:", endpoint)
    print("AI configured:", bool(getattr(config, "configured", False)))
    print(__doc__.split("Then use the AI Assistant page", 1)[1].split("In browser/network", 1)[0].strip())
    return 0 if getattr(config, "configured", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
