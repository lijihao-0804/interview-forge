# KV Cache 稀疏化管理器

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260715/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-07-15 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

在大语言模型（LLM）的自回归推理中，KV Cache 用于缓存历史 token 的 Key 和 Value 张量，其显存占用随序列长度线性增长。为支持长上下文，系统设定容量上限 $K$，仅保留注意力分数最高的 $K$ 个 token。

需要支持两种操作：

ADD pos score ：插入一个新 token 的 KV 对及其注意力分数。插入后若缓存数量超过 $K$，立即淘汰分数最低的 token；若最低分并列，则淘汰位置编号 pos 最小的 token。 QUERY ：按位置编号 pos 从小到大输出当前缓存中的所有 token 及其 KV。

## 输入格式

第一行包含两个整数 $K,N$，分别表示容量上限和操作数量，其中 $1\le K,N\le10^5$。

接下来有 $N$ 个操作：

ADD 操作占三行。第一行是 ADD pos score ，其中 $0\le pos\le10^9$， pos 唯一且随插入顺序严格递增，$0.0\le score\le1000.0$；第二行是 Key 向量的 $4$ 个浮点数；第三行是 Value 向量的 $4$ 个浮点数。 QUERY 操作占一行，仅包含 QUERY 。

## 输出格式

对每个 ADD 操作，如果触发淘汰，输出一行 PRUNED pos ；未触发则不输出。

对每个 QUERY 操作，先输出当前缓存数量 $M$，然后按 pos 升序输出 $M$ 组数据。每组占三行，依次为 pos score 、Key 向量和 Value 向量。分数与向量必须按照插入时的文本原样输出。

## 样例

输入

输出

```text
3 7
ADD 0 5.0
1.0 2.0 3.0 4.0
0.1 0.2 0.3 0.4
ADD 1 2.0
2.0 2.0 2.0 2.0
0.5 0.5 0.5 0.5
ADD 2 8.0
3.0 3.0 3.0 3.0
0.9 0.9 0.9 0.9
QUERY
ADD 3 6.0
4.0 4.0 4.0 4.0
0.0 0.0 0.0 0.0
QUERY
ADD 4 9.0
5.0 5.0 5.0 5.0
1.0 1.0 1.0 1.0
3
0 5.0
1.0 2.0 3.0 4.0
0.1 0.2 0.3 0.4
1 2.0
2.0 2.0 2.0 2.0
0.5 0.5 0.5 0.5
2 8.0
3.0 3.0 3.0 3.0
0.9 0.9 0.9 0.9
PRUNED 1
3
0 5.0
1.0 2.0 3.0 4.0
0.1 0.2 0.3 0.4
2 8.0
3.0 3.0 3.0 3.0
0.9 0.9 0.9 0.9
3 6.0
4.0 4.0 4.0 4.0
0.0 0.0 0.0 0.0
PRUNED 0
```

## 思路分析

第一步：把查询和淘汰拆成两个排序维度

QUERY 要按 pos 递增输出，而淘汰要按 (score, pos) 递增选择。一个数据结构很难同时按两套关键字高效工作，因此分别维护缓存字典与最小堆。

第二步：用最小堆定位淘汰项

最小堆存放 (score, pos) 。Python 元组按第一项、第二项依次比较，所以堆顶恰好是分数最低且并列时 pos 最小的 token。分数使用 Decimal(score_text) 解析，避免二进制浮点舍入影响极接近分数的先后关系；用于输出的分数、Key 和 Value 则保留原始文本。

第三步：利用严格递增的 pos 保持查询顺序

题目保证 pos 唯一且随插入顺序严格递增。Python 3 的字典保持插入顺序，删除元素不会改变其余元素的相对顺序，因此直接遍历缓存字典就是按 pos 升序，无需在每次 QUERY 时重新排序。

第四步：维护同步不变量

每次插入同时写入字典和最小堆；超出容量时，从堆顶弹出同一个 token，并从字典删除。这样堆和缓存始终保存同一批 token，缓存数量不会超过 $K$。

以样例为例，前三个分数为 $5.0,2.0,8.0$，缓存刚好装满。插入分数 $6.0$ 后，堆顶 (2.0,1) 被淘汰；再插入 $9.0$ 后，新的堆顶 (5.0,0) 被淘汰。

## 题解代码

### Python 实现

