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
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class FileConflictDetector {
    static final class Edit {
        final String agent;
        final String path;

        Edit(String agent, String path) {
            this.agent = agent;
            this.path = path;
        }
    }

    static List<String> detectConflicts(List<Edit> edits) {
        Map<String, Set<String>> agentsByPath = new LinkedHashMap<>();
        for (Edit edit : edits) {
            agentsByPath.computeIfAbsent(edit.path, key -> new LinkedHashSet<>()).add(edit.agent);
        }
        List<String> conflicts = new ArrayList<>();
        for (Map.Entry<String, Set<String>> entry : agentsByPath.entrySet()) {
            if (entry.getValue().size() > 1) {
                conflicts.add(entry.getKey());
            }
        }
        return conflicts;
    }

    public static void main(String[] args) {
        List<Edit> edits = new ArrayList<>();
        edits.add(new Edit("agent-a", "src/Main.java"));
        edits.add(new Edit("agent-b", "src/Main.java"));
        edits.add(new Edit("agent-a", "README.md"));
        System.out.println(detectConflicts(edits));
    }
}
```
