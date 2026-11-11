# LoRA Linear

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：LoRA Linear
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

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

### Java 实现

```java
// 题目：LoRA Linear
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）

import java.util.Random;

final class LoRALinear {
    private final double[][] baseWeight;
    private final double[] baseBias;
    private final double[][] a;
    private final double[][] b;
    private final double scale;

    LoRALinear(double[][] baseWeight, double[] baseBias, int rank, double alpha) {
        this.baseWeight = baseWeight;
        this.baseBias = baseBias;
        int inFeatures = baseWeight[0].length;
        int outFeatures = baseWeight.length;
        this.a = new double[rank][inFeatures];
        this.b = new double[outFeatures][rank];
        Random random = new Random();
        double bound = 1.0 / Math.sqrt(inFeatures);
        for (int i = 0; i < rank; i++) {
            for (int j = 0; j < inFeatures; j++) {
                a[i][j] = (random.nextDouble() * 2.0 - 1.0) * bound;
            }
        }
        this.scale = alpha / rank;
    }

    private static double[][] matmul(double[][] x, double[][] y) {
        int rows = x.length;
        int cols = y[0].length;
        int inner = y.length;
        double[][] out = new double[rows][cols];
        for (int i = 0; i < rows; i++) {
            for (int j = 0; j < cols; j++) {
                double sum = 0.0;
                for (int k = 0; k < inner; k++) {
                    sum += x[i][k] * y[k][j];
                }
                out[i][j] = sum;
            }
        }
        return out;
    }

    private static double[][] transpose(double[][] x) {
        int rows = x.length;
        int cols = x[0].length;
        double[][] out = new double[cols][rows];
        for (int i = 0; i < rows; i++) {
            for (int j = 0; j < cols; j++) {
                out[j][i] = x[i][j];
            }
        }
        return out;
    }

    double[][] forward(double[][] inputs) {
        double[][] delta = matmul(matmul(inputs, transpose(a)), transpose(b));
        double[][] output = matmul(inputs, transpose(baseWeight));
        for (int i = 0; i < output.length; i++) {
            if (baseBias != null) {
                for (int j = 0; j < output[0].length; j++) {
                    output[i][j] += baseBias[j];
                }
            }
        }
        for (int i = 0; i < output.length; i++) {
            for (int j = 0; j < output[0].length; j++) {
                output[i][j] += scale * delta[i][j];
            }
        }
        return output;
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        double[][] weight = {{1.0, 2.0}, {3.0, 4.0}};
        double[] bias = {0.5, -0.5};
        LoRALinear layer = new LoRALinear(weight, bias, 2, 1.0);
        double[][] out = layer.forward(new double[][]{{1.0, 1.0}});
        System.out.println(java.util.Arrays.deepToString(out));
    }
}
```
