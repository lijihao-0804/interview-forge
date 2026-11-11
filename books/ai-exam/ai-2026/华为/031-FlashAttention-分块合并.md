# FlashAttention 分块合并

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260819/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-08-19 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

每个序列块维护状态三元组 $(m,d,v)$：

$m$：该块打分的最大值； $d$：以 $m$ 为基准重缩放后的权重和； $v$：以 $m$ 为基准重缩放后的加权值之和。

该状态对应的注意力结果为 $v/d$。相邻状态 $A=(m_a,d_a,v_a)$ 与 $B=(m_b,d_b,v_b)$ 合并时，令

$$m=\max(m_a,m_b),$$

$$d=d_ae^{m_a-m}+d_be^{m_b-m},$$

$$v=v_ae^{m_a-m}+v_be^{m_b-m}.$$

该合并运算满足结合律。给定 $B$ 个按顺序排列的块，支持 $Q$ 次操作：

1 i m d v ：把第 i 个块替换为新状态； 2 l r ：依次合并第 l 到第 r 个块，输出结果 $v/d$，保留 6 位小数。

## 样例

输入

输出

```text
2 3
1.0 2.0 8.0
1.0 2.0 12.0
2 1 2
2 1 1
2 2 2
5.000000
4.000000
6.000000
```

## 思路分析

合并运算满足结合律，所以可以用线段树让每个节点保存对应区间的合并状态：

单点更新只需重算叶子到根路径，复杂度 $O(\log B)$； 区间查询由 $O(\log B)$ 个线段树节点组成。

尽管该公式在数学上还满足交换律，下面仍使用通用的“左累积 + 右累积”迭代查询写法，严格保持区间顺序，也便于迁移到只满足结合律而不满足交换律的算子。

为便于处理补齐叶子，定义空状态为 None ；它与任意真实状态合并都返回另一方。这样不需要依赖某个有限的负数模拟负无穷，也避免题目数值范围未知时哨兵不够小的问题。

合并时统一减去两侧最大值，两个指数都不大于 0，可避免指数上溢；至少一侧指数严格为 1。只要输入状态的 d 为正，合并后的分母也为正。

## 题解代码

### Python 实现

```python
# 题目：FlashAttention 分块合并
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(B)； 每次更新或查询时间复杂度 ：O( B)； 空间复杂度 ：O(B)；空间 O(B)

import sys
from math import exp


def merge(left, right):
    if left is None:
        return right
    if right is None:
        return left

    lm, ld, lv = left
    rm, rd, rv = right
    maximum = max(lm, rm)
    left_scale = exp(lm - maximum)
    right_scale = exp(rm - maximum)

    return (
        maximum,
        ld * left_scale + rd * right_scale,
        lv * left_scale + rv * right_scale,
    )


# 读取输入并输出答案
):
    input = sys.stdin.buffer.readline
    block_count, query_count = map(int, input().split())
    blocks = [tuple(map(float, input().split())) for _ in range(block_count)]

    size = 1
    while size < block_count:
        size <<= 1

    tree = [None] * (2 * size)
    for index, block in enumerate(blocks):
        tree[size + index] = block
    for index in range(size - 1, 0, -1):
        tree[index] = merge(tree[index * 2], tree[index * 2 + 1])

    def update(position, state):
        index = size + position
        tree[index] = state
        index >>= 1
        while index:
            tree[index] = merge(tree[index * 2], tree[index * 2 + 1])
            index >>= 1

    def query(left, right):
        # 查询半开区间 [left, right)。
        left += size
        right += size
        left_result = None
        right_result = None

        while left < right:
            if left & 1:
                left_result = merge(left_result, tree[left])
                left += 1
            if right & 1:
                right -= 1
                right_result = merge(tree[right], right_result)
            left >>= 1
            right >>= 1

        return merge(left_result, right_result)

    output = []
    for _ in range(query_count):
        operation = input().split()
        if operation[0] == b"1":
            position = int(operation[1]) - 1
            state = tuple(map(float, operation[2:5]))
            update(position, state)
        else:
            left = int(operation[1]) - 1
            right = int(operation[2])
            _, denominator, numerator = query(left, right)
            output.append(f"{numerator / denominator:.6f}")

    sys.stdout.write("\n".join(output))


if __name__ == "__main__":
    solve()
```

