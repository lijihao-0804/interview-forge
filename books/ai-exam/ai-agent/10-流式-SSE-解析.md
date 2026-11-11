# 流式 SSE 解析

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：流式 SSE 解析
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）


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
// 题目：流式 SSE 解析
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）

import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;
    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) return null;
            st = new StringTokenizer(line);
        }
        return st.nextToken();
    }
    static int nextInt() throws IOException { return Integer.parseInt(next()); }
    static long nextLong() throws IOException { return Long.parseLong(next()); }
    // 核心方法：parseSse
    static List<Map<String, String>> parseSse(Iterable<String> lines) {
        List<Map<String, String>> events = new ArrayList<>();
        String eventType = "message";
        List<String> data = new ArrayList<>();
        // 循环处理
        for (String raw : lines) {
            String line = stripTrailingNewlines(raw);
            // 条件判断
            if (line.isEmpty()) {
                // 条件判断
                if (!data.isEmpty()) {
                    Map<String, String> event = new LinkedHashMap<>();
                    event.put("event", eventType);
                    event.put("data", String.join("
", data));
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
        // 返回结果
        return events;
    }

    private static String stripTrailingNewlines(String value) {
        int end = value.length();
        // 循环处理
        while (end > 0 && value.charAt(end - 1) == '
') {
            end--;
        }
        // 返回结果
        return value.substring(0, end);
    }

    private static String stripLeadingWhitespace(String value) {
        int start = 0;
        // 循环处理
        while (start < value.length() && Character.isWhitespace(value.charAt(start))) {
            start++;
        }
        // 返回结果
        return value.substring(start);
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        List<String> lines = new ArrayList<>();
        lines.add("event: update");
        lines.add("data: hello");
        lines.add("data: world");
        lines.add("");
        System.out.println(parseSse(lines));
    }
}
```
