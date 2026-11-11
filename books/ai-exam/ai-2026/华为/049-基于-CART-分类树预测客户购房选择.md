# 基于 CART 分类树预测客户购房选择

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20261014/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-10-14 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

给定客户训练数据，按指定规则构建 CART 二叉分类树，预测待测客户是否购房。每条训练记录包含 4 个整数枚举特征和 1 个二分类标签：

特征 1：年龄段，0 为 18—30 岁，1 为 31—40 岁，2 为 41—55 岁，3 为 56 岁及以上。 特征 2：婚姻状况，0 为单身，1 为恋爱，2 为已婚。 特征 3：是否有房，0 为无，1 为有。 特征 4：是否有工作，0 为无，1 为有。 标签：是否购房，0 为否，1 为是。

对特征 $A$ 和候选取值 $v$，左子集为 $D_1={s\in D:s_A=v}$，右子集为 $D_2={s\in D:s_A\ne v}$。候选值取当前节点出现的特征值。

对于包含 $K$ 个类别的数据集 $D$，第 $k$ 类占比为 $p_k$，基尼指数为

$$Gini(D)=1-\sum_{k=1}^{K}p_k^2.$$

切分的加权基尼指数为

$$Gini(D,A,v)=\frac{\lvert D_1\rvert}{\lvert D\rvert}Gini(D_1)+\frac{\lvert D_2\rvert}{\lvert D\rvert}Gini(D_2).$$

选择加权基尼指数最小的切分。多个候选同分时先选特征编号较小的；同一特征同分时选取值较小的。满足以下任一条件即停止，生成叶子：

所有样本标签相同。 样本数小于 2。 没有切分能够使基尼指数严格降低。

叶子预测多数类别；类别数相同时预测编号较小的 0。预测时特征值等于切分值走左支，否则走右支。

输入格式 ：第一行为 $N$，$4\le N\le20$；随后 $N$ 行各含 5 个整数，前 4 个为特征，最后一个为标签。再输入 $M$，$1\le M\le10$，随后 $M$ 行各含 4 个测试特征。

输出格式 ：输出一行 $M$ 个预测标签，用空格分隔。

## 样例 1

输入

输出

```text
8
0 0 0 0 0
0 1 0 1 1
1 0 0 1 1
1 1 1 0 1
2 2 1 1 1
2 0 0 0 0
3 2 1 0 0
3 2 0 1 1
3
2 0 0 0
1 1 1 0
3 2 1 0
0 1 0
```

## 样例 2

输入

输出

```text
20
0 0 0 1 1
0 0 1 0 0
0 1 0 0 0
0 1 1 1 1
0 2 0 1 1
1 0 0 0 0
1 0 1 1 1
1 1 0 1 1
1 1 1 0 0
1 2 1 0 0
2 0 0 1 1
2 0 1 0 1
2 1 0 0 0
2 1 1 1 1
2 2 0 0 0
3 0 0 0 0
3 0 1 1 0
3 1 0 1 1
3 1 1 0 0
3 2 0 1 0
10
1 1 1 0
2 0 0 1
3 2 0 1
0 0 0 1
1 2 1 0
2 1 0 0
3 0 1 1
0 1 1 1
1 0 0 0
2 2 0 0
0 1 0 1 0 0 0 1 0 0
```

## 思路分析

第一步：把训练过程视为确定性的递归规则。

本题不是寻找全局最优决策树，也不进行剪枝或随机选特征。对每个节点枚举规定的二元切分，选择当前最优，再递归处理左右子集即可。某个特征可以重复使用，因为先分出一种取值后，右侧仍可能包含该特征的其他取值。

第二步：用分数精确比较基尼指数。

设节点中标签 0、1 的数量分别为 $c_0,c_1$，样本数为 $s=c_0+c_1$。定义

$$mass(S)=\lvert S\rvert\cdot Gini(S)=\frac{s^2-c_0^2-c_1^2}{s}=\frac{2c_0c_1}{s},$$

空集的 mass 约定为 0。对于同一个父节点，所有候选的加权基尼都有相同的分母 $\lvert D\rvert$，所以可以比较

$$mass(D_1)+mass(D_2).$$

代码保存分数的分子和分母，不需要浮点运算。比较 $a/b<c/d$ 时判断 $ad<cb$；两分数相加使用 $(ad+cb)/(bd)$。这样不会把数学上的平局误判成微小差异。

