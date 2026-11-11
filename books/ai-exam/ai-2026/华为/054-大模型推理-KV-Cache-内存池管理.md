# 大模型推理 KV Cache 内存池管理

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20261023/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-10-23 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

在大语言模型推理过程中，KV Cache 存储历史 token 的 Key 和 Value，避免重复计算，加速自回归生成。随着序列增长，缓存占用增加，系统使用预先分配的等大小内存块（Block）管理 GPU 内存。

内存池共有 $m$ 个 Block，每个 Block 可以容纳 $k$ 个 token 的 KV 数据。现有 $n$ 个推理请求，第 $i$ 个请求处理 $len[i]$ 个 token（输入长度加生成长度），需要占用

$$b_i=\left\lceil\frac{len[i]}{k}\right\rceil$$

个 Block。

分配规则如下：

请求按给定顺序依次到达。 对每个请求可以选择接受或拒绝；接受后的最终总占用不能超过 $m$，拒绝不占资源。 允许在后续决策中撤销之前已经接受的请求，释放其 Block，以获得更好的整体结果。 请求一旦被拒绝，不可再次考虑。 请求之间不能重排，必须按输入顺序进行决策。

求总占用不超过 $m$ 时，最终可以接受的最多请求数量。

## 输入描述与约束

第一行三个整数 $m,k,n$，分别表示 Block 总数、每个 Block 可容纳的 token 数和请求数。

第二行 $n$ 个整数 $len[1],\ldots,len[n]$，表示各请求的 token 数。

$1\le m\le 100000$。 $1\le k\le 1000$。 $1\le n\le 100000$。 $1\le len[i]\le 1000000$。

若某请求需要的 Block 数大于 $m$，它一定无法被接受。题目建议算法时间复杂度优于 $O(n^2)$。

## 输出描述

输出一个整数，表示最多可接受的请求数量。

## 样例 1

输入

输出

解释 ：Block 需求依次为 $3,1,2$。只保留请求 1 会占满内存，只能保留一个请求；跳过请求 1，接受请求 2、3，总占用为 $1+2=3$，可保留两个请求。

```text
3 10 3
25 5 15
2
```

## 样例 2

输入

输出

解释 ：Block 需求依次为 $1,3,2,2$。选择请求 1、3、4，总占用 $1+2+2=5$，共接受三个请求。

```text
5 10 4
8 25 15 12
3
```

## 解题思路：排序贪心

先区分计算顺序与请求到达顺序。 输入已经给出了全部请求，算法可以离线计算应该保留的集合；对需求排序只是求最优数量，并不是让系统重新排列到达顺序。

任取一个总需求不超过 $m$ 的集合 $S$，按照原输入顺序处理：属于 $S$ 的请求接受，其余拒绝。由于需求均为正数，任意前缀的占用都不超过整个集合的占用，因此过程始终可行。这甚至不需要执行撤销操作，也不会重新考虑被拒绝的请求。

问题因此等价于：从所有 Block 需求中选尽量多个数，使其和不超过 $m$。每个请求带来的收益都是“数量加一”，自然优先选择需求小的请求。

用整数式 (length + k - 1) // k 计算向上取整，不使用浮点数。 将全部需求升序排序。 从小到大累加；若当前需求放不下，则停止，因为后面的需求不会更小。

## 正确性证明

设排序后的需求为 $b_1\le b_2\le\cdots\le b_n$。

引理一： 任意满足容量限制的子集，都能按原到达顺序合法实现。证明如上：逐个接受集合内的请求，前缀需求和不会超过集合总需求和。

引理二： 任意包含 $t$ 个请求的集合，其需求和都不小于 $\sum_{i=1}^{t}b_i$。因为最小的 $t$ 个数在所有大小为 $t$ 的选择中取得最小总和。

若贪心接受了 $r$ 个请求后停止，前 $r$ 个需求和不超过 $m$，由引理一可实现。当 $r<n$ 时，前 $r+1$ 个需求和超过 $m$，由引理二，任何 $r+1$ 个请求都不可能同时保留。因此不存在更大的可行解。若 $r=n$，已经接受全部请求，同样最优。

## Python ACM 代码

### Python 实现

```python
# 题目：大模型推理 KV Cache 内存池管理
# 算法：排序 + 扫描
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(n n)，排序占主导，计算需求和扫描均为 O(n)；空间 O(n)，包括输入、需求数组以及 Python 排序使用的辅助空间

import sys


# 核心函数：max_accept
def max_accept(m, k, lengths):
    needs = sorted((length + k - 1) // k for length in lengths)
    used = 0
    answer = 0
    # 遍历 need
    for need in needs:
        # 条件判断
        if used + need > m:
            break
        used += need
        answer += 1
    # 返回结果
    return answer


# 核心函数：main
def main():
    data = list(map(int, sys.stdin.buffer.read().split()))
    # 条件判断
    if not data:
        # 返回结果
        return
    m, k, n = data[:3]
    print(max_accept(m, k, data[3:3 + n]))


if __name__ == "__main__":
    main()
```

## 复杂度分析

时间复杂度 ：$O(n\log n)$，排序占主导，计算需求和扫描均为 $O(n)$。

空间复杂度 ：$O(n)$，包括输入、需求数组以及 Python 排序使用的辅助空间。

## 本题小结

关键是证明到达顺序不影响最终可行集合，再使用“固定数量时取最小需求”的贪心。不必套容量背包，也不必模拟复杂的缓存管理。所有请求都放不下时输出 0；恰好装满时仍应计入最后一个请求。

### Java 实现

```java
// 题目：大模型推理 KV Cache 内存池管理
// 算法：排序 + 扫描
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(n n)，排序占主导，计算需求和扫描均为 O(n)；空间 O(n)，包括输入、需求数组以及 Python 排序使用的辅助空间

import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;
    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) return null;
            st = new StringTokenizer(line);
        }
        return st.nextToken();
    }
    static int nextInt() throws IOException { return Integer.parseInt(next()); }
    static long nextLong() throws IOException { return Long.parseLong(next()); }

    // 主函数：读取输入并输出答案
    public static void main(String[] a) throws IOException {
        // 条件判断
        long m=nextLong();
        long k=nextLong();
        int n=nextInt();
        long[] len=new long[n];
        // 枚举位置 i
        for(int i=0;i<n;i++)len[i]=nextLong();
        long[] need=new long[n];
        // 枚举位置 i
        for(int i=0;i<n;i++)need[i]=(len[i]+k-1)/k;
        Arrays.sort(need);
        long used=0;
        int ans=0;
        // 循环处理
        for(long nd:need) {
            // 条件判断
            if(used+nd>m)break;
            used+=nd;
            ans++;
        }
        System.out.println(ans);
    }
}
```
