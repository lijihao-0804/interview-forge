# 流水线并行最小化最大 Stage 负载

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260918/ · 华为 · 2026-09-18 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

某深度学习团队正在训练一个大型神经网络，需要将模型的 $N$ 个层划分到 $K$ 个 GPU 上进行流水线并行训练。为了保证流水线效率，需要让各 GPU 的负载尽可能均衡。

流水线并行 ：把模型按层切分为 $K$ 个部分，每个部分称为一个 Stage，分配给一个 GPU。训练时，多个微批次在流水线中接力执行：第一个微批次在 GPU0 完成前向计算后传递给 GPU1，同时 GPU0 开始处理第二个微批次，以此类推。

Stage 负载 ：一个 Stage 的负载定义为该 Stage 内所有层的前向传播时间之和。若 Stage $s$ 包含层 $l_{1},l_{1}+1,\dots,l_{2}$，则

其中 $f[i]$ 是第 $i$ 层的前向传播时间。

气泡问题 ：流水线执行过程中，如果某个 Stage 负载明显高于其他 Stage，其他 GPU 就需要等待它完成，产生空闲时间，称为「气泡」。最大负载决定了气泡的上界，因此需要最小化最大负载。

划分约束 ：每个 Stage 内的层编号必须连续；每层恰好属于一个 Stage；每个 Stage 至少包含一层。

## 输入描述

第一行两个整数 $N,K$，分别表示模型的层数和划分的 Stage 数，满足 $1\le K\le N\le500$。

第二行 $N$ 个整数 $f[0],f[1],\dots,f[N-1]$，$f[i]$ 表示第 $i$ 层的前向传播时间（毫秒），满足 $1\le f[i]\le1000$。

## 输出描述

输出只有一行，包含一个整数，即最小化的最大 Stage 负载。

## 样例 1

输入

输出

样例解释 ：若干种划分方案如下，最优的最大负载为 $13$。

方案 Stage 0 Stage 1 Stage 2 最大负载 均分 [3,5,2] [7,4,6] [3,4] $\max(10,17,7)=17$ 方案 A [3,5] [2,7,4] [6,3,4] $\max(8,13,13)=13$ 方案 B [3,5,2] [7,4] [6,3,4] $\max(10,11,13)=13$

```text
8 3
3 5 2 7 4 6 3 4
13
```

## 样例 2

输入

输出

样例解释 ：把 $5$ 层划分为 $2$ 个 Stage，每层耗时为 $[3,5,2,7,4]$，所有切法如下，最优方案 C 的最大负载为 $\max(10,11)=11$。

方案 Stage 0 Stage 1 负载分布 最大负载 A [3] [5,2,7,4] 3 vs 18 18 B [3,5] [2,7,4] 8 vs 13 13 C [3,5,2] [7,4] 10 vs 11 11 D [3,5,2,7] [4] 17 vs 4 17

```text
5 2
3 5 2 7 4
11
```

## 思路分析

第一步：把问题翻译成区间划分。 题目要求把长度为 $N$ 的正整数序列切成恰好 $K$ 段连续非空的子段，让各段和的最大值尽量小。直接枚举切法要在 $N-1$ 个缝里选 $K-1$ 个，$N=500$ 时方案数是天文数字，不能枚举。

第二步：把求最优值转成判定问题。 给定一个上限 $\text{cap}$，「能不能切成不超过 $K$ 段、每段和都不超过 $\text{cap}$」很好判断，并且 $\text{cap}$ 越大需要的段数只会越少，判定结果单调，于是可以二分答案。

第三步：写 check。 从左往右贪心装层，当前段再装一层就超过 $\text{cap}$ 时就另起一段，得到最少段数 $\operatorname{cnt}(\text{cap})$。贪心之所以最少：每段都尽量往右装满，下一段的起点就尽可能靠右，剩下的层只会更少，不可能比别的切法多用段。可行条件是

段数少于 $K$ 也算可行，因为 $N\ge K$，总能把某个含两层以上的段再拆开，直到恰好 $K$ 段；拆开后每段负载只减不增，仍不超过 $\text{cap}$。

第四步：定二分边界。 下界取 $\max f[i]$，最重的一层单独成段也得装下；上界取 $\sum f[i]$，所有层放进一段。若 $\operatorname{cnt}(\text{mid})\le K$ 说明 $\text{mid}$ 可行，答案不会更大，令 $\text{hi}=\text{mid}$；否则段数不够用，令 $\text{lo}=\text{mid}+1$。收敛时 $\text{lo}=\text{hi}$ 就是最小的可行上限，它恰好覆盖 $K=N$（每层单独一段，答案为 $\max f[i]$）与 $K=1$（答案为 $\sum f[i]$）两个边界。

