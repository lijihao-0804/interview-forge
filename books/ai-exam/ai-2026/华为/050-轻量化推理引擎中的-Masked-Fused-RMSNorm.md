# 轻量化推理引擎中的 Masked Fused RMSNorm

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20261014/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-10-14 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

实现融合残差连接、RMSNorm、逐元素缩放、偏置和 padding mask 的算子。共有 $m$ 个样本，向量最大长度为 $n$；所有样本共享缩放向量 $\gamma$、偏置向量 $\beta$ 和稳定项 $\varepsilon$。第 $k$ 个样本给出有效长度 $l_k$、残差系数 $\alpha_k$、输入向量 $x_k$ 和残差向量 $r_k$。

先融合残差：

$$h_{k,i}=x_{k,i}+\alpha_k\cdot r_{k,i}.$$

只对前 $l_k$ 个有效位置统计能量与均方根：

$$energy_k=\sum_{i=1}^{l_k}h_{k,i}^2,\qquad d_k=\max(l_k,1),\qquad RMS_k=\sqrt{\frac{energy_k}{d_k}+\varepsilon}.$$

有效位置缩放并加偏置；padding 位置固定为 0：

$$y_{k,i}=\begin{cases} \gamma_i\cdot h_{k,i}/RMS_k+\beta_i, & 1\le i\le l_k,\\ 0, & l_k<i\le n. \end{cases}$$

输入格式与约束 ：

第一行为 m n epsilon ，$1\le m\le200$，$1\le n\le256$，$0\le\varepsilon\le1$。 第二、三行各有 $n$ 个浮点数，分别为 $\gamma$ 和 $\beta$，每项范围为 $[-10^3,10^3]$。 接下来 $m$ 行，每行格式为 l alpha x_1 ... x_n r_1 ... r_n 。 $0\le l\le n$，$-10^3\le\alpha\le10^3$；$x_i,r_i$ 均在 $[-10^6,10^6]$ 内。 时间限制：C/C++ 1000ms，其他语言 2000ms；内存限制：C/C++ 512MB，其他语言 1024MB。

输出格式 ：每个样本输出一行 y_1 ... y_n | RMS | energy 。各项之间单个空格，竖线两侧各一个空格。所有数保留两位小数，按标准四舍五入；绝对值小于 0.005 时统一输出 0.00 ，避免 -0.00 。

题面边界缺口 ：约束允许 $\varepsilon=0$。若 $l>0$ 且全部有效 $h_i=0$，则 $RMS=0$，有效位置公式出现 $0/0$，题面没有规定结果。下方实现只对公式有定义的输入给出答案；遇到这类未定义输入会明确报错，不擅自把输出规定为 0 或偏置。$l=0$ 时不执行有效位置除法，因此即使 $\varepsilon=0$ 仍有定义。

## 样例 1

输入

输出

```text
2 3 0.01
1.0 0.5 -1.0
0.0 1.0 0.0
3 1.0 3.0 4.0 0.0 0.0 0.0 0.0
2 0.5 -1.0 1.0 -1.0 2.0 -2.0 10.0
1.04 1.69 0.00 | 2.89 | 25.00
0.00 1.00 0.00 | 0.10 | 0.00
```

## 样例 2

输入

输出

```text
2 4 0.000001
1.0 1.0 1.0 1.0
0.0 0.0 0.0 0.0
4 0.0 1.0 2.0 3.0 4.0 0.0 0.0 0.0 0.0
0 1.0 0.0 0.0 0.0 0.0 1.0 2.0 3.0 4.0
0.37 0.73 1.10 1.46 | 2.74 | 30.00
0.00 0.00 0.00 0.00 | 0.00 | 0.00
```

## 思路分析

第一步：确定掩码作用范围。

padding 不参与平方和，输出也不加偏置。可以只计算前 $l$ 个位置的融合值，并将完整输出向量初始化为 0。共享参数按位置索引，不能把缩放向量 $\gamma$ 与样本残差向量 $r$ 混淆。

第二步：按依赖顺序完成计算。

先得到有效位置的 $h$，然后累加 $energy$，再求 $RMS$，最后计算各个有效位置的 $y$。均方的分母是 $\max(l,1)$，不是向量最大长度 $n$；稳定项位于平方根内部。不能先把 RMS 舍入到两位再计算输出，只在最终展示时舍入。

当 $l=0$，平方和为 0，RMS 为 $\sqrt\varepsilon$，输出向量全零。样例 2 的第二个样本 RMS 实际为 0.001，只是打印后显示 0.00。

样例 1 的第一个样本得到 $h=[3,4,0]$、$energy=25$、$RMS=\sqrt{25/3+0.01}$。第二个样本完整融合值为 $[0,0,4]$，最后一个位置是 padding，因此平方和仍为 0；第二个有效位置的输出为偏置 1。

第三步：处理四舍五入和负零。

Python 的 f"{value:.2f}" 在精确中点采用 ties-to-even，并不总等价于题面所写的标准四舍五入。例如精确可表示的 0.125，前者输出 0.12，通常的四舍五入应为 0.13。这里用 Decimal.from_float 保留已经计算出的二进制浮点值，再用 ROUND_HALF_UP 定标到两位小数；计算过程仍使用双精度，最后一步才格式化。绝对值小于 0.005 的值先直接输出 0.00。

