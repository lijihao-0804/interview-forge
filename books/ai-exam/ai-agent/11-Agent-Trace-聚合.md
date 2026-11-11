# Agent Trace 聚合

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

输入一组 Span，统计：

- 总延迟；
- 模型、检索、工具耗时；
- Token 和成本；
- 重试次数；
- 最慢步骤；
- 相同错误指纹。

要求输出结构化报告，并处理 Span 缺失、重复和乱序。

### Java 实现

```java
// 题目：Agent Trace 聚合
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
    // 核心方法：aggregate
    static Map<String, Object> aggregate(List<Map<String, Object>> trace) {
        int totalEvents = trace.size();
        int toolCalls = 0;
        int errors = 0;
        double totalDuration = 0.0;
        Map<String, Integer> toolCounts = new LinkedHashMap<>();

        // 循环处理
        for (Map<String, Object> event : trace) {
            Object type = event.get("type");
            // 条件判断
            if ("tool_call".equals(type)) {
                toolCalls++;
                Object tool = event.get("tool");
                // 条件判断
                if (tool != null) {
                    toolCounts.merge(tool.toString(), 1, Integer::sum);
                }
            }
            Object error = event.get("error");
            // 条件判断
            if ("error".equals(type) || Boolean.TRUE.equals(error)) {
                errors++;
            }
            Object duration = event.get("duration_ms");
            // 条件判断
            if (duration instanceof Number) {
                totalDuration += ((Number) duration).doubleValue();
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total_events", totalEvents);
        result.put("tool_calls", toolCalls);
        result.put("errors", errors);
        result.put("total_duration_ms", totalDuration);
        result.put("tool_counts", toolCounts);
        // 返回结果
        return result;
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        List<Map<String, Object>> trace = new ArrayList<>();
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", "tool_call");
        event.put("tool", "search");
        event.put("duration_ms", 12);
        trace.add(event);
        System.out.println(aggregate(trace));
    }
}
```
