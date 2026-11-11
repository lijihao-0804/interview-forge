# 带循环守卫的 ReAct Agent

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：带循环守卫的 ReAct Agent
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

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

### Java 实现

```java
// 题目：带循环守卫的 ReAct Agent
// 算法：排序 + 扫描
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
    interface Model {
        Map<String, Object> decide(List<Map<String, Object>> messages, List<String> toolNames);
    }

    interface Tool {
        Object run(Map<String, Object> arguments) throws Exception;
    }

    // 核心方法：runAgent
    static Map<String, Object> runAgent(Model model, Map<String, Tool> tools, String objective) {
        // 返回结果
        return runAgent(model, tools, objective, 12, 2);
    }

    // 核心方法：runAgent
    static Map<String, Object> runAgent(Model model, Map<String, Tool> tools, String objective, int maxSteps, int repeatLimit) {
        List<Map<String, Object>> messages = new ArrayList<>();
        Map<String, Object> userMessage = new LinkedHashMap<>();
        userMessage.put("role", "user");
        userMessage.put("content", objective);
        messages.add(userMessage);

        Map<String, Integer> counts = new HashMap<>();
        // 循环处理
        for (int step = 0; step < maxSteps; step++) {
            Map<String, Object> decision = model.decide(messages, new ArrayList<>(tools.keySet()));
            // 条件判断
            if ("final".equals(decision.get("type"))) {
                Map<String, Object> completed = new LinkedHashMap<>();
                completed.put("status", "completed");
                completed.put("answer", decision.get("answer"));
                completed.put("steps", step);
                // 返回结果
                return completed;
            }

            String fingerprint = actionFingerprint(decision);
            int count = counts.getOrDefault(fingerprint, 0) + 1;
            counts.put(fingerprint, count);
            // 条件判断
            if (count > repeatLimit) {
                Map<String, Object> blocked = new LinkedHashMap<>();
                blocked.put("status", "blocked");
                blocked.put("reason", "repeated_action");
                blocked.put("action", decision);
                // 返回结果
                return blocked;
            }

            Object toolName = decision.get("tool");
            Tool tool = toolName == null ? null : tools.get(toolName.toString());
            Map<String, Object> observation = new LinkedHashMap<>();
            // 条件判断
            if (tool == null) {
                observation.put("ok", false);
                observation.put("error", "unknown_tool");
            } else {
                try {
                    Object result = tool.run(arguments(decision.get("arguments")));
                    observation.put("ok", true);
                    observation.put("result", result);
                } catch (Exception exception) {
                    observation.put("ok", false);
                    observation.put("error", exception.getClass().getSimpleName());
                }
            }

            Map<String, Object> assistantMessage = new LinkedHashMap<>();
            assistantMessage.put("role", "assistant");
            assistantMessage.put("content", decision);
            messages.add(assistantMessage);

            Map<String, Object> toolMessage = new LinkedHashMap<>();
            toolMessage.put("role", "tool");
            toolMessage.put("content", observation);
            messages.add(toolMessage);
        }

        Map<String, Object> blocked = new LinkedHashMap<>();
        blocked.put("status", "blocked");
        blocked.put("reason", "step_budget_exhausted");
        // 返回结果
        return blocked;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> arguments(Object value) {
        // 条件判断
        if (value instanceof Map) {
            // 返回结果
            return (Map<String, Object>) value;
        }
        // 返回结果
        return new LinkedHashMap<>();
    }

    // 核心方法：actionFingerprint
    static String actionFingerprint(Map<String, Object> action) {
        StringBuilder builder = new StringBuilder();
        writeJson(builder, action, true);
        // 返回结果
        return builder.toString();
    }

    @SuppressWarnings("unchecked")
    private static void writeJson(StringBuilder builder, Object value, boolean sortKeys) {
        // 条件判断
        if (value == null) {
            builder.append("null");
        } else if (value instanceof String) {
            writeString(builder, (String) value);
        } else if (value instanceof Number || value instanceof Boolean) {
            builder.append(value.toString());
        } else if (value instanceof Map) {
            Map<String, Object> map = (Map<String, Object>) value;
            List<String> keys = new ArrayList<>(map.keySet());
            // 条件判断
            if (sortKeys) {
                Collections.sort(keys);
            }
            builder.append('{');
            boolean first = true;
            // 循环处理
            for (String key : keys) {
                // 条件判断
                if (!first) {
                    builder.append(", ");
                }
                writeString(builder, key);
                builder.append(": ");
                writeJson(builder, map.get(key), sortKeys);
                first = false;
            }
            builder.append('}');
        } else if (value instanceof Iterable) {
            builder.append('[');
            boolean first = true;
            // 循环处理
            for (Object item : (Iterable<Object>) value) {
                // 条件判断
                if (!first) {
                    builder.append(", ");
                }
                writeJson(builder, item, sortKeys);
                first = false;
            }
            builder.append(']');
        } else {
            writeString(builder, value.toString());
        }
    }

    private static void writeString(StringBuilder builder, String value) {
        builder.append((char) 34);
        // 枚举位置 i
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            // 条件判断
            if (c == (char) 34 || c == (char) 92) {
                builder.append((char) 92).append(c);
            } else if (c == (char) 10) {
                builder.append((char) 92).append('n');
            } else if (c == (char) 13) {
                builder.append((char) 92).append('r');
            } else if (c == (char) 9) {
                builder.append((char) 92).append('t');
            } else {
                builder.append(c);
            }
        }
        builder.append((char) 34);
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        Map<String, Tool> tools = new LinkedHashMap<>();
        tools.put("echo", arguments -> arguments.get("text"));
        Model model = (messages, toolNames) -> {
            Map<String, Object> decision = new LinkedHashMap<>();
            decision.put("type", "final");
            decision.put("answer", "done");
            // 返回结果
            return decision;
        };
        System.out.println(runAgent(model, tools, "hello"));
    }
}
```