## 正确性说明

对任意 $\text{cap}$，贪心扫描给出的段数不超过任何合法划分的段数：若某划分每段和都不超过 $\text{cap}$，把贪心得到的第 $j$ 段与最优划分的第 $j$ 段比较可知贪心段的右端点不会更靠左，归纳即得贪心段数最少。因此当且仅当存在合法划分时 $\operatorname{cnt}(\text{cap})\le K$，二分所需的单调性也由「$\text{cap}$ 增大时贪心段数不增」保证。二分取到的是最小的可行 $\text{cap}$，即最小的最大 Stage 负载。

## 题解代码

### Python 实现

```python
# 题目：流水线并行最小化最大 Stage 负载
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(N\log\sum f)；空间 O(N)，存下每层的前向传播时间，判定过程只用常数个变量

import sys

input = sys.stdin.readline


# 给定每段负载上限 cap，从左往右贪心装层，返回最少要切成几段
def count_stages(f, cap):
    stages = 1  # 开头就有第一段
    load = 0  # 当前这一段已装入的负载
    for x in f:
        # 再装这一层就超上限，只能让它另起一段；cap >= max(f) 保证单层一定装得下
        if load + x > cap:
            stages += 1
            load = 0
        load += x
    return stages


# 二分最大负载：cap 越大，贪心需要的段数越少，判定结果单调
def min_max_load(f, k):
    lo = max(f)  # 下界：最大的那一层必须装得下
    hi = sum(f)  # 上界：所有层放进同一段
    while lo < hi:
        mid = (lo + hi) // 2
        # 段数 <= k 就算可行：n >= k 时总能把含两层以上的段继续拆开，
        # 直到恰好 k 段且都非空；拆开后每段负载只会变小，仍不超过 mid
        if count_stages(f, mid) <= k:
            hi = mid
        else:
            lo = mid + 1
    return lo


# 读取输入并输出答案
):
    n, k = map(int, input().split())
    f = list(map(int, input().split()))
    print(min_max_load(f, k))


solve()
```

## 复杂度分析

时间复杂度 ：$O(N\log\sum f)$。$\sum f\le5\times10^{5}$，二分约 $19$ 轮，每轮贪心扫描一遍为 $O(N)$；写成 $O(N^{2}K)$ 的区间划分 DP，在 $N=500$ 时约需 $1.25\times10^{8}$ 次转移，反而慢得多。

空间复杂度 ：$O(N)$，存下每层的前向传播时间，判定过程只用常数个变量。

## 易错点

判定要允许段数 少于 $K$，因为多出来的段总能继续拆分；写成「必须恰好等于 $K$」会漏掉可行解。 二分下界必须是 $\max f[i]$，否则最重的那一层单独成段都会超上限，判定永远不可行。 贪心装层时要把整层装进某一段，不能把一层切开分给两个 Stage，划分的连续性约束也要求切点只能落在层与层之间。 $K=N$ 与 $K=1$ 是两个边界，用 $\max f[i]$ 和 $\sum f[i]$ 作初值即可自然覆盖，不需要特判。

### Java 实现

```java
// 题目：流水线并行最小化最大 Stage 负载
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(N\log\sum f)；空间 O(N)，存下每层的前向传播时间，判定过程只用常数个变量

import java.io.*;
import java.util.*;

public class Main {
    static class In {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        StringTokenizer st = new StringTokenizer("");
        String next() { while (!st.hasMoreTokens()) { String l=null; try { l=br.readLine(); } catch (IOException e) { throw new RuntimeException(e); } if (l==null) return null; st=new StringTokenizer(l); } return st.nextToken(); }
        int ni() { return Integer.parseInt(next()); }
        long nl() { return Long.parseLong(next()); }
    }
    static long[] f;
    static long countStages(long cap) {
        long stages = 1;
        long load = 0;
        for (long x : f) {
            if (load + x > cap) { stages++; load = 0; }
            load += x;
        }
        return stages;
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        In in = new In();
        int n = in.ni();
        int k = in.ni();
        f = new long[n];
        long lo = Long.MIN_VALUE, hi = 0;
        for (int i = 0; i < n; i++) { f[i] = in.nl(); if (f[i] > lo) lo = f[i]; hi += f[i]; }
        while (lo < hi) {
            long mid = (lo + hi) / 2;
            if (countStages(mid) <= k) hi = mid; else lo = mid + 1;
        }
        System.out.println(lo);
    }
}
```