## 复杂度分析

建树时间复杂度 ：$O(B)$； 每次更新或查询时间复杂度 ：$O(\log B)$； 空间复杂度 ：$O(B)$。

## 易错点

必须先减去公共最大值再取指数，避免上溢。 区间查询应保持块的原始顺序。 输出的是合并后的 v / d ，不是三元组本身。 使用 None 作为单位元比猜测一个足够小的有限哨兵更稳健。

### Java 实现

```java
// 题目：FlashAttention 分块合并
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(B)； 每次更新或查询时间复杂度 ：O( B)； 空间复杂度 ：O(B)；空间 O(B)

import java.io.*;
import java.util.*;

public class Main {
    static final char NL = (char) 10;
    static class FastScanner {
        BufferedReader br;
        StringTokenizer st;
        FastScanner() {
            br = new BufferedReader(new InputStreamReader(System.in));
        }
        String next() throws IOException {
            while (st == null || !st.hasMoreTokens()) {
                String line = br.readLine();
                if (line == null) return null;
                st = new StringTokenizer(line);
            }
            return st.nextToken();
        }
        int nextInt() throws IOException {
            return Integer.parseInt(next());
        }
        double nextDouble() throws IOException {
            return Double.parseDouble(next());
        }
    }

    static double[] merge(double[] left, double[] right) {
        if (left == null) return right;
        if (right == null) return left;
        double maximum = Math.max(left[0], right[0]);
        double ls = Math.exp(left[0] - maximum);
        double rs = Math.exp(right[0] - maximum);
        return new double[]{maximum, left[1] * ls + right[1] * rs, left[2] * ls + right[2] * rs};
    }

    static double[] query(double[][] tree, int size, int left, int right) {
        left += size;
        right += size;
        double[] lr = null;
        double[] rr = null;
        while (left < right) {
            if ((left & 1) == 1) {
                lr = merge(lr, tree[left]);
                left++;
            }
            if ((right & 1) == 1) {
                right--;
                rr = merge(tree[right], rr);
            }
            left >>= 1;
            right >>= 1;
        }
        return merge(lr, rr);
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        FastScanner fs = new FastScanner();
        String t = fs.next();
        if (t == null) return;
        int blockCount = Integer.parseInt(t);
        int queryCount = fs.nextInt();
        double[][] blocks = new double[blockCount][];
        for (int i = 0; i < blockCount; i++) {
            blocks[i] = new double[]{fs.nextDouble(), fs.nextDouble(), fs.nextDouble()};
        }
        int size = 1;
        while (size < blockCount) size <<= 1;
        double[][] tree = new double[2 * size][];
        for (int i = 0; i < blockCount; i++) tree[size + i] = blocks[i];
        for (int i = size - 1; i >= 1; i--) tree[i] = merge(tree[2 * i], tree[2 * i + 1]);
        StringBuilder sb = new StringBuilder();
        boolean firstOut = true;
        for (int q = 0; q < queryCount; q++) {
            String op = fs.next();
            if (op.equals("1")) {
                int position = fs.nextInt() - 1;
                double m = fs.nextDouble();
                double d = fs.nextDouble();
                double v = fs.nextDouble();
                int idx = size + position;
                tree[idx] = new double[]{m, d, v};
                idx >>= 1;
                while (idx >= 1) {
                    tree[idx] = merge(tree[2 * idx], tree[2 * idx + 1]);
                    idx >>= 1;
                }
            } else {
                int left = fs.nextInt() - 1;
                int right = fs.nextInt();
                double[] res = query(tree, size, left, right);
                double denom = res[1];
                double numer = res[2];
                if (!firstOut) sb.append(NL);
                firstOut = false;
                sb.append(String.format(Locale.US, "%.6f", numer / denom));
            }
        }
        System.out.print(sb);
    }
}
```
