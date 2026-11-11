# Tool 参数校验

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：Tool 参数校验
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

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

### Java 实现

```java
// 题目：Tool 参数校验
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
    static final Map<String, Map<String, Object>> TOOLS = new LinkedHashMap<>();

    static {
        Map<String, Object> getWeather = new LinkedHashMap<>();
        getWeather.put("required", new LinkedHashSet<>(Arrays.asList("city")));
        getWeather.put("allowed", new LinkedHashSet<>(Arrays.asList("city", "date")));
        getWeather.put("risk", "read");
        TOOLS.put("get_weather", getWeather);

        Map<String, Object> sendEmail = new LinkedHashMap<>();
        sendEmail.put("required", new LinkedHashSet<>(Arrays.asList("to", "subject", "body")));
        sendEmail.put("allowed", new LinkedHashSet<>(Arrays.asList("to", "subject", "body")));
        sendEmail.put("risk", "write");
        TOOLS.put("send_email", sendEmail);
    }

    @SuppressWarnings("unchecked")
    // 核心方法：validateToolCall
    static List<String> validateToolCall(String name, Map<String, ?> arguments) {
        Map<String, Object> spec = TOOLS.get(name);
        // 条件判断
        if (spec == null) {
            List<String> unknown = new ArrayList<>();
            unknown.add("unknown tool");
            // 返回结果
            return unknown;
        }
        List<String> errors = new ArrayList<>();
        Set<String> required = (Set<String>) spec.get("required");
        Set<String> allowed = (Set<String>) spec.get("allowed");
        Set<String> provided = arguments == null ? new LinkedHashSet<>() : new LinkedHashSet<>(arguments.keySet());
        Set<String> missing = new TreeSet<>(required);
        missing.removeAll(provided);
        Set<String> extra = new TreeSet<>(provided);
        extra.removeAll(allowed);
        // 条件判断
        if (!missing.isEmpty()) {
            errors.add("missing: " + pyList(missing));
        }
        // 条件判断
        if (!extra.isEmpty()) {
            errors.add("unexpected: " + pyList(extra));
        }
        // 条件判断
        if ("write".equals(spec.get("risk"))) {
            errors.add("approval required");
        }
        // 返回结果
        return errors;
    }

    private static String pyList(Set<String> values) {
        StringBuilder builder = new StringBuilder("[");
        boolean first = true;
        // 循环处理
        for (String value : values) {
            // 条件判断
            if (!first) {
                builder.append(", ");
            }
            builder.append('\'').append(value).append('\'');
            first = false;
        }
        builder.append(']');
        // 返回结果
        return builder.toString();
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        Map<String, Object> arguments = new LinkedHashMap<>();
        arguments.put("city", "Beijing");
        System.out.println(validateToolCall("get_weather", arguments));
        System.out.println(validateToolCall("send_email", arguments));
    }
}
```
