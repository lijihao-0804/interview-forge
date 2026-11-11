# DBSCAN 点类型判定

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/jd/algo-20260926/" target="_blank" rel="noopener noreferrer">原题解析</a> · 京东 · 2026-09-26 · 算法岗 · ACM 模式（stdin/stdout）

## 题目描述

给定 $n$ 个 $d$ 维样本，邻域半径 eps 和最小样本数 min_samples 。不需要求聚类簇编号，只需输出每个点的类型：核心点为 2 ，边界点为 1 ，噪声点为 0 。

点 $i$ 的邻域包含所有与它的欧氏距离不超过 eps 的点， 包含点自身 。若邻域点数不少于 min_samples ，该点是核心点；否则，如果它位于至少一个核心点的邻域内，就是边界点；剩余点为噪声点。边界点不能像核心点一样继续扩张邻域。

输入一行 JSON，字段 X 为样本矩阵， eps 为正浮点数， min_samples 为不小于 $1$ 的整数。约束为 $1<n<20$、$0<d<10$。

输出一行长度为 $n$ 的 JSON 整数数组，元素间保留空格。数值计算只允许使用 NumPy、pandas 或 scikit-learn；下面使用 NumPy，标准库负责输入输出与 JSON 解析。

## 样例

输入

输出

```text
{"X":[[0,0],[0,0.1],[0.1,0],[5,5]],"eps":0.2,"min_samples":3}
[2, 2, 2, 0]
```

## 思路分析

第一步：把邻域关系表示成矩阵。

类型判定只依赖两点是否相邻，无须执行完整的 DBSCAN 聚类。计算

再令 $A_{ij}$ 表示 $D_{ij}\le\mathrm{eps}^2$。比较平方距离可避免开平方，不能把 <= 改成 < ，也不应擅自引入容差改变题目规则。矩阵对角线为真，自身已经计算在邻域内，不要额外加一。

第二步：先确定全部核心点。

矩阵每行的真值数量就是对应点的邻域大小。把行和与 min_samples 比较，得到核心点掩码。样例的前三个点互相相邻，每个都有三个邻居，因此均为核心点。

第三步：只检查核心点对应的列。

对于非核心点，如果它所在行在某个核心点列上为真，就应输出边界点。欧氏距离对称，因此“它靠近某个核心点”与“它落在核心点邻域里”等价。必须先判核心，再判边界，不能把同时邻近其他核心点的核心点降级。

当没有核心点时，取出的矩阵有零列，NumPy 的 any(axis=1) 为每一行返回假，因此自然全部输出噪声点。当 min_samples=1 时，所有点都因自身而成为核心点。最终用 tolist() 转为 Python 整数列表，再由 json.dumps 生成规定格式。

## 题解代码

### Python 实现

```python
# 题目：DBSCAN 点类型判定
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(n^2d)，枚举所有点对并计算各维度差值，后续布尔运算不超过 O(n^2)；空间 O(n^2d)，主要为广播得到的三维差值张量

import sys
import json
import numpy as np


def classify_points(x, eps, min_samples):
    diff = x[:, None, :] - x[None, :, :]
    adjacent = np.sum(diff * diff, axis=2) <= eps * eps
    core = adjacent.sum(axis=1) >= min_samples
    near_core = adjacent[:, core].any(axis=1)
    types = np.zeros(len(x), dtype=int)
    types[near_core & ~core] = 1
    types[core] = 2
    return types.tolist()


# 读取输入并输出答案
):
    data = json.loads(sys.stdin.readline())
    x = np.asarray(data["X"], dtype=float)
    result = classify_points(x, float(data["eps"]), int(data["min_samples"]))
    print(json.dumps(result))


if __name__ == "__main__":
    solve()
```

## 复杂度分析

时间复杂度 ：$O(n^2d)$，枚举所有点对并计算各维度差值，后续布尔运算不超过 $O(n^2)$。

空间复杂度 ：$O(n^2d)$，主要为广播得到的三维差值张量。

### Java 实现

```java
// 题目：DBSCAN 点类型判定
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(n^2d)，枚举所有点对并计算各维度差值，后续布尔运算不超过 O(n^2)；空间 O(n^2d)，主要为广播得到的三维差值张量

import java.util.*;
public class Main {
    static class Json {
        private final String s; private int i;
        Json(String s) { this.s = s; }
        static Object parse(String s) { Json j = new Json(s); j.ws(); return j.value(); }
        private void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }
        private Object value() {
            ws(); char c = s.charAt(i);
            if (c == '{') return object();
            if (c == '[') return array();
            if (c == '"') return string();
            if (c == 't') { i += 4; return Boolean.TRUE; }
            if (c == 'f') { i += 5; return Boolean.FALSE; }
            if (c == 'n') { i += 4; return null; }
            return number();
        }
        private Map<String,Object> object() {
            Map<String,Object> m = new LinkedHashMap<>();
            i++; ws();
            if (s.charAt(i) == '}') { i++; return m; }
            while (true) {
                ws(); String k = string(); ws(); i++;
                Object v = value(); m.put(k, v); ws();
                char c = s.charAt(i++); if (c == '}') break;
            }
            return m;
        }
        private List<Object> array() {
            List<Object> a = new ArrayList<>();
            i++; ws();
            if (s.charAt(i) == ']') { i++; return a; }
            while (true) {
                a.add(value()); ws();
                char c = s.charAt(i++); if (c == ']') break;
            }
            return a;
        }
        private String string() {
            StringBuilder b = new StringBuilder(); i++;
            while (true) {
                char c = s.charAt(i++);
                if (c == '"') break;
                if (c == (char)92) { char e = s.charAt(i++); if (e == 'n') b.append((char)10); else b.append(e); }
                else b.append(c);
            }
            return b.toString();
        }
        private Object number() {
            int start = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            return Double.parseDouble(s.substring(start, i));
        }
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws Exception {
        java.io.BufferedReader br = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String line = br.readLine();
        Map<String,Object> data = (Map<String,Object>) Json.parse(line);
        List<Object> xObj = (List<Object>) data.get("X");
        int n = xObj.size();
        int d = ((List<Object>) xObj.get(0)).size();
        double[][] x = new double[n][d];
        for (int i = 0; i < n; i++) { List<Object> row = (List<Object>) xObj.get(i); for (int j = 0; j < d; j++) x[i][j] = ((Number) row.get(j)).doubleValue(); }
        double eps = ((Number) data.get("eps")).doubleValue();
        int minSamples = ((Number) data.get("min_samples")).intValue();
        double eps2 = eps * eps;
        boolean[] core = new boolean[n];
        for (int i = 0; i < n; i++) { int cnt = 0; for (int j = 0; j < n; j++) { double dd = 0; for (int k = 0; k < d; k++) { double df = x[i][k] - x[j][k]; dd += df * df; } if (dd <= eps2) cnt++; } core[i] = cnt >= minSamples; }
        int[] types = new int[n];
        for (int i = 0; i < n; i++) {
            boolean nearCore = false;
            for (int j = 0; j < n; j++) { if (!core[j]) continue; double dd = 0; for (int k = 0; k < d; k++) { double df = x[i][k] - x[j][k]; dd += df * df; } if (dd <= eps2) { nearCore = true; break; } }
            if (core[i]) types[i] = 2; else if (nearCore) types[i] = 1; else types[i] = 0;
        }
        StringBuilder sb = new StringBuilder();
        sb.append('[');
        for (int i = 0; i < n; i++) { if (i > 0) sb.append(", "); sb.append(types[i]); }
        sb.append(']');
        System.out.println(sb);
    }
}
```
