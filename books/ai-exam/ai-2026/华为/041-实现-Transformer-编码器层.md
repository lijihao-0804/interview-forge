# 实现 Transformer 编码器层

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260916/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-09-16 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

实现一个标准的 Transformer Encoder Layer。该层依次执行：

多头自注意力； 与输入做残差相加，再做层归一化； 逐位置前馈网络； 再做一次残差相加和层归一化。

本题固定 $d_{model}=4$、注意力头数 $h=2$、每头维度 $d_k=2$，FFN 隐藏维度为 4。$W_Q,W_K,W_V,W_O,W_1,W_2$ 都是 $4\times4$ 单位矩阵，偏置均为 0。两次层归一化的 $\gamma=1$、$\beta=0$、$\varepsilon=10^{-5}$，在最后一维上按总体方差计算。

缩放点积注意力为：

$$\operatorname{Attention}(Q,K,V)=\operatorname{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$

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
# 题目：实现 Transformer 编码器层
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 一般序列长度为 T、模型维度为 d 时，注意力为 O(T^2d)，线性层为 O(Td^2)；本题 T=2,d=4，实际为常数量级；空间 一般为 O(T^2h+Td)；本题参数固定，实际为 O(1)

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


# 读取输入并输出答案
):
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

### Java 实现

```java
// 题目：实现 Transformer 编码器层
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 一般序列长度为 T、模型维度为 d 时，注意力为 O(T^2d)，线性层为 O(Td^2)；本题 T=2,d=4，实际为常数量级；空间 一般为 O(T^2h+Td)；本题参数固定，实际为 O(1)

import java.io.*;
import java.util.*;
import java.util.Locale;

public class Main {
    static final int D_MODEL = 4;
    static final int D_K = 2;
    static final double EPS = 1e-5;
    static class In {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        StringTokenizer st = new StringTokenizer("");
        String next() { while (!st.hasMoreTokens()) { String l=null; try { l=br.readLine(); } catch (IOException e) { throw new RuntimeException(e); } if (l==null) return null; st=new StringTokenizer(l); } return st.nextToken(); }
        double nd() { return Double.parseDouble(next()); }
    }
    static double[] layerNorm(double[] values) {
        double mean = 0.0;
        for (double v : values) mean += v;
        mean /= D_MODEL;
        double variance = 0.0;
        for (double v : values) variance += (v - mean) * (v - mean);
        variance /= D_MODEL;
        double scale = Math.sqrt(variance + EPS);
        double[] out = new double[D_MODEL];
        for (int i = 0; i < D_MODEL; i++) out[i] = (values[i] - mean) / scale;
        return out;
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        In in = new In();
        double[] values = new double[2 * D_MODEL];
        for (int i = 0; i < values.length; i++) values[i] = in.nd();
        double[][] x = new double[2][D_MODEL];
        for (int i = 0; i < D_MODEL; i++) x[0][i] = values[i];
        for (int i = 0; i < D_MODEL; i++) x[1][i] = values[D_MODEL + i];
        double[][][] headOut = new double[2][2][D_K];
        for (int hi = 0; hi < 2; hi++) {
            int start = hi * D_K;
            double[][] headValues = new double[2][D_K];
            for (int tok = 0; tok < 2; tok++) for (int d = 0; d < D_K; d++) headValues[tok][d] = x[tok][start + d];
            for (int qi = 0; qi < 2; qi++) {
                double[] scores = new double[2];
                for (int kj = 0; kj < 2; kj++) {
                    double dot = 0.0;
                    for (int d = 0; d < D_K; d++) dot += headValues[qi][d] * headValues[kj][d];
                    scores[kj] = dot / Math.sqrt(D_K);
                }
                double maximum = scores[0];
                for (int kj = 1; kj < 2; kj++) if (scores[kj] > maximum) maximum = scores[kj];
                double[] w = new double[2];
                double total = 0.0;
                for (int kj = 0; kj < 2; kj++) { w[kj] = Math.exp(scores[kj] - maximum); total += w[kj]; }
                for (int d = 0; d < D_K; d++) {
                    double sum = 0.0;
                    for (int kj = 0; kj < 2; kj++) sum += w[kj] * headValues[kj][d];
                    headOut[hi][qi][d] = sum / total;
                }
            }
        }
        double[][] attention = new double[2][D_MODEL];
        for (int tok = 0; tok < 2; tok++) {
            for (int d = 0; d < D_K; d++) {
                attention[tok][d] = headOut[0][tok][d];
                attention[tok][D_K + d] = headOut[1][tok][d];
            }
        }
        double[][] hidden = new double[2][D_MODEL];
        for (int tok = 0; tok < 2; tok++) {
            double[] pre = new double[D_MODEL];
            for (int d = 0; d < D_MODEL; d++) pre[d] = x[tok][d] + attention[tok][d];
            hidden[tok] = layerNorm(pre);
        }
        double[][] output = new double[2][D_MODEL];
        for (int tok = 0; tok < 2; tok++) {
            double[] pre = new double[D_MODEL];
            for (int d = 0; d < D_MODEL; d++) pre[d] = hidden[tok][d] + Math.max(0.0, hidden[tok][d]);
            output[tok] = layerNorm(pre);
        }
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (int tok = 0; tok < 2; tok++) {
            for (int d = 0; d < D_MODEL; d++) {
                String text = String.format(Locale.US, "%.2f", output[tok][d]);
                if (text.equals("-0.00")) text = "0.00";
                if (!first) sb.append(' ');
                first = false;
                sb.append(text);
            }
        }
        System.out.println(sb.toString());
    }
}
```
