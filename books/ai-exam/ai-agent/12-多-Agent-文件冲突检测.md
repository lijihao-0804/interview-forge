# 多 Agent 文件冲突检测

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

给定多个 Agent 的修改清单：

```json
[
  {"agent": "backend", "files": ["api.py", "schema.py"]},
  {"agent": "test", "files": ["test_api.py", "schema.py"]}
]
```

输出：

- 文件所有者；
- 冲突文件；
- 可以并行的任务组；
- 建议的合并顺序。

**追问**：文件不冲突但接口语义冲突怎么办？为什么需要 Task Contract 和集成测试？

### Java 实现

```java
// 题目：多 Agent 文件冲突检测
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
    static final class Edit {
        final String agent;
        final String path;

        Edit(String agent, String path) {
            this.agent = agent;
            this.path = path;
        }
    }

    // 核心方法：detectConflicts
    static List<String> detectConflicts(List<Edit> edits) {
        Map<String, Set<String>> agentsByPath = new LinkedHashMap<>();
        // 循环处理
        for (Edit edit : edits) {
            agentsByPath.computeIfAbsent(edit.path, key -> new LinkedHashSet<>()).add(edit.agent);
        }
        List<String> conflicts = new ArrayList<>();
        // 循环处理
        for (Map.Entry<String, Set<String>> entry : agentsByPath.entrySet()) {
            // 条件判断
            if (entry.getValue().size() > 1) {
                conflicts.add(entry.getKey());
            }
        }
        // 返回结果
        return conflicts;
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        List<Edit> edits = new ArrayList<>();
        edits.add(new Edit("agent-a", "src/Main.java"));
        edits.add(new Edit("agent-b", "src/Main.java"));
        edits.add(new Edit("agent-a", "README.md"));
        System.out.println(detectConflicts(edits));
    }
}
```
