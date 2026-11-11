# Expert Choice Routing

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260612/ · 华为 · 2026-06-12 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

混合专家模型（MoE）中，Expert Choice Routing 让每个专家主动选择得分最高的 Top-$S$ 个 Token，保持天然的负载均衡。要求不调用深度学习库，仅用 NumPy 实现以下四步：

门控分数与归一化权重 ：计算 $G = X \cdot W_g$，对每个 token 在专家维度上做数值稳定 softmax 每个专家选 Top-S ：按归一化权重选最高的 $S$ 个 token，权重相等时优先序号小的 专家变换与加权聚合 ：被选中的 token 做对应专家的线性变换并以权重加权累加 零向量补全 ：未被任何专家选中的 token 输出为全零向量

输入约束：$N, d, E, S$ 须均为正整数且 $S \leq N$，否则只输出一个 $0$。

## 样例

输入

输出

```text
4 3 2 3
1.0 0.5 0.2
0.8 0.3 0.9
0.2 0.7 0.4
0.5 0.1 0.6
0.3 0.7
0.5 0.2
0.2 0.1
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
0.5 0.0 0.0
0.0 0.5 0.0
0.0 0.0 0.5
0.28 0.14 0.06
0.59 0.22 0.66
0.11 0.38 0.22
0.37 0.07 0.44
```

## 思路分析

第一步：观察题目性质

本题是一道矩阵运算模拟题，不涉及训练，只需照定义完成一次前向路由。所有比较的平局规则都钉死了，结果唯一。

第二步：数值稳定 Softmax

计算 $G = X \cdot W_g$ 得到 $(N, E)$ 的分数矩阵后，对每个 token 在专家维度上做 softmax。关键是减去行最大值：$\exp(g_{ie} - \max_j g_{ij})$，避免指数运算上溢为 inf。

第三步：每个专家选 Top-S

对专家 $e$，取其权重列中值最大的 $S$ 个 token。按 $(-\text{weight}, \text{index})$ 排序后取前 $S$ 个，即可在权重降序的同时让”权重相等取序号小”自动成立。

第四步：加权聚合

若 token $i$ 被专家集合 $\mathcal{E}_i$ 选中，则输出为：

把输出矩阵 $Y$ 初始化为全零，没被任何专家选中的 token 自然保持零向量。

第五步：合法性校验

进入计算流程前先检查 $N, d, E, S$ 是否均为正整数且 $S \leq N$，不满足则直接输出 $0$。

## 题解代码

### Python 实现

```python
# 题目：Expert Choice Routing
# 算法：排序 + 扫描
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(N \cdot d \cdot E + E \cdot S \cdot d^2)，门控分数 O(N \cdot d \cdot E)，聚合阶段共 E \cdot S 次 token 变换、每次 O(d^2) 空间复杂度 ：O(N \cdot E + E \cdot d^2)，分别存储权重矩阵和所有专家变换矩阵；空间 O(N \cdot E + E \cdot d^2)，分别存储权重矩阵和所有专家变换矩阵

import sys
import numpy as np

def fmt2(v):
    s = f"{v:.2f}"
    return "0.00" if s == "-0.00" else s

data = sys.stdin.read().split()
n = int(data[0]); d = int(data[1]); e = int(data[2]); s = int(data[3])
if n < 1 or d < 1 or e < 1 or s < 1 or s > n:
    print("0")
    sys.exit(0)

pos = 4
X = np.array(data[pos:pos + n * d], dtype=float).reshape(n, d); pos += n * d
Wg = np.array(data[pos:pos + d * e], dtype=float).reshape(d, e); pos += d * e
We = []
for _ in range(e):
    We.append(np.array(data[pos:pos + d * d], dtype=float).reshape(d, d))
    pos += d * d

scores = X @ Wg
m = scores.max(axis=1, keepdims=True)
expv = np.exp(scores - m)
W = expv / expv.sum(axis=1, keepdims=True)

Y = np.zeros((n, d))
for ee in range(e):
    col = W[:, ee]
    chosen = sorted(range(n), key=lambda i: (-col[i], i))[:s]
    for i in chosen:
        Y[i] += col[i] * (X[i] @ We[ee])

print("\n".join(" ".join(fmt2(v) for v in row) for row in Y))
```