```python
# 题目：KV Cache 稀疏化管理器
# 算法：堆 / 优先队列
# 模式：ACM（stdin/stdout）
# 复杂度：时间 每次 ADD 和淘汰均为 O( K)，每次 QUERY 为 O(M)，总时间复杂度为 O(N K+S)；空间 字典、最小堆与单次查询的输出缓冲区均为 O(K)

import heapq
import sys
from decimal import Decimal

input = sys.stdin.readline

capacity, operation_count = map(int, input().split())
cache = {}
min_heap = []
write = sys.stdout.write

# 遍历 _
for _ in range(operation_count):
    command = input().split()
    # 条件判断
    if command[0] == "ADD":
        pos = int(command[1])
        score_text = command[2]
        key_text = input().rstrip("\r\n")
        value_text = input().rstrip("\r\n")

        cache[pos] = (score_text, key_text, value_text)
        heapq.heappush(min_heap, (Decimal(score_text), pos))

        # 条件判断
        if len(cache) > capacity:
            _, pruned_pos = heapq.heappop(min_heap)
            del cache[pruned_pos]
            write(f"PRUNED {pruned_pos}\n")
    else:
        query_output = [str(len(cache))]
        for pos, (score_text, key_text, value_text) in cache.items():
            query_output.append(f"{pos} {score_text}")
            query_output.append(key_text)
            query_output.append(value_text)
        write("\n".join(query_output) + "\n")
```

## 复杂度分析

设一次查询时缓存中有 $M$ 个 token，所有查询实际输出的 token 总数为 $S$。

时间复杂度 ：每次 ADD 和淘汰均为 $O(\log K)$，每次 QUERY 为 $O(M)$，总时间复杂度为 $O(N\log K+S)$。

空间复杂度 ：字典、最小堆与单次查询的输出缓冲区均为 $O(K)$。

### Java 实现

```java
// 题目：KV Cache 稀疏化管理器
// 算法：堆 / 优先队列
// 模式：ACM（stdin/stdout）
// 复杂度：时间 每次 ADD 和淘汰均为 O( K)，每次 QUERY 为 O(M)，总时间复杂度为 O(N K+S)；空间 字典、最小堆与单次查询的输出缓冲区均为 O(K)

import java.io.*;
import java.math.BigDecimal;
import java.util.*;

public class Main {
    static final char NL = (char) 10;
    static class Entry {
        BigDecimal score;
        int pos;
        Entry(BigDecimal score, int pos) {
            this.score = score;
            this.pos = pos;
        }
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        StringBuilder sb = new StringBuilder();
        String first = br.readLine();
        // 条件判断
        if (first == null) return;
        StringTokenizer st = new StringTokenizer(first);
        int capacity = Integer.parseInt(st.nextToken());
        int operationCount = Integer.parseInt(st.nextToken());
        LinkedHashMap<Integer, String[]> cache = new LinkedHashMap<>();
        PriorityQueue<Entry> heap = new PriorityQueue<>(new Comparator<Entry>() {
            public int compare(Entry a, Entry b) {
                int c = a.score.compareTo(b.score);
                // 条件判断
                if (c != 0) return c;
                // 返回结果
                return Integer.compare(a.pos, b.pos);
            }
        });
        // 循环处理
        for (int op = 0; op < operationCount; op++) {
            String line = br.readLine();
            // 条件判断
            if (line == null) break;
            StringTokenizer cmd = new StringTokenizer(line);
            // 条件判断
            if (!cmd.hasMoreTokens()) continue;
            String command = cmd.nextToken();
            // 条件判断
            if (command.equals("ADD")) {
                int pos = Integer.parseInt(cmd.nextToken());
                String scoreText = cmd.nextToken();
                String keyText = br.readLine();
                String valueText = br.readLine();
                // 条件判断
                if (keyText == null) keyText = "";
                // 条件判断
                if (valueText == null) valueText = "";
                cache.put(pos, new String[]{scoreText, keyText, valueText});
                heap.add(new Entry(new BigDecimal(scoreText), pos));
                // 条件判断
                if (cache.size() > capacity) {
                    Entry pruned = heap.poll();
                    int prunedPos = pruned.pos;
                    cache.remove(prunedPos);
                    sb.append("PRUNED ").append(prunedPos).append(NL);
                }
            } else {
                sb.append(cache.size()).append(NL);
                // 循环处理
                for (Map.Entry<Integer, String[]> e : cache.entrySet()) {
                    String[] v = e.getValue();
                    sb.append(e.getKey()).append(' ').append(v[0]).append(NL);
                    sb.append(v[1]).append(NL);
                    sb.append(v[2]).append(NL);
                }
            }
        }
        System.out.print(sb);
    }
}
```
