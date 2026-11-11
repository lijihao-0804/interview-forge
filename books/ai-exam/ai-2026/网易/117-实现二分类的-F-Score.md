# 实现二分类的 F-Score

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/netease/algo-20260929/" target="_blank" rel="noopener noreferrer">原题解析</a> · 网易 · 2026-09-29 · 算法岗 · ACM 模式（stdin/stdout）

## 题目描述

给定等长的真实标签数组与预测标签数组，元素为 $0$ 或 $1$，计算二分类的 $F_\beta$ 指标。

记 $TP$ 为真实标签与预测标签均为 $1$ 的数量，$FP$ 为真实标签为 $0$、预测标签为 $1$ 的数量，$FN$ 为真实标签为 $1$、预测标签为 $0$ 的数量。精确率与召回率分别为

$$P=\frac{TP}{TP+FP},\qquad R=\frac{TP}{TP+FN}.$$

某个比值的分母为 $0$ 时，该指标取 $0$。最终结果为

$$F_\beta=\frac{(1+\beta^2)PR}{\beta^2P+R}.$$

若 $\beta^2P+R=0$，结果取 $0$。

## 输入描述

三行依次给出真实标签列表、预测标签列表、浮点数 $\beta$。两个列表均为 Python 列表字面量，长度 $n$ 满足 $1\le n\le1000$，且 $0<\beta\le5$。

## 输出描述

输出 F-Score，固定保留三位小数。

## 样例

输入

输出

```text
[1, 1, 0, 0]
[1, 0, 0, 1]
1.0
0.500
```

## 思路分析

第一步：只统计三个计数。 每个样本独立贡献给 $TP$、$FP$、$FN$ 中的一项，或者属于真负例而不影响公式。注意假正例增加精确率的分母，假负例增加召回率的分母，不可交换。

第二步：消去中间分数。 将 $P,R$ 代入后，可把公式写成

$$F_\beta=\frac{(1+\beta^2)TP}{(1+\beta^2)TP+\beta^2FN+FP}.$$

当 $TP=0$ 时，题面定义的最终结果必为 $0$，直接返回即可。当 $TP>0$ 时，原公式涉及的两个计数分母都为正，上述化简合法，最终分母也严格为正。这样无需连续处理三个除零分支。

$\beta>1$ 时对漏掉正例的惩罚更重；$\beta=1$ 时就是 F1。样例中三个计数均为 $1$，代入得到 $0.5$，但输出应为 0.500 。

## 正确性说明

逐项检查两个标签，代码恰好统计定义中的三个互斥事件。$TP=0$ 时按题面零分母约定返回 $0$；否则计算代数等价的计数公式，因此结果与指定 F-Score 一致。

## 题解代码

### Python 实现

```python
# 题目：实现二分类的 F-Score
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(n)，每对标签检查一次；空间 O(n)，用于读入两个列表；计数过程只使用常数个变量

import ast
import sys

input = sys.stdin.readline


# 核心函数：f_score
def f_score(y_true, y_pred, beta):
    tp = fp = fn = 0
    for actual, predicted in zip(y_true, y_pred):
        # 条件判断
        if actual == 1 and predicted == 1:
            tp += 1
        # 条件判断
        elif actual == 0 and predicted == 1:
            fp += 1
        # 条件判断
        elif actual == 1 and predicted == 0:
            fn += 1
    # 条件判断
    if tp == 0:
        # 返回结果
        return 0.0
    b2 = beta * beta
    # 返回结果
    return (1 + b2) * tp / ((1 + b2) * tp + b2 * fn + fp)


# 读取输入并输出答案
def solve():
    y_true = ast.literal_eval(input())
    y_pred = ast.literal_eval(input())
    beta = float(input())
    print(f"{f_score(y_true, y_pred, beta):.3f}")


if __name__ == "__main__":
    solve()
```

## 复杂度分析

时间复杂度 ：$O(n)$，每对标签检查一次。

空间复杂度 ：$O(n)$，用于读入两个列表；计数过程只使用常数个变量。

### Java 实现

```java
// 题目：实现二分类的 F-Score
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(n)，每对标签检查一次；空间 O(n)，用于读入两个列表；计数过程只使用常数个变量

import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static String nextLine() throws IOException { return br.readLine(); }

    // 核心方法：parseInts
    static int[] parseInts(String s) {
        List<Integer> list = new ArrayList<>();
        int i = 0;
        // 循环处理
        while (i < s.length()) {
            char c = s.charAt(i);
            // 条件判断
            if (Character.isDigit(c) || (c == '-' && i + 1 < s.length() && Character.isDigit(s.charAt(i + 1)))) {
                int sign = 1;
                // 条件判断
                if (c == '-') { sign = -1; i++; }
                int val = 0;
                // 循环处理
                while (i < s.length() && Character.isDigit(s.charAt(i))) {
                    val = val * 10 + (s.charAt(i) - '0');
                    i++;
                }
                list.add(sign * val);
            } else {
                i++;
            }
        }
        int[] a = new int[list.size()];
        // 循环处理
        for (int k = 0; k < a.length; k++) a[k] = list.get(k);
        // 返回结果
        return a;
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        int[] yTrue = parseInts(nextLine());
        int[] yPred = parseInts(nextLine());
        double beta = Double.parseDouble(nextLine().trim());
        long tp = 0, fp = 0, fn = 0;
        int len = Math.min(yTrue.length, yPred.length);
        // 枚举位置 i
        for (int i = 0; i < len; i++) {
            int actual = yTrue[i];
            int predicted = yPred[i];
            // 条件判断
            if (actual == 1 && predicted == 1) tp++;
            else if (actual == 0 && predicted == 1) fp++;
            else if (actual == 1 && predicted == 0) fn++;
        }
        double score;
        // 条件判断
        if (tp == 0) {
            score = 0.0;
        } else {
            double b2 = beta * beta;
            score = (1 + b2) * tp / ((1 + b2) * tp + b2 * fn + fp);
        }
        System.out.println(String.format(Locale.US, "%.3f", score));
    }
}
```
