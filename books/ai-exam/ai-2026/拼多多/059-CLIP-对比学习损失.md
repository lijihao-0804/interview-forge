# CLIP 对比学习损失

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/pinduoduo/algo-20260702/" target="_blank" rel="noopener noreferrer">原题解析</a> · 拼多多 · 2026-07-02 · 算法岗 · ACM 模式（stdin/stdout）

## 题目描述

实现 CLIP 对比学习损失函数。给定已 L2 归一化的图像嵌入矩阵（$N \times D$）、文本嵌入矩阵（$N \times D$）和温度参数 $\tau$：

计算相似度矩阵 $S = I \cdot T^\top / \tau$ 标签在对角线：第 $i$ 个图像匹配第 $i$ 个文本 图像→文本方向和文本→图像方向各做 softmax 交叉熵，取平均

输出最终损失值，保留 6 位小数。仅使用 NumPy。

## 样例

输入

输出

```text
{"image_embeds": [[1, 0], [0, 1]], "text_embeds": [[1, 0], [0, 1]], "temperature": 1.0}
0.313262
```

## 思路分析

第一步：相似度矩阵

图像与文本先做矩阵乘法再除以温度，得到 $N \times N$ 的 logits 矩阵。第 $i$ 行第 $j$ 列是图像 $i$ 与文本 $j$ 的相似度。

第二步：对比学习的标签在对角线

一个 batch 里第 $i$ 个图像的正确匹配就是第 $i$ 个文本，标签为 $\text{diag}(0, 1, …, N-1)$。

第三步：数值稳定的交叉熵

对每一行先减去行最大值再取指数（避免溢出）。单行交叉熵 = log-sum-exp - 标签位置的分数（即对角元）。对所有行求平均得该方向的损失。

第四步：双向取平均

图像→文本对 $S$ 的每一行做 softmax 交叉熵；文本→图像对 $S^\top$ 做同样计算。最终损失为两者均值。

## 题解代码

### Python 实现

```python
# 题目：CLIP 对比学习损失
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）
# 复杂度：时间 O(N^2 D)，主要开销是相似度矩阵的矩阵乘法；空间 O(N^2)，存储 logits 矩阵

import sys
import json
import numpy as np

# 读取输入并输出答案
def solve():
    data = json.loads(input())
    img = np.array(data['image_embeds'], dtype=np.float64)
    txt = np.array(data['text_embeds'], dtype=np.float64)
    temperature = float(data['temperature'])

    logits = img @ txt.T / temperature

    # 核心函数：cross_entropy
    def cross_entropy(mat):
        row_max = mat.max(axis=1, keepdims=True)
        log_sum = row_max[:, 0] + np.log(np.exp(mat - row_max).sum(axis=1))
        diag = np.diag(mat)
        # 返回结果
        return float((log_sum - diag).mean())

    loss = (cross_entropy(logits) + cross_entropy(logits.T)) / 2.0
    print(f"{loss:.6f}")

solve()
```

## 复杂度分析

时间复杂度 ：$O(N^2 D)$，主要开销是相似度矩阵的矩阵乘法。 空间复杂度 ：$O(N^2)$，存储 logits 矩阵。

### Java 实现

