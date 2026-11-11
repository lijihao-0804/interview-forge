# X-Means 聚类算法的实现

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20261021/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-10-21 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

给定 $N$ 个 $d$ 维数据点及允许的簇数范围 $[K_{min},K_{max}]$，对范围内每个簇数运行确定性 K-Means，合并重合中心，再用 BIC 选出最终聚类，输出中心和每个输入点的标签。

这里的“X-Means”按本题定义，是 枚举簇数并比较 BIC ，不是另行实现文献中基于局部二分裂的版本。

设点 $x_i$ 的标签为 $c(i)$，中心为 $\mu_{c(i)}$，误差平方和为

$$SSE=\sum_{i=1}^{N}\sum_{j=1}^{d}(x_{ij}-\mu_{c(i),j})^2.$$

若合并后的实际簇数为 $k$，使用参数数目 $p=k(d+1)$，评分为

$$BIC=N\ln\left(\frac{SSE}{N}\right)+k(d+1)\ln N.$$

BIC 越小越好 。前一项衡量拟合误差，后一项惩罚过多的簇。计算中用 $(SSE+10^{-8})/N$ 保护对数输入。

按点的第一维坐标升序稳定排序；请求 $K>1$ 个簇时，初始中心取排序后下标 $i(N-1)\mathbin{//}(K-1)$ 的点，其中 $i=0,\ldots,K-1$。$K=1$ 单独取排序后的第一个点。 按欧氏距离平方分配点；距离相等时取编号最小的簇。 非空簇更新为所属点的均值；空簇保留旧中心。 交替分配、更新；一轮分配后所有标签不变时收敛。 先令 $K_{max}=\min(K_{max},N)$；若此时 $K_{min}>K_{max}$，令 $K_{min}=K_{max}$。上下界相同时只运行一次。 收敛后，中心距离平方严格小于 $10^{-4}$ 的簇需要合并，标签同步映射；合并后的中心使用所属全部点的均值。 用合并后的实际簇数和 SSE 计算 BIC；BIC 并列时选择较小的枚举 $K$。实现使用 $10^{-9}$ 的比较容差。 输出前按中心第一维升序重新编号为 $0,1,\ldots,k-1$；第一维相同保持原编号顺序，点标签仍按输入顺序输出。

实现口径 ：近邻关系不一定具有传递性，本文按材料题解的“归为同一组”实现：在合并前的中心之间连边，合并每个连通分量，然后重新求均值，不反复合并新均值。完全为空的分量保留代表中心。此细节不应被误认为所有 X-Means 实现通用的规则。

## 输入描述

第一行：两个整数 $N,d$。 接下来 $N$ 行：每行 $d$ 个浮点数，表示一个点。 最后一行：两个整数 $K_{min},K_{max}$。

## 输出描述

第一行输出实际簇数 $k$；接下来 $k$ 行输出中心，各坐标保留两位小数；最后一行输出 $N$ 个标签。无法聚类时输出 0 。

## 数据范围与边界

$1\le N\le 2000$，$1\le d\le 10$。 每个坐标的绝对值不超过 $10^4$。 正常输入保证 $1\le K_{min}\le K_{max}\le N$；材料同时给出越界截断规则，实现仍保留该保护。 材料未给出可保证收敛的固定迭代轮数；以下代码按标签不变停止，不把任意迭代上限说成题面保证。

## 样例 1

输入

输出

每两个相邻点组成一个紧密簇，中心是各自的坐标均值。

```text
6 2
0.0 0.0
1.0 0.0
5.0 5.0
6.0 5.0
10.0 10.0
11.0 10.0
1 3
3
0.50 0.00
5.50 5.00
10.50 10.00
0 0 1 1 2 2
```

## 样例 2

输入

输出

两个簇已能很好地解释数据，继续增加簇带来的误差下降不足以抵消 BIC 的复杂度惩罚。

```text
4 2
0.0 0.0
1.0 0.0
10.0 10.0
11.0 10.0
1 3
2
0.50 0.00
10.50 10.00
0 0 1 1
```

## 思路分析

簇数增多通常能让点更接近某个中心。极端情况下，每个点单独成簇就能让 SSE 为零，但这样的模型未必有价值。题目给定的 BIC 把误差项与簇数惩罚放在一起比较，因此应完整枚举候选 $K$，不能看到 SSE 下降就立即接受，也不能假定 BIC 关于 $K$ 单调。

各个 $K$ 必须独立初始化、独立迭代，不能直接把上一轮的中心拿来续算，否则就不是题目指定的确定性结果。

分配时只比较距离平方，省去开根号。从小编号向大编号扫描，只有距离严格更小时才替换，这自然实现距离平局取小编号。

更新时累计每个簇的点数和各维坐标和，非空簇取均值，空簇跳过。上一轮已经更新过中心，如果新一轮标签完全相同，那么再更新得到的均值也相同，可以直接结束。

第一维的稳定排序只需预处理一次；初始化时按当前 $K$ 取不同的等距下标。

把合并前的中心看成图的顶点，距离平方小于阈值时连边。使用并查集维护连通分量，并让较小编号作为代表，避免归组结果取决于边的处理顺序。

接着将每个点的旧标签映射到所在分量，重新统计点数和坐标和。合并中心必须是 所属点的加权均值 ，不能对原中心直接等权平均，因为不同簇的点数可能不同。最后用新中心和新标签重新计算 SSE。

此时请求簇数与实际簇数可能不同，甚至实际簇数小于 $K_{min}$；BIC 中应使用实际簇数。

从小到大枚举 $K$，仅当新 BIC 小于当前最优值减去 $10^{-9}$ 时替换。这样将容差范围内的差异视为平局，保留先出现的小 $K$。这属于浮点比较约定，并不表示相差极小的两个真实数严格相等。

统一使用 $SSE+10^{-8}$ 与材料题解保持一致。这个平滑项在 SSE 极小时可能影响分数，不能断言它对所有正 SSE 都毫无影响；SSE 为零也不要求全部输入点相同，各簇内点分别重合时同样可能发生。

选定结果后再排序中心并重映射标签。仅在格式化后将字符串 -0.00 改成 0.00 ，不要提前修改坐标，否则会影响距离和 BIC。

## 正确性说明

1. 每一轮执行了规定的 K-Means 操作。 固定中心时，每个点选距离平方最小的中心，逐点最小化当前分配的 SSE，并按扫描顺序解决距离平局。固定标签时，对某个非空簇及任意中心 $a$，有

$$\sum_{x\in C}\lVert x-a\rVert^2 =\sum_{x\in C}\lVert x-\bar x\rVert^2 +\lvert C\rvert\cdot\lVert a-\bar x\rVert^2.$$

其中 $\bar x$ 为均值，故均值最小化该簇的 SSE；空簇对 SSE 无贡献，保留旧中心符合规则。因此交替操作不会增加 SSE。标签不变时，均值也不变，结果满足指定的停止条件。

2. 合并符合分组口径。 并查集恰好连接所有满足阈值的中心对，其分量就是规定的合并组。重映射后每个点仍恰好属于一个组；按该组全部点求均值，得到一致的中心、标签和 SSE。

3. 枚举保留最优候选。 每轮得到的 BIC 都使用合并后的实际簇数。按约定的浮点比较规则维护最优值，枚举结束后保留评分最优的候选，容差内并列保留较小的请求 $K$。最后的重编号只改变名称，不改变聚类。

这里证明的是 实现符合本题算法 ，不是证明 K-Means 求得全局最小 SSE，也不保证 BIC 选出的簇数一定等于数据的真实类别数。

## 题解代码

仅使用 Python 标准库，ACM 输入输出。为便于核对，代码将 K-Means、中心合并和模型选择分开实现。

### Python 实现

```python
# 题目：X-Means 聚类算法的实现
# 算法：排序 + 扫描
# 模式：ACM（stdin/stdout）
# 复杂度：时间 总时间可保守写为 O(N N+_K=K_min^K_max [T_KNKd+K^2(d+(K+1))]). 空间复杂度 ：O(Nd+K_maxd+N)=O(Nd)，因为截断后 K_max N；空间 O(Nd+K_maxd+N)=O(Nd)，因为截断后 K_max N

import sys
import math

MERGE_EPS = 1e-4
BIC_EPS = 1e-9


# 核心函数：dist2
def dist2(a, b):
    value = 0.0
    for x, y in zip(a, b):
        delta = x - y
        value += delta * delta
    # 返回结果
    return value


# 核心函数：kmeans
def kmeans(points, order, d, k):
    n = len(points)
    centers = []
    # 枚举位置 i
    for i in range(k):
        pos = 0 if k == 1 else i * (n - 1) // (k - 1)
        centers.append(points[order[pos]][:])

    labels = [-1] * n
    # 循环处理
    while True:
        new_labels = []
        # 遍历 point
        for point in points:
            best = 0
            best_dist = dist2(point, centers[0])
            # 遍历 c
            for c in range(1, k):
                current = dist2(point, centers[c])
                # 条件判断
                if current < best_dist:
                    best, best_dist = c, current
            new_labels.append(best)

        # 条件判断
        if new_labels == labels:
            # 返回结果
            return centers, labels
        labels = new_labels

        counts = [0] * k
        totals = [[0.0] * d for _ in range(k)]
        for point, c in zip(points, labels):
            counts[c] += 1
            # 枚举阶段 j
            for j in range(d):
                totals[c][j] += point[j]
        # 遍历 c
        for c in range(k):
            # 条件判断
            if counts[c]:
                centers[c] = [v / counts[c] for v in totals[c]]


# 核心函数：merge_centers
def merge_centers(points, centers, labels, d):
    k = len(centers)
    parent = list(range(k))

    # 核心函数：find
    def find(x):
        # 循环处理
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        # 返回结果
        return x

    # 所有距离都使用合并前的中心，不在枚举中修改中心。
    # 遍历 a
    for a in range(k):
        # 枚举分割点 b
        for b in range(a + 1, k):
            # 条件判断
            if dist2(centers[a], centers[b]) < MERGE_EPS:
                ra, rb = find(a), find(b)
                # 条件判断
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

    roots = [find(c) for c in range(k)]
    representatives = sorted(set(roots))
    number = {root: i for i, root in enumerate(representatives)}
    new_labels = [number[roots[c]] for c in labels]
    size = len(representatives)
    counts = [0] * size
    totals = [[0.0] * d for _ in range(size)]
    for point, c in zip(points, new_labels):
        counts[c] += 1
        # 枚举阶段 j
        for j in range(d):
            totals[c][j] += point[j]

    merged = []
    for c, root in enumerate(representatives):
        # 条件判断
        if counts[c]:
            merged.append([v / counts[c] for v in totals[c]])
        else:
            merged.append(centers[root][:])
    # 返回结果
    return merged, new_labels


# 核心函数：main
def main():
    stream = iter(sys.stdin.buffer.read().split())
    first = next(stream, None)
    # 条件判断
    if first is None:
        # 返回结果
        return
    n, d = int(first), int(next(stream))
    # 条件判断
    if n <= 0 or d <= 0:
        print(0)
        # 返回结果
        return
    points = [[float(next(stream)) for _ in range(d)] for _ in range(n)]
    kmin, kmax = int(next(stream)), int(next(stream))
    kmax = min(kmax, n)
    kmin = min(kmin, kmax)
    # 条件判断
    if kmin < 1:
        print(0)
        # 返回结果
        return

    order = sorted(range(n), key=lambda i: points[i][0])
    best_bic = math.inf
    best_centers = best_labels = None
    # 遍历 k
    for k in range(kmin, kmax + 1):
        centers, labels = kmeans(points, order, d, k)
        centers, labels = merge_centers(points, centers, labels, d)
        sse = sum(dist2(point, centers[c])
                  for point, c in zip(points, labels))
        bic = (n * math.log((sse + 1e-8) / n)
               + len(centers) * (d + 1) * math.log(n))
        # 条件判断
        if bic < best_bic - BIC_EPS:
            best_bic = bic
            best_centers, best_labels = centers, labels

    order = sorted(range(len(best_centers)),
                   key=lambda c: (best_centers[c][0], c))
    remap = {old: new for new, old in enumerate(order)}
    print(len(order))
    # 遍历 c
    for c in order:
        row = []
        # 遍历 value
        for value in best_centers[c]:
            text = f"{value:.2f}"
            row.append("0.00" if text == "-0.00" else text)
        print(" ".join(row))
    print(" ".join(str(remap[c]) for c in best_labels))


if __name__ == "__main__":
    main()
```

## 复杂度分析

记候选簇数为 $K$，其 K-Means 分配轮数为 $T_K$。

排序预处理：$O(N\log N)$。 固定 $K$ 的分配、更新：$O(T_KNKd)$。 合并时检查中心对的距离：$O(K^2d)$；并查集使用路径压缩、按较小编号连接，未使用按秩合并，保守另计 $O(K^2\log(K+1))$ 的摊还上界。 重算均值与 SSE：$O(Nd+Kd)$；最终排序和重编号不超过 $O(K_{max}\log K_{max}+N)$。

时间复杂度 ：总时间可保守写为

$$O\left(N\log N+\sum_{K=K_{min}}^{K_{max}} \left[T_KNKd+K^2\bigl(d+\log(K+1)\bigr)\right]\right).$$

空间复杂度 ：$O(Nd+K_{max}d+N)=O(Nd)$，因为截断后 $K_{max}\le N$。只保留当前候选和最佳候选，不存储全部枚举结果。

性能边界 ：若允许枚举从小簇数直到 $N$，该纯 Python 直接实现的最坏代价较高。材料未披露时间限制、总迭代预算或更小的枚举跨度，不能仅凭样例通过就声称覆盖最大规模的运行时间保证；也不能为了加速擅自提前停止枚举。

### Java 实现

```java
// 题目：X-Means 聚类算法的实现
// 算法：排序 + 扫描
// 模式：ACM（stdin/stdout）
// 复杂度：时间 总时间可保守写为 O(N N+_K=K_min^K_max [T_KNKd+K^2(d+(K+1))]). 空间复杂度 ：O(Nd+K_maxd+N)=O(Nd)，因为截断后 K_max N；空间 O(Nd+K_maxd+N)=O(Nd)，因为截断后 K_max N

import java.io.*;
import java.util.*;
public class Main {
    static final double MERGE_EPS=1e-4;
    static final double BIC_EPS=1e-9;
    // 核心方法：dist2
    static double dist2(double[] a,double[] b) {
        double v=0.0;
        // 枚举位置 i
        for(int i=0;i<a.length;i++) {
            double d=a[i]-b[i];
            v+=d*d;
        }
        // 返回结果
        return v;
    }
    // 核心方法：find
    static int find(int[] p,int x) {
        // 循环处理
        while(p[x]!=x) {
            p[x]=p[p[x]];
            x=p[x];
        }
        // 返回结果
        return x;
    }
    // 核心方法：kmeans
    static double[][] kmeans(double[][] pts,int[] order,int d,int k,int[] outLab) {
        int n=pts.length;
        double[][] c=new double[k][];
        // 枚举位置 i
        for(int i=0;i<k;i++) {
            int pos=(k==1)?0:i*(n-1)/(k-1);
            c[i]=pts[order[pos]].clone();
        }
        int[] lab=new int[n];
        Arrays.fill(lab,-1);
        // 循环处理
        while(true) {
            int[] nl=new int[n];
            // 循环处理
            for(int p=0;p<n;p++) {
                int best=0;
                double bd=dist2(pts[p],c[0]);
                // 枚举阶段 j
                for(int j=1;j<k;j++) {
                    double cur=dist2(pts[p],c[j]);
                    // 条件判断
                    if(cur<bd) {
                        best=j;
                        bd=cur;
                    }
                }
                nl[p]=best;
            }
            // 条件判断
            if(Arrays.equals(nl,lab)) {
                System.arraycopy(lab,0,outLab,0,n);
                // 返回结果
                return c;
            }
            lab=nl;
            int[] cnt=new int[k];
            double[][] tot=new double[k][d];
            // 循环处理
            for(int p=0;p<n;p++) {
                int ci=lab[p];
                cnt[ci]++;
                // 枚举阶段 j
                for(int j=0;j<d;j++)tot[ci][j]+=pts[p][j];
            }
            // 循环处理
            for(int ci=0;ci<k;ci++)if(cnt[ci]!=0)for(int j=0;j<d;j++)c[ci][j]=tot[ci][j]/cnt[ci];
        }
    }
    // 核心方法：mergeCenters
    static Object[] mergeCenters(double[][] pts,double[][] c,int[] lab,int d) {
        int k=c.length;
        int[] par=new int[k];
        // 枚举位置 i
        for(int i=0;i<k;i++)par[i]=i;
        // 循环处理
        for(int a=0;a<k;a++)for(int b=a+1;b<k;b++)if(dist2(c[a],c[b])<MERGE_EPS) {
            int ra=find(par,a),rb=find(par,b);
            // 条件判断
            if(ra!=rb)par[Math.max(ra,rb)]=Math.min(ra,rb);
        }
        int[] roots=new int[k];
        TreeSet<Integer> set=new TreeSet<>();
        // 枚举位置 i
        for(int i=0;i<k;i++) {
            roots[i]=find(par,i);
            set.add(roots[i]);
        }
        List<Integer> reps=new ArrayList<>(set);
        HashMap<Integer,Integer> num=new HashMap<>();
        // 枚举位置 i
        for(int i=0;i<reps.size();i++)num.put(reps.get(i),i);
        int size=reps.size();
        int[] nl=new int[lab.length];
        // 枚举位置 i
        for(int i=0;i<lab.length;i++)nl[i]=num.get(roots[lab[i]]);
        int[] cnt=new int[size];
        double[][] tot=new double[size][d];
        // 循环处理
        for(int p=0;p<pts.length;p++) {
            int ci=nl[p];
            cnt[ci]++;
            // 枚举阶段 j
            for(int j=0;j<d;j++)tot[ci][j]+=pts[p][j];
        }
        double[][] merged=new double[size][];
        // 循环处理
        for(int ci=0;ci<size;ci++) {
            // 条件判断
            if(cnt[ci]!=0) {
                merged[ci]=new double[d];
                // 枚举阶段 j
                for(int j=0;j<d;j++)merged[ci][j]=tot[ci][j]/cnt[ci];
            } else merged[ci]=c[reps.get(ci)].clone();
        }
        // 返回结果
        return new Object[] {
            merged,nl
        }
        ;
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args)throws Exception {
        byte[] raw=System.in.readAllBytes();
        String text=new String(raw,java.nio.charset.StandardCharsets.UTF_8).trim();
        // 条件判断
        if(text.isEmpty())return;
        StringTokenizer st=new StringTokenizer(text);
        int n=Integer.parseInt(st.nextToken());
        int d=Integer.parseInt(st.nextToken());
        // 条件判断
        if(n<=0||d<=0) {
            System.out.println(0);
            // 返回结果
            return;
        }
        double[][] pts=new double[n][d];
        // 枚举位置 i
        for(int i=0;i<n;i++)for(int j=0;j<d;j++)pts[i][j]=Double.parseDouble(st.nextToken());
        int kmin=Integer.parseInt(st.nextToken());
        int kmax=Integer.parseInt(st.nextToken());
        kmax=Math.min(kmax,n);
        kmin=Math.min(kmin,kmax);
        // 条件判断
        if(kmin<1) {
            System.out.println(0);
            // 返回结果
            return;
        }
        Integer[] ord=new Integer[n];
        // 枚举位置 i
        for(int i=0;i<n;i++)ord[i]=i;
        final double[][] P=pts;
        Arrays.sort(ord,(x,y)-> {
            int r=Double.compare(P[x][0],P[y][0]);return r!=0?r:Integer.compare(x,y);
        }
        );
        int[] order=new int[n];
        // 枚举位置 i
        for(int i=0;i<n;i++)order[i]=ord[i];
        double bestBic=Double.POSITIVE_INFINITY;
        double[][] bestC=null;
        int[] bestL=null;
        // 循环处理
        for(int k=kmin;k<=kmax;k++) {
            int[] lab=new int[n];
            double[][] c=kmeans(pts,order,d,k,lab);
            Object[] mr=mergeCenters(pts,c,lab,d);
            c=(double[][])mr[0];
            lab=(int[])mr[1];
            double sse=0.0;
            // 循环处理
            for(int p=0;p<n;p++)sse+=dist2(pts[p],c[lab[p]]);
            double bic=n*Math.log((sse+1e-8)/n)+c.length*(d+1)*Math.log(n);
            // 条件判断
            if(bic<bestBic-BIC_EPS) {
                bestBic=bic;
                bestC=c;
                bestL=lab;
            }
        }
        Integer[] co=new Integer[bestC.length];
        // 枚举位置 i
        for(int i=0;i<co.length;i++)co[i]=i;
        final double[][] BC=bestC;
        Arrays.sort(co,(x,y)-> {
            int r=Double.compare(BC[x][0],BC[y][0]);return r!=0?r:Integer.compare(x,y);
        }
        );
        int[] remap=new int[bestC.length];
        // 枚举位置 i
        for(int i=0;i<co.length;i++)remap[co[i]]=i;
        StringBuilder sb=new StringBuilder();
        sb.append(co.length).append((char)10);
        // 循环处理
        for(int oi=0;oi<co.length;oi++) {
            int ci=co[oi];
            StringBuilder row=new StringBuilder();
            // 枚举阶段 j
            for(int j=0;j<bestC[ci].length;j++) {
                String s=String.format(Locale.ROOT,"%.2f",bestC[ci][j]);
                // 条件判断
                if(s.equals("-0.00"))s="0.00";
                // 条件判断
                if(j>0)row.append(' ');
                row.append(s);
            }
            sb.append(row).append((char)10);
        }
        // 循环处理
        for(int p=0;p<bestL.length;p++) {
            // 条件判断
            if(p>0)sb.append(' ');
            sb.append(remap[bestL[p]]);
        }
        sb.append((char)10);
        System.out.print(sb);
    }
}
```
