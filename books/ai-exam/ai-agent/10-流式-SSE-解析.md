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

### Java 实现

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class SseParser {
    static List<Map<String, String>> parseSse(Iterable<String> lines) {
        List<Map<String, String>> events = new ArrayList<>();
        String eventType = "message";
        List<String> data = new ArrayList<>();
        for (String raw : lines) {
            String line = stripTrailingNewlines(raw);
            if (line.isEmpty()) {
                if (!data.isEmpty()) {
                    Map<String, String> event = new LinkedHashMap<>();
                    event.put("event", eventType);
                    event.put("data", String.join("\n", data));
                    events.add(event);
                }
                eventType = "message";
                data = new ArrayList<>();
            } else if (line.startsWith("event:")) {
                eventType = line.substring(6).trim();
            } else if (line.startsWith("data:")) {
                data.add(stripLeadingWhitespace(line.substring(5)));
            }
        }
        return events;
    }

    private static String stripTrailingNewlines(String value) {
        int end = value.length();
        while (end > 0 && value.charAt(end - 1) == '\n') {
            end--;
        }
        return value.substring(0, end);
    }

    private static String stripLeadingWhitespace(String value) {
        int start = 0;
        while (start < value.length() && Character.isWhitespace(value.charAt(start))) {
            start++;
        }
        return value.substring(start);
    }

    public static void main(String[] args) {
        List<String> lines = new ArrayList<>();
        lines.add("event: update");
        lines.add("data: hello");
        lines.add("data: world");
        lines.add("");
        System.out.println(parseSse(lines));
    }
}
```
