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
