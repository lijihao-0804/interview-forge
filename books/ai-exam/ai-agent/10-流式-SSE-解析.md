# 流式 SSE 解析

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python

def parse_sse(lines):
    event = {"event": "message", "data": []}
    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            if event["data"]:
                yield {"event": event["event"], "data": "\n".join(event["data"])}
            event = {"event": "message", "data": []}
        elif line.startswith("event:"):
            event["event"] = line[6:].strip()
        elif line.startswith("data:"):
            event["data"].append(line[5:].lstrip())
```

**追问**：断线重连如何避免漏事件？`Last-Event-ID` 如何使用？SSE 与 WebSocket 如何选择？

## 第四层：可观测与多 Agent 协作

面向生产的问题：追踪聚合与并发冲突。