## 复杂度分析

时间复杂度 ：$O(N \cdot d \cdot E + E \cdot S \cdot d^2)$，门控分数 $O(N \cdot d \cdot E)$，聚合阶段共 $E \cdot S$ 次 token 变换、每次 $O(d^2)$

空间复杂度 ：$O(N \cdot E + E \cdot d^2)$，分别存储权重矩阵和所有专家变换矩阵

### Java 实现

```java
// 题目：Expert Choice Routing
// 算法：排序 + 扫描
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(N \cdot d \cdot E + E \cdot S \cdot d^2)，门控分数 O(N \cdot d \cdot E)，聚合阶段共 E \cdot S 次 token 变换、每次 O(d^2) 空间复杂度 ：O(N \cdot E + E \cdot d^2)，分别存储权重矩阵和所有专家变换矩阵；空间 O(N \cdot E + E \cdot d^2)，分别存储权重矩阵和所有专家变换矩阵

import java.util.*;
public class Main {
    static String fmt2(double v) { String t = String.format(Locale.US, "%.2f", v); return t.equals("-0.00") ? "0.00" : t; }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt(), d = sc.nextInt(), e = sc.nextInt(), s = sc.nextInt();
        if (n < 1 || d < 1 || e < 1 || s < 1 || s > n) { System.out.println("0"); return; }
        double[][] X = new double[n][d];
        for (int i = 0; i < n; i++) for (int j = 0; j < d; j++) X[i][j] = sc.nextDouble();
        double[][] Wg = new double[d][e];
        for (int i = 0; i < d; i++) for (int j = 0; j < e; j++) Wg[i][j] = sc.nextDouble();
        double[][][] We = new double[e][d][d];
        for (int ee = 0; ee < e; ee++) for (int i = 0; i < d; i++) for (int j = 0; j < d; j++) We[ee][i][j] = sc.nextDouble();
        double[][] scores = new double[n][e];
        for (int i = 0; i < n; i++) for (int ee = 0; ee < e; ee++) { double sum = 0; for (int k = 0; k < d; k++) sum += X[i][k] * Wg[k][ee]; scores[i][ee] = sum; }
        double[][] W = new double[n][e];
        for (int i = 0; i < n; i++) {
            double mx = Double.NEGATIVE_INFINITY;
            for (int ee = 0; ee < e; ee++) if (scores[i][ee] > mx) mx = scores[i][ee];
            double sum = 0;
            for (int ee = 0; ee < e; ee++) { double v = Math.exp(scores[i][ee] - mx); W[i][ee] = v; sum += v; }
            for (int ee = 0; ee < e; ee++) W[i][ee] /= sum;
        }
        double[][] Y = new double[n][d];
        for (int ee = 0; ee < e; ee++) {
            Integer[] idx = new Integer[n];
            for (int i = 0; i < n; i++) idx[i] = i;
            final double[][] Wf = W; final int col = ee;
            Arrays.sort(idx, (a, b) -> { int c = Double.compare(Wf[b][col], Wf[a][col]); if (c != 0) return c; return Integer.compare(a, b); });
            for (int t = 0; t < s; t++) {
                int i = idx[t]; double coef = W[i][ee];
                double[] xw = new double[d];
                for (int k = 0; k < d; k++) { double sum = 0; for (int j = 0; j < d; j++) sum += X[i][j] * We[ee][j][k]; xw[k] = sum; }
                for (int k = 0; k < d; k++) Y[i][k] += coef * xw[k];
            }
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < n; i++) { if (i > 0) sb.append((char)10); for (int k = 0; k < d; k++) { if (k > 0) sb.append(' '); sb.append(fmt2(Y[i][k])); } }
        System.out.println(sb);
    }
}
```