题面没有提供恰好半分值的判题样例或特殊容差，因而无法确认隐藏判题是否也严格采用 HALF_UP；本实现按文字要求处理，而不将 ties-to-even 当作同一种规则。二进制浮点值与理想十进制实数之间仍可能有微小差异，这不是增加打印位数能够完全消除的。

## 题解代码

### Python 实现

```python
# 题目：轻量化推理引擎中的 Masked Fused RMSNorm
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(mn)；空间 O(n)

import math
import sys
from decimal import Decimal, ROUND_HALF_UP
input = sys.stdin.readline


# 核心函数：format_value
def format_value(value):
    # 条件判断
    if abs(value) < 0.005:
        # 返回结果
        return "0.00"
    rounded = Decimal.from_float(value).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # 返回结果
    return format(rounded, ".2f")


# 核心函数：masked_rms_norm
def masked_rms_norm(length, alpha, x, residual, gamma, beta, epsilon):
    fused = [x[i] + alpha * residual[i] for i in range(length)]
    energy = sum(value * value for value in fused)
    rms = math.sqrt(energy / max(length, 1) + epsilon)
    # 条件判断
    if length > 0 and rms == 0.0:
        raise ValueError("题面未定义：有效长度非零且 RMS 为零")
    output = [0.0] * len(x)
    # 枚举位置 i
    for i in range(length):
        output[i] = gamma[i] * (fused[i] / rms) + beta[i]
    # 返回结果
    return output, rms, energy


# 读取输入并输出答案
def solve():
    first = input().split()
    m, n = int(first[0]), int(first[1])
    epsilon = float(first[2])
    gamma = list(map(float, input().split()))
    beta = list(map(float, input().split()))
    # 遍历 _
    for _ in range(m):
        tokens = input().split()
        length, alpha = int(tokens[0]), float(tokens[1])
        x = list(map(float, tokens[2:2 + n]))
        residual = list(map(float, tokens[2 + n:2 + 2 * n]))
        output, rms, energy = masked_rms_norm(
            length, alpha, x, residual, gamma, beta, epsilon
        )
        print(" ".join(format_value(value) for value in output)
              + " | " + format_value(rms) + " | " + format_value(energy))


if __name__ == "__main__":
    solve()
```

## 复杂度分析

时间复杂度 ：$O(mn)$。每个样本读取长度为 $n$ 的向量，计算有效位置，并输出 $n$ 个结果；题面数值范围有限，格式化每个数的开销可视为常数。

空间复杂度 ：$O(n)$。逐行处理样本，只保留共享向量和当前样本的输入、有效融合值、输出，不保存全部样本。

### Java 实现

```java
// 题目：轻量化推理引擎中的 Masked Fused RMSNorm
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(mn)；空间 O(n)

import java.io.*;
import java.util.*;
import java.math.BigDecimal;
import java.math.RoundingMode;

public class Main {
    static class In {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        StringTokenizer st = new StringTokenizer("");
        String next() { while (!st.hasMoreTokens()) { String l=null; try { l=br.readLine(); } catch (IOException e) { throw new RuntimeException(e); } if (l==null) return null; st=new StringTokenizer(l); } return st.nextToken(); }
        int ni() { return Integer.parseInt(next()); }
        double nd() { return Double.parseDouble(next()); }
    }
    // 核心方法：formatValue
    static String formatValue(double value) {
        // 条件判断
        if (Math.abs(value) < 0.005) return "0.00";
        BigDecimal bd = new BigDecimal(value);
        bd = bd.setScale(2, RoundingMode.HALF_UP);
        // 返回结果
        return bd.toPlainString();
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        In in = new In();
        int m = in.ni();
        int n = in.ni();
        double epsilon = in.nd();
        double[] gamma = new double[n];
        double[] beta = new double[n];
        // 枚举位置 i
        for (int i = 0; i < n; i++) gamma[i] = in.nd();
        // 枚举位置 i
        for (int i = 0; i < n; i++) beta[i] = in.nd();
        StringBuilder out = new StringBuilder();
        // 循环处理
        for (int row = 0; row < m; row++) {
            int length = in.ni();
            double alpha = in.nd();
            double[] x = new double[n];
            double[] residual = new double[n];
            // 枚举位置 i
            for (int i = 0; i < n; i++) x[i] = in.nd();
            // 枚举位置 i
            for (int i = 0; i < n; i++) residual[i] = in.nd();
            double[] fused = new double[length];
            double energy = 0.0;
            // 枚举位置 i
            for (int i = 0; i < length; i++) { fused[i] = x[i] + alpha * residual[i]; energy += fused[i] * fused[i]; }
            double rms = Math.sqrt(energy / Math.max(length, 1) + epsilon);
            double[] output = new double[n];
            // 枚举位置 i
            for (int i = 0; i < length; i++) output[i] = gamma[i] * (fused[i] / rms) + beta[i];
            StringBuilder line = new StringBuilder();
            // 枚举位置 i
            for (int i = 0; i < n; i++) { if (i > 0) line.append(' '); line.append(formatValue(output[i])); }
            line.append(" | ").append(formatValue(rms)).append(" | ").append(formatValue(energy));
            out.append(line).append((char)10);
        }
        System.out.print(out.toString());
    }
}
```
