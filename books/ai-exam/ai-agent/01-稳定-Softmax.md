# 稳定 Softmax

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

**要求**：实现一维 Softmax，避免大数溢出。

### Python 实现

```python
import math


def softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    maximum = max(values)
    exps = [math.exp(value - maximum) for value in values]
    total = sum(exps)
    return [value / total for value in exps]
```

**追问**：为什么减去最大值不改变结果？如何扩展到二维 Batch？
