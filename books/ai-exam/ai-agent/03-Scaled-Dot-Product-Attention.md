# Scaled Dot-Product Attention

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
import math


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def attention(query, keys, values):
    dimension = len(query)
    scores = [dot(query, key) / math.sqrt(dimension) for key in keys]
    weights = softmax(scores)
    output = [0.0] * len(values[0])
    for weight, value in zip(weights, values):
        for index, number in enumerate(value):
            output[index] += weight * number
    return output, weights
```

**追问**：Mask 加在哪里？为什么除以 `sqrt(d_k)`？Multi-Head 如何拆分和合并？