```java
// 题目：CLIP 对比学习损失
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）
// 复杂度：时间 O(N^2 D)，主要开销是相似度矩阵的矩阵乘法；空间 O(N^2)，存储 logits 矩阵

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
    static String nextLine() throws IOException { return br.readLine(); }

    static class Json {
        String s;
        int i=0;
        Json(String s) {
            this.s=s;
        }
        Object parse() {
            // 返回结果
            return value();
        }
        void ws() {
            // 循环处理
            while(i<s.length()&&Character.isWhitespace(s.charAt(i)))i++;
        }
        Object value() {
            ws();
            char c=s.charAt(i);
            // 条件判断
            if(c=='{')return obj();
            // 条件判断
            if(c=='[')return arr();
            // 条件判断
            if(c=='"')return str();
            // 条件判断
            if(c=='t') {
                i+=4;
                // 返回结果
                return Boolean.TRUE;
            }
            // 条件判断
            if(c=='f') {
                i+=5;
                // 返回结果
                return Boolean.FALSE;
            }
            // 条件判断
            if(c=='n') {
                i+=4;
                // 返回结果
                return null;
            }
            int st=i;
            // 循环处理
            while(i<s.length()&&"-+.eE0123456789".indexOf(s.charAt(i))>=0)i++;
            // 返回结果
            return Double.parseDouble(s.substring(st,i));
        }
        Map<String,Object> obj() {
            Map<String,Object> m=new LinkedHashMap<>();
            i++;
            ws();
            // 条件判断
            if(s.charAt(i)=='}') {
                i++;
                // 返回结果
                return m;
            }
            // 循环处理
            while(true) {
                ws();
                String k=str();
                ws();
                i++;
                Object v=value();
                m.put(k,v);
                ws();
                char c=s.charAt(i);
                i++;
                // 条件判断
                if(c=='}')break;
            }
            // 返回结果
            return m;
        }
        List<Object> arr() {
            List<Object> l=new ArrayList<>();
            i++;
            ws();
            // 条件判断
            if(s.charAt(i)==']') {
                i++;
                // 返回结果
                return l;
            }
            // 循环处理
            while(true) {
                l.add(value());
                ws();
                char c=s.charAt(i);
                i++;
                // 条件判断
                if(c==']')break;
            }
            // 返回结果
            return l;
        }
        String str() {
            StringBuilder sb=new StringBuilder();
            i++;
            // 循环处理
            while(s.charAt(i)!='"') {
                sb.append(s.charAt(i));
                i++;
            }
            i++;
            // 返回结果
            return sb.toString();
        }
    }
    // 核心方法：toMat
    static double[][] toMat(List<Object> l) {
        double[][] m=new double[l.size()][];
        // 枚举位置 i
        for(int i=0;i<l.size();i++) {
            List<Object> row=(List<Object>)l.get(i);
            m[i]=new double[row.size()];
            // 枚举阶段 j
            for(int j=0;j<row.size();j++)m[i][j]=((Number)row.get(j)).doubleValue();
        }
        // 返回结果
        return m;
    }
    // 核心方法：crossEntropy
    static double crossEntropy(double[][] m) {
        int n=m.length;
        double sum=0;
        // 枚举位置 i
        for(int i=0;i<n;i++) {
            double mx=Double.NEGATIVE_INFINITY;
            // 枚举阶段 j
            for(int j=0;j<m[i].length;j++)mx=Math.max(mx,m[i][j]);
            double s=0;
            // 枚举阶段 j
            for(int j=0;j<m[i].length;j++)s+=Math.exp(m[i][j]-mx);
            sum+=(mx+Math.log(s))-m[i][i];
        }
        // 返回结果
        return sum/n;
    }
    // 核心方法：transpose
    static double[][] transpose(double[][] a) {
        int r=a.length,c=a[0].length;
        double[][] t=new double[c][r];
        // 枚举位置 i
        for(int i=0;i<r;i++)for(int j=0;j<c;j++)t[j][i]=a[i][j];
        // 返回结果
        return t;
    }
    // 主函数：读取输入并输出答案
    public static void main(String[] a) throws IOException {
        String line=nextLine();
        // 条件判断
        if(line==null)return;
        Object parsed=new Json(line).parse();
        Map<String,Object> root=(Map<String,Object>)parsed;
        double[][] img=toMat((List<Object>)root.get("image_embeds"));
        double[][] txt=toMat((List<Object>)root.get("text_embeds"));
        double temp=((Number)root.get("temperature")).doubleValue();
        int N=img.length,D=img[0].length,M=txt.length;
        double[][] logits=new double[N][M];
        // 枚举位置 i
        for(int i=0;i<N;i++)for(int j=0;j<M;j++) {
            double s=0;
            // 循环处理
            for(int k=0;k<D;k++)s+=img[i][k]*txt[j][k];
            logits[i][j]=s/temp;
        }
        double loss=(crossEntropy(logits)+crossEntropy(transpose(logits)))/2.0;
        System.out.println(String.format(Locale.ROOT,"%.6f",loss));
    }
}
```
