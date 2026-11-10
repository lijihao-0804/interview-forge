# LoRA Linear

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
import torch
from torch import nn


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, rank: int, alpha: float = 1.0):
        super().__init__()
        self.base = base
        self.base.weight.requires_grad_(False)
        if self.base.bias is not None:
            self.base.bias.requires_grad_(False)
        self.a = nn.Parameter(torch.empty(rank, base.in_features))
        self.b = nn.Parameter(torch.zeros(base.out_features, rank))
        nn.init.kaiming_uniform_(self.a, a=5 ** 0.5)
        self.scale = alpha / rank

    def forward(self, inputs):
        delta = (inputs @ self.a.T) @ self.b.T
        return self.base(inputs) + self.scale * delta
```

**追问**：为什么 B 通常初始化为零？推理时如何 Merge？Rank 越大一定越好吗？

## 第二层：检索与排序

RAG 链路里的核心组件，考察工程实现与边界处理。
