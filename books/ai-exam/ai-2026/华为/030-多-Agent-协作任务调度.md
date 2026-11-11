# 多 Agent 协作任务调度

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260805/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-08-05 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

一个多 Agent 系统包含 $N$ 个 Agent。每调用一次第 $i$ 个 Agent，任务进度增加 $p_i$ 个百分点，并产生代价 $c_i$。每个 Agent 可以调用任意多次，但不能连续两次调用同一个 Agent。

当累计进度达到或超过 $100$ 时任务完成，允许最终进度超过 $100$。请计算完成任务的最小总代价；若无法完成，输出 -1 。

## 输入格式

第一行输入整数 $N$，满足 $1\le N\le10^5$。

接下来 $N$ 行，每行包含两个整数 $p_i,c_i$：

$1\le p_i\le100$； $1\le c_i\le10^4$。

## 输出格式

输出完成任务所需的最小总代价；若无解，输出 -1 。

## 样例 1

输入

输出

只有一个 Agent，调用一次后进度为 $60$，第二次调用会违反相邻不同约束，因此无解。

```text
1
60 5
-1
```

## 样例 2

输入

输出

依次调用 Agent 1、Agent 2、Agent 1，进度为 $30+40+30=100$，代价为 $1+2+1=4$。

```text
3
30 1
40 2
100 50
4
```

## 思路分析

进度只需保留 $0$ 到 $99$：一旦达到 $100$，直接更新答案。由于 $p_i\ge1$，进度严格增加，可以按进度从小到大转移。

朴素状态可定义为：

$$dp[j][i]=\text{累计进度恰为 }j\text{，且最后调用 Agent }i\text{ 的最小代价}.$$

若下一次调用 Agent $k$，需要求

$$\min_{i\ne k}dp[j][i]+c_k.$$

完整枚举 $i,k$ 的复杂度为 $O(100N^2)$，无法通过。注意：从一层状态中排除某个 Agent 后的最小值，只可能是该层的最小值或“属于另一个 Agent 的次小值”。

对每个进度 $j$ 维护：

best[j] ：这一层的最小代价； best_last[j] ：取得最小代价时最后调用的 Agent； second[j] ：最后一个 Agent 与 best_last[j] 不同的最小代价。

转移到 Agent $k$ 时：

$$base= \begin{cases} second[j],&k=best\_last[j],\\ best[j],&k\ne best\_last[j]. \end{cases}$$

然后令 new_cost = base + c[k] 。若 $j+p_k\ge100$，用它更新答案；否则把 (new_cost, k) 合并到目标进度层的最小值/次小值中。

进度 $0$ 是虚拟起点，没有“上一个 Agent”。令 best[0] = second[0] = 0 且 best_last[0] = -1 ，即可让第一次调用任意 Agent。

## 复杂度分析

时间复杂度 ：$O(100N)$。最多处理 100 个进度层，每层扫描全部 Agent。 空间复杂度 ：$O(N)$，用于保存所有 $p_i,c_i$；DP 数组长度固定为 100。

## Python 代码

### Python 实现

```python
# 题目：多 Agent 协作任务调度
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(100N)；空间 O(N)，用于保存所有 p_i,c_i；DP 数组长度固定为 100

import sys


# 读取输入并输出答案
def solve():
    input = sys.stdin.readline
    n = int(input())
    progress = [0] * n
    cost = [0] * n

    # 枚举位置 i
    for i in range(n):
        progress[i], cost[i] = map(int, input().split())

    inf = 10**30

    # best[j]：进度恰为 j 时的最小代价。
    # second[j]：排除 best_last[j] 后，由另一个 Agent 结尾的最小代价。
    best = [inf] * 100
    second = [inf] * 100
    best_last = [-1] * 100

    # 虚拟起点：第一次调用不受“相邻不同”限制。
    best[0] = 0
    second[0] = 0

    answer = inf

    # 遍历 current
    for current in range(100):
        # 条件判断
        if best[current] == inf:
            continue

        # 遍历 agent
        for agent in range(n):
            # 条件判断
            if agent == best_last[current]:
                base = second[current]
            else:
                base = best[current]

            # 条件判断
            if base == inf:
                continue

            new_cost = base + cost[agent]
            next_progress = current + progress[agent]

            # 条件判断
            if next_progress >= 100:
                answer = min(answer, new_cost)
                continue

            # 将“代价 new_cost、末尾 agent”合并到目标层。
            # 条件判断
            if new_cost < best[next_progress]:
                # 条件判断
                if best_last[next_progress] == agent:
                    # 同一 Agent 的状态变优，不影响异 Agent 次小值。
                    best[next_progress] = new_cost
                else:
                    # 原最小值来自另一个 Agent，可成为新的次小值。
                    second[next_progress] = best[next_progress]
                    best[next_progress] = new_cost
                    best_last[next_progress] = agent
            # 条件判断
            elif (
                best_last[next_progress] != agent
                and new_cost < second[next_progress]
            ):
                second[next_progress] = new_cost

    print(-1 if answer == inf else answer)


if __name__ == "__main__":
    solve()
```

