# K-Median 聚类

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20261010/ · 华为 · 2026-10-10 · AI岗

## 题目描述

给定 $n$ 个 $d$ 维样本，按以下固定流程划分为 $k$ 个簇：
取前 $k$ 个样本作为初始中心，编号从零开始。 按曼哈顿距离将样本分给最近的中心，距离相等时选择编号最小的簇。 对每个非空簇，逐维取中位数作为新中心。偶数个数时取中间两数的平均值；空簇保持原中心。 当全部中心所有坐标的绝对变化总和小于 $10^{-4}$，或完成 100 轮分配与更新时停止。
输出最后一轮分配的标签、更新后的中心，以及按这些标签和最终中心计算的曼哈顿距离总和 inertia 。停止后不额外再做一轮分配。
输入格式 ：第一行 $n,d,k$，其中 $1\le n\le5000$、$1\le d\le20$、$1\le k\le\min(100,n)$。随后 $n$ 行，每行 $d$ 个实数，范围为 $[-10^4,10^4]$。
输出格式 ：首行输出 $n$ 个标签；接下来 $k$ 行输出各中心坐标，最后一行输出 inertia。所有实数保留六位小数。
这里要求实现给定的交替迭代过程，并不保证求得聚类目标的全局最优解。初始样本可能重复，因此从第一轮起就需要处理空簇。

## 样例 1

输入
输出

```text
5 2 1
1 2
0 10
10 0
10 10
5 5
0 0 0 0 0
5.000000 5.000000
37.000000
```

## 样例 2

输入
输出

```text
4 2 2
0 0
1 1
2 2
100 100
0 0 0 1
1.000000 1.000000
100.000000 100.000000
4.000000
```

## 思路分析

第一步：分配为何使用曼哈顿距离。 对每个样本计算到各中心的逐维绝对差之和。按中心编号遍历并仅在严格更小时更新，或使用返回第一个最小值的 argmin ，均可实现相等距离取最小编号。
第二步：更新为何使用中位数。 固定簇成员后，各坐标互相独立。一维目标 $\sum_i\lvert x_i-c\rvert$ 在中位数处取得最小值：向右移动时，左侧点的距离增加、右侧点的距离减少，两边数量平衡时最优。偶数个样本的中间区间都能达到最小值，本题指定采用中间两数的平均值，不能任取一端。
第三步：控制距离矩阵的内存。 不一次生成 $n\times k\times d$ 张量，而是逐维广播得到 $n\times k$ 的差值矩阵，再累加到距离矩阵。使用 NumPy 向量化完成主要数值计算，避免在最大规模下用 Python 三重循环逐元素运行。
第四步：严格遵守轮次边界。 每轮先分配、再更新，再检查所有中心的总变化。空簇直接保留旧中心。输出使用该轮的标签和更新结果，在达到轮数上限时尤其不能擅自多做一次分配。样例一只有一个簇，各坐标中位数均为 5，距离总和为 37。
正确性说明 ：分配函数逐项计算规定距离并正确打破平局；更新函数独立计算每一簇每一维的指定中位数，并保留空簇。循环严格按顺序执行最多 100 轮，故输出与题设过程一致。

## 题解代码

### Python 实现

```python
import sys
import numpy as np


def k_median(points, k):
    n, d = points.shape
    centers = points[:k].copy()
    for _ in range(100):
        distances = np.zeros((n, k), dtype=float)
        for axis in range(d):
            distances += np.abs(points[:, axis, None] - centers[None, :, axis])
        labels = distances.argmin(axis=1)
        updated = centers.copy()
        for cluster in range(k):
            members = points[labels == cluster]
            if len(members):
                updated[cluster] = np.median(members, axis=0)
        shift = np.abs(updated - centers).sum()
        centers = updated
        if shift < 1e-4:
            break
    inertia = np.abs(points - centers[labels]).sum()
    return labels, centers, inertia


def solve():
    input = sys.stdin.readline
    n, d, k = map(int, input().split())
    points = np.array([list(map(float, input().split())) for _ in range(n)])
    labels, centers, inertia = k_median(points, k)
    print(" ".join(map(str, labels)))
    for center in centers:
        print(" ".join(f"{value:.6f}" for value in center))
    print(f"{inertia:.6f}")


if __name__ == "__main__":
    solve()
```

## 复杂度分析

时间复杂度 ：$O(Tnkd)$，$T\le100$ 为实际轮数；分配需要 $O(nkd)$，簇筛选为 $O(nk)$，NumPy 中位数采用选择算法，所有簇合计处理 $O(nd)$ 个坐标值。
空间复杂度 ：$O(nk+nd+kd)$，包括距离矩阵、样本、簇成员与中心。
