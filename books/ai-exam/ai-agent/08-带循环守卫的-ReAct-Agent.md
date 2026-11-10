# 带循环守卫的 ReAct Agent

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
import json


def action_fingerprint(action: dict) -> str:
    return json.dumps(action, ensure_ascii=False, sort_keys=True)


def run_agent(model, tools, objective, max_steps=12, repeat_limit=2):
    messages = [{"role": "user", "content": objective}]
    counts = {}

    for step in range(max_steps):
        decision = model(messages, list(tools))
        if decision["type"] == "final":
            return {"status": "completed", "answer": decision["answer"], "steps": step}

        fingerprint = action_fingerprint(decision)
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
        if counts[fingerprint] > repeat_limit:
            return {"status": "blocked", "reason": "repeated_action", "action": decision}

        tool = tools.get(decision["tool"])
        if tool is None:
            observation = {"ok": False, "error": "unknown_tool"}
        else:
            try:
                observation = {"ok": True, "result": tool(**decision.get("arguments", {}))}
            except Exception as exc:
                observation = {"ok": False, "error": type(exc).__name__}

        messages.append({"role": "assistant", "content": decision})
        messages.append({"role": "tool", "content": observation})

    return {"status": "blocked", "reason": "step_budget_exhausted"}
```

**追问**：如何检测 A→B→A→B 的路径震荡？怎样保存 Checkpoint？工具有副作用时如何恢复？