## 易错点

把问题写成普通完全背包 ：状态必须体现“上一个 Agent”，否则无法检查相邻不同约束。 次小值定义错误 ： second[j] 必须来自与 best_last[j] 不同的 Agent，而不是简单的第二个数值。 同一 Agent 刷新最小值时误改次小值 ：若最小值持有者不变，只更新 best ，不能覆盖 second 。 达到 100 后仍继续转移 ：题目在进度达到或超过 $100$ 时即完成，直接更新答案即可。 单 Agent 特例 ：若仅有一个 Agent 且 $p_1<100$，最多合法调用一次，答案为 -1 ；上述 DP 会自然得到该结果。 初始化不当 ：进度 $0$ 尚无上一个 Agent，必须允许任意 Agent 作为第一次调用。

### Java 实现

```java
// 题目：多 Agent 协作任务调度
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(100N)；空间 O(N)，用于保存所有 p_i,c_i；DP 数组长度固定为 100

import java.io.*;
import java.util.*;

public class Main {
    static class FastScanner {
        BufferedReader br;
        StringTokenizer st;
        FastScanner() {
            br = new BufferedReader(new InputStreamReader(System.in));
        }
        String next() throws IOException {
            // 循环处理
            while (st == null || !st.hasMoreTokens()) {
                String line = br.readLine();
                // 条件判断
                if (line == null) return null;
                st = new StringTokenizer(line);
            }
            // 返回结果
            return st.nextToken();
        }
        int nextInt() throws IOException {
            // 返回结果
            return Integer.parseInt(next());
        }
        long nextLong() throws IOException {
            // 返回结果
            return Long.parseLong(next());
        }
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        FastScanner fs = new FastScanner();
        String t = fs.next();
        // 条件判断
        if (t == null) return;
        int n = Integer.parseInt(t);
        long[] progress = new long[n];
        long[] cost = new long[n];
        // 枚举位置 i
        for (int i = 0; i < n; i++) {
            progress[i] = fs.nextLong();
            cost[i] = fs.nextLong();
        }
        long INF = Long.MAX_VALUE / 4;
        long[] best = new long[100];
        long[] second = new long[100];
        int[] bestLast = new int[100];
        Arrays.fill(best, INF);
        Arrays.fill(second, INF);
        Arrays.fill(bestLast, -1);
        best[0] = 0;
        second[0] = 0;
        long answer = INF;
        // 循环处理
        for (int current = 0; current < 100; current++) {
            // 条件判断
            if (best[current] == INF) continue;
            // 循环处理
            for (int agent = 0; agent < n; agent++) {
                long base;
                // 条件判断
                if (agent == bestLast[current]) base = second[current];
                else base = best[current];
                // 条件判断
                if (base == INF) continue;
                long newCost = base + cost[agent];
                long nextProgress = current + progress[agent];
                // 条件判断
                if (nextProgress >= 100) {
                    answer = Math.min(answer, newCost);
                    continue;
                }
                int np = (int) nextProgress;
                // 条件判断
                if (newCost < best[np]) {
                    // 条件判断
                    if (bestLast[np] == agent) {
                        best[np] = newCost;
                    } else {
                        second[np] = best[np];
                        best[np] = newCost;
                        bestLast[np] = agent;
                    }
                } else if (bestLast[np] != agent && newCost < second[np]) {
                    second[np] = newCost;
                }
            }
        }
        System.out.println(answer == INF ? -1 : answer);
    }
}
```
