# 实现 Transformer 编码器层

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260916/ · 华为 · 2026-09-16 · AI岗

## 题目描述

实现一个标准的 Transformer Encoder Layer。该层依次执行：
多头自注意力； 与输入做残差相加，再做层归一化； 逐位置前馈网络； 再做一次残差相加和层归一化。
本题固定 $d_{model}=4$、注意力头数 $h=2$、每头维度 $d_k=2$，FFN 隐藏维度为 4。$W_Q,W_K,W_V,W_O,W_1,W_2$ 都是 $4\times4$ 单位矩阵，偏置均为 0。两次层归一化的 $\gamma=1$、$\beta=0$、$\varepsilon=10^{-5}$，在最后一维上按总体方差计算。
缩放点积注意力为：

## 输入描述

一行 8 个实数，表示形状为 $(1,2,4)$ 的输入张量按顺序展开后的结果。每个输入在 $[-100,100]$ 内，保留两位小数。

## 输出描述

一行 8 个实数，表示输出张量展开后的结果，每个数保留两位小数。

## 样例 1

输入
输出

```text
11.00 12.00 3.00 1.00 15.00 16.00 10.00 11.00
0.81 1.17 -0.95 -1.04 0.72 1.24 -1.11 -0.85
```

## 样例 2

输入
输出

```text
1.00 2.00 3.00 4.00 5.00 6.00 7.00 8.00
-1.18 -0.59 0.30 1.47 -1.18 -0.59 0.29 1.47
```

## 思路分析

第一步：拆分注意力头。 两个 token 都有 4 维，把前两维交给第一个头、后两维交给第二个头。权重全是单位矩阵，所以 $Q=K=V=X$。
第二步：逐头计算注意力。 对每个查询 token，计算它和两个键的点积，除以 $\sqrt{2}$ 后做数值稳定的 softmax，再对两个值向量加权求和。缩放因子使用每头维度 $d_k$，不是总维度 $d_{model}$。
第三步：完成两次 Post-LN。 拼接两个头的输出，与原输入相加并归一化。FFN 的两个权重都是单位矩阵，所以它退化为逐元素 ReLU；再次残差相加并归一化即可。

## 正确性说明

代码按维度拆出两个互不混合的注意力头，并直接实现缩放点积注意力定义，因此每个头的输出正确。拼接恢复原来的特征顺序后，依题面依次执行残差、层归一化、单位权重 FFN 和第二次残差归一化，所以最终结果与给定编码器层的计算顺序完全一致。

## 题解代码

### Python 实现

```python
import sys
from math import exp, sqrt


D_MODEL = 4
D_K = 2
EPS = 1e-5


def layer_norm(values):
    mean = sum(values) / D_MODEL
    variance = sum((value - mean) ** 2 for value in values) / D_MODEL
    scale = sqrt(variance + EPS)
    return [(value - mean) / scale for value in values]


def solve():
    values = list(map(float, sys.stdin.buffer.read().split()))
    x = [values[:D_MODEL], values[D_MODEL:]]

    head_outputs = []
    for start in (0, D_K):
        head_values = [row[start:start + D_K] for row in x]
        output = []
        for query in head_values:
            scores = [
                sum(a * b for a, b in zip(query, key)) / sqrt(D_K)
                for key in head_values
            ]
            maximum = max(scores)
            weights = [exp(score - maximum) for score in scores]
            total = sum(weights)
            output.append([
                sum(weights[j] * head_values[j][d] for j in range(2)) / total
                for d in range(D_K)
            ])
        head_outputs.append(output)

    attention = [
        head_outputs[0][token] + head_outputs[1][token]
        for token in range(2)
    ]
    hidden = [
        layer_norm([x[token][d] + attention[token][d] for d in range(D_MODEL)])
        for token in range(2)
    ]
    output = [
        layer_norm([value + max(0.0, value) for value in hidden[token]])
        for token in range(2)
    ]

    result = []
    for value in (item for row in output for item in row):
        text = f"{value:.2f}"
        result.append("0.00" if text == "-0.00" else text)
    print(" ".join(result))


solve()
```

## 复杂度分析

时间复杂度 ：一般序列长度为 $T$、模型维度为 $d$ 时，注意力为 $O(T^2d)$，线性层为 $O(Td^2)$；本题 $T=2,d=4$，实际为常数量级。
空间复杂度 ：一般为 $O(T^2h+Td)$；本题参数固定，实际为 $O(1)$。

## 易错点

softmax 前应减去该行最大值，避免指数溢出。 方差除以 4，使用总体方差；不能改成样本方差。 极小负数格式化后可能成为 -0.00 ，题面要求输出 0.00 。