第三步：用遍历顺序落实平局规则。

按特征 1 到 4、取值从小到大枚举，只在新分数严格更小时更新最优项。同分候选不覆盖旧候选，自然保留较小特征编号和较小取值。

最优切分仍必须严格优于父节点的 mass，否则直接返回多数类叶子。全体样本落到一侧的候选不会降低基尼，可以跳过。标签不纯也可能停止：例如异或型标签，两侧类别比例与父节点一致时，任何一步都不能降低基尼；不能为了以后可能变纯而强行继续切分。

第四步：核对样例与预测路径。

样例 1 的根节点标签数量为 3 个 0、5 个 1，基尼为 0.46875。以“特征 4 等于 0”切分，左侧标签为 0、1、0、0，右侧全为 1，加权基尼为 0.1875。左右互换的取值 1 得到同分，因此选取值 0。左侧再按“特征 1 等于 1”切分，两侧变纯。三个测试客户最终预测为 0、1、0。

训练时没有出现的测试取值，也按“不等于当前切分值”走右支，不需要单独建立未知类别分支。

## 题解代码

### Python 实现

```python
# 题目：基于 CART 分类树预测客户购房选择
# 算法：排序 + 扫描
# 模式：ACM（stdin/stdout）

import sys
input = sys.stdin.readline


# 核心函数：mass
def mass(count_zero, count_one):
    size = count_zero + count_one
    # 返回结果
    return (2 * count_zero * count_one, size) if size else (0, 1)


# 核心函数：add_fraction
def add_fraction(a, b):
    # 返回结果
    return (a[0] * b[1] + b[0] * a[1], a[1] * b[1])


# 核心函数：less_fraction
def less_fraction(a, b):
    # 返回结果
    return a[0] * b[1] < b[0] * a[1]


# 核心函数：build_tree
def build_tree(rows):
    count_one = sum(row[4] for row in rows)
    count_zero = len(rows) - count_one
    majority = int(count_one > count_zero)
    # 条件判断
    if count_zero == 0 or count_one == 0 or len(rows) < 2:
        # 返回结果
        return (majority,)

    best_score = mass(count_zero, count_one)
    best_feature = best_value = None
    # 遍历 feature
    for feature in range(4):
        # 遍历 value
        for value in sorted({row[feature] for row in rows}):
            left = [row for row in rows if row[feature] == value]
            left_one = sum(row[4] for row in left)
            left_zero = len(left) - left_one
            score = add_fraction(
                mass(left_zero, left_one),
                mass(count_zero - left_zero, count_one - left_one),
            )
            # 条件判断
            if less_fraction(score, best_score):
                best_score = score
                best_feature, best_value = feature, value

    # 条件判断
    if best_feature is None:
        # 返回结果
        return (majority,)
    left = [row for row in rows if row[best_feature] == best_value]
    right = [row for row in rows if row[best_feature] != best_value]
    # 返回结果
    return (best_feature, best_value, build_tree(left), build_tree(right))


# 核心函数：predict
def predict(tree, sample):
    # 循环处理
    while len(tree) != 1:
        feature, value, left, right = tree
        tree = left if sample[feature] == value else right
    # 返回结果
    return tree[0]


# 读取输入并输出答案
def solve():
    n = int(input())
    rows = [list(map(int, input().split())) for _ in range(n)]
    tree = build_tree(rows)
    m = int(input())
    answers = [predict(tree, list(map(int, input().split()))) for _ in range(m)]
    print(*answers)


if __name__ == "__main__":
    solve()
```

## 复杂度分析

设树深为 $H$。每个特征的取值数不超过 4，节点中有 $s$ 条记录时，枚举并计算全部候选需要 $O(s)$ 时间。每层节点的样本集合互不重叠，建树需要 $O(NH)$，预测需要 $O(MH)$。

本题的取值域固定为 4、3、2、2。沿任一路径，每次有效切分都会使某个特征的剩余可能取值数至少减少 1，因此 $H\le(4-1)+(3-1)+(2-1)+(2-1)=7$。按本题固定域， 时间复杂度 为 $O(N+M)$，常数来自特征与候选枚举。如果只使用 $H\le N$ 而不利用固定域带来的更紧深度界，也可写成保守上界 $O(N^2+MN)$；这一估计仍以每个特征的候选数为常数为前提。

