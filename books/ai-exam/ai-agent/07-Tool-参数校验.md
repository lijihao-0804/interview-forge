# Tool 参数校验

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
TOOLS = {
    "get_weather": {
        "required": {"city"},
        "allowed": {"city", "date"},
        "risk": "read"
    },
    "send_email": {
        "required": {"to", "subject", "body"},
        "allowed": {"to", "subject", "body"},
        "risk": "write"
    }
}


def validate_tool_call(name: str, arguments: dict) -> list[str]:
    spec = TOOLS.get(name)
    if spec is None:
        return ["unknown tool"]
    errors = []
    missing = spec["required"] - arguments.keys()
    extra = arguments.keys() - spec["allowed"]
    if missing:
        errors.append(f"missing: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected: {sorted(extra)}")
    if spec["risk"] == "write":
        errors.append("approval required")
    return errors
```

**追问**：格式合法但业务参数越权怎么办？Schema 版本升级如何兼容运行中的任务？
