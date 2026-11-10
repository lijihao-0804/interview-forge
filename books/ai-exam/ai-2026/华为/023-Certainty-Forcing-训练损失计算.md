# Certainty Forcing 训练损失计算

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260701/ · 华为 · 2026-07-01 · AI岗

## 题目描述

给定 $N$ 个 token，词表大小 $V$，每个 token 有 logits 向量 $z$、正确标签 $y$、稳定性影响值 $c$。需要：
对每个 token 计算 softmax 概率，得到基础交叉熵 $\text{CE}_i = -\log p_i[y_i]$ 和预测分布熵 $H_i = -\sum_j p_j \log p_j$ 在总稳定性影响不超过上限 $B$ 的约束下，选择一部分 token 使其交叉熵之和最大（0/1 背包） 最终总损失 = 基础损失之和 + $\lambda \times$ 被选 token 的熵之和
对数一律使用自然对数，结果保留两位小数。

## 样例

输入
输出
输入
输出

```text
4 4 4 0.80
3.00 1.00 0.00 -1.00 0 2
0.00 1.00 3.00 0.00 2 2
1.00 1.00 1.00 1.00 1 3
2.00 0.00 1.00 2.00 3 1
4.75
3 3 3 0.50
2.00 1.00 0.00 0 2
0.00 2.00 1.00 1 1
1.00 1.00 1.00 2 2
2.88
```

## 思路分析

第一步：数值稳定的 softmax 与交叉熵
直接对 logits 取指数可能上溢，先减去每个 token 的最大 logit 值 $m$ 再取指数。交叉熵可以化简为 $\text{CE} i = -(z {y_i} - m) + \log(\sum e^{z_j - m})$，避免先算概率再取对数的精度损失。
第二步：分布熵的计算
熵看的是整个词表的概率分布：$H_i = -\sum_j p_j \log p_j$。这里 $p_j = e^{z_j - m} / \sum e^{z_k - m}$。
第三步：0/1 背包建模
基础损失 $\sum \text{CE}_i$ 恒定不变，增强项只由被选集合决定。令价值 = 交叉熵、重量 = 影响值、容量 = $B$，”选出交叉熵之和最大的合法子集”就是标准 0/1 背包。关键是求出最优子集后，需要同步搬运该子集对应的熵之和——在 DP 更新价值时，同步更新一个附属数组 $g$ 记录对应的熵之和。
第四步：最终答案
$\text{total} = \text{base} + \lambda \cdot g[B]$，四舍五入保留两位小数。

## 题解代码

### Python 实现

```python
import sys
import math
input = sys.stdin.readline

def solve():
    first = input().split()
    N = int(first[0]); V = int(first[1]); B = int(first[2]); lam = float(first[3])
    base = 0.0
    items = []
    for _ in range(N):
        row = input().split()
        z = [float(row[j]) for j in range(V)]
        y = int(row[V]); c = int(row[V + 1])
        m = max(z)
        exps = [math.exp(v - m) for v in z]
        s = sum(exps)
        ce = -(z[y] - m) + math.log(s)
        H = 0.0
        for e in exps:
            p = e / s
            if p > 0.0:
                H -= p * math.log(p)
        base += ce
        items.append((ce, c, H))
    # 0/1 背包：容量 B，重量 c，价值 ce，同步搬运熵
    f = [0.0] * (B + 1)
    g = [0.0] * (B + 1)
    for ce, c, H in items:
        for b in range(B, c - 1, -1):
            cand = f[b - c] + ce
            if cand > f[b]:
                f[b] = cand
                g[b] = g[b - c] + H
    total = base + lam * g[B]
    print(f"{total:.2f}")

solve()
```

## 复杂度分析

时间复杂度 ：$O(NV + NB)$，softmax 与熵 $O(NV)$，背包 $O(NB)$。 空间复杂度 ：$O(B + NV)$。