空间复杂度 ：递归会保留祖先的样本列表，上界为 $O(NH)$；本题 $H\le7$，因此为 $O(N)$。树节点、训练集和输出列表同样在此范围内。

### Java 实现

```java
// 题目：基于 CART 分类树预测客户购房选择
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）

import java.io.*;
import java.util.*;
import java.math.BigInteger;

public class Main {
    static class In {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        StringTokenizer st = new StringTokenizer("");
        String next() { while (!st.hasMoreTokens()) { String l=null; try { l=br.readLine(); } catch (IOException e) { throw new RuntimeException(e); } if (l==null) return null; st=new StringTokenizer(l); } return st.nextToken(); }
        int ni() { return Integer.parseInt(next()); }
    }
    static class Tree {
        boolean leaf; int value; int feature; int splitValue; Tree left, right;
        Tree(int v) { leaf = true; value = v; }
        Tree(int f, int sv, Tree a, Tree b) { feature = f; splitValue = sv; left = a; right = b; }
    }
    // 核心方法：mass
    static BigInteger[] mass(long cz, long co) {
        long size = cz + co;
        // 条件判断
        if (size == 0) return new BigInteger[]{BigInteger.ZERO, BigInteger.ONE};
        // 返回结果
        return new BigInteger[]{BigInteger.valueOf(2 * cz * co), BigInteger.valueOf(size)};
    }
    // 核心方法：addF
    static BigInteger[] addF(BigInteger[] a, BigInteger[] b) {
        // 返回结果
        return new BigInteger[]{a[0].multiply(b[1]).add(b[0].multiply(a[1])), a[1].multiply(b[1])};
    }
    // 核心方法：lessF
    static boolean lessF(BigInteger[] a, BigInteger[] b) {
        // 返回结果
        return a[0].multiply(b[1]).compareTo(b[0].multiply(a[1])) < 0;
    }
    // 核心方法：build
    static Tree build(List<int[]> rows) {
        long countOne = 0;
        // 循环处理
        for (int[] r : rows) countOne += r[4];
        long countZero = rows.size() - countOne;
        int majority = countOne > countZero ? 1 : 0;
        // 条件判断
        if (countZero == 0 || countOne == 0 || rows.size() < 2) return new Tree(majority);
        BigInteger[] bestScore = mass(countZero, countOne);
        int bestFeature = -1, bestValue = 0;
        // 循环处理
        for (int feature = 0; feature < 4; feature++) {
            TreeSet<Integer> vals = new TreeSet<>();
            // 循环处理
            for (int[] r : rows) vals.add(r[feature]);
            // 循环处理
            for (int value : vals) {
                long leftOne = 0, leftSize = 0;
                // 循环处理
                for (int[] r : rows) if (r[feature] == value) { leftSize++; leftOne += r[4]; }
                long leftZero = leftSize - leftOne;
                BigInteger[] score = addF(mass(leftZero, leftOne), mass(countZero - leftZero, countOne - leftOne));
                // 条件判断
                if (lessF(score, bestScore)) { bestScore = score; bestFeature = feature; bestValue = value; }
            }
        }
        // 条件判断
        if (bestFeature == -1) return new Tree(majority);
        List<int[]> left = new ArrayList<>();
        List<int[]> right = new ArrayList<>();
        // 循环处理
        for (int[] r : rows) { if (r[bestFeature] == bestValue) left.add(r); else right.add(r); }
        // 返回结果
        return new Tree(bestFeature, bestValue, build(left), build(right));
    }
    // 核心方法：predict
    static int predict(Tree t, int[] s) {
        // 循环处理
        while (!t.leaf) { t = (s[t.feature] == t.splitValue) ? t.left : t.right; }
        // 返回结果
        return t.value;
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        In in = new In();
        int n = in.ni();
        List<int[]> rows = new ArrayList<>();
        // 枚举位置 i
        for (int i = 0; i < n; i++) { int[] r = new int[5]; for (int j = 0; j < 5; j++) r[j] = in.ni(); rows.add(r); }
        Tree tree = build(rows);
        int m = in.ni();
        StringBuilder sb = new StringBuilder();
        // 枚举位置 i
        for (int i = 0; i < m; i++) {
            int[] s = new int[4];
            // 枚举阶段 j
            for (int j = 0; j < 4; j++) s[j] = in.ni();
            // 条件判断
            if (i > 0) sb.append(' ');
            sb.append(predict(tree, s));
        }
        System.out.println(sb.toString());
    }
}
```
