# RRF 融合排序

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
from collections import defaultdict


def reciprocal_rank_fusion(rankings, constant=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (constant + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

**追问**：为什么 RRF 不直接使用不同检索器的原始分数？`constant` 如何影响头部结果？

## 第三层：工具与 Agent 运行时

Agent 工程最容易出事故的部分：参数校验、循环守卫、幂等、流式解析。
