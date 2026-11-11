# Agent 执行轨迹压缩

> <a href="https://onefly.top/zero2Leetcode/04_real_interviews/huawei/ai-20260715/" target="_blank" rel="noopener noreferrer">原题解析</a> · 华为 · 2026-07-15 · AI岗 · ACM 模式（stdin/stdout）

## 题目描述

一个 Agent 在 $n\times m$ 的二维网格上移动并执行操作。$n$ 和 $m$ 均为奇数，Agent 从网格正中心出发。每个时间步先移动、再操作，两件事合起来算作一步。

移动指令为 U 、 D 、 L 、 R 。如果移动后仍在网格内，Agent 到达新位置；如果移动越界，Agent 停留在原地，但仍会执行本步操作。

操作指令为：

I x ：将当前格子的状态值增加 $x$； D x ：将当前格子的状态值减少 $x$； N 0 ：不进行操作。

所有格子的初始状态均为 $0$。给定一条完整原轨迹，需要构造一条最短的语义等价轨迹，使新轨迹执行后的每个格子状态与原轨迹完全相同，起点仍是网格中心，终点也与原轨迹终点相同。输出最短轨迹长度。

构造语义说明 ：输入中的原轨迹满足 I / D 参数 $1\le x\le100$；本题来源题解对“构造出的新轨迹”采用的语义是 I / D 参数可以取任意正整数，因此到达一个非零目标格一次，就能用一次操作写入其最终净值。本文按这一语义求解。若新轨迹同样被限制为 $x\le100$，则还必须记录每个格子剩余的操作量，下面的状态压缩模型不再成立。

## 输入格式

第一行包含两个正整数 $n,m$，满足 $3\le n,m\le15$，并且 $n,m$ 均为奇数。

第二行包含一个正整数 $K$，表示原轨迹长度，满足 $1\le K\le2000$。

接下来 $K$ 行，每行包含 move op param ：

move 是 U 、 D 、 L 、 R 之一； op 是 I 、 D 、 N 之一； 当 op 为 I 或 D 时，$1\le param\le100$；当 op 为 N 时， param 固定为 $0$。

数据保证：原轨迹执行后，状态非零的格子不超过 $12$ 个。

## 输出格式

输出一个整数，表示最短语义等价轨迹的时间步数。

## 样例

输入

输出

原轨迹执行后的网格为：

非零格为 $(0,1)=3$、$(0,2)=-1$、$(1,2)=4$，终点为 $(1,2)$。从中心 $(1,1)$ 出发，依次向上、向右、向下，正好用三步访问三个目标格并停在原终点。

输入

输出

原轨迹执行后的网格为：

非零格为 $(1,3)=1$、$(1,4)=3$、$(2,4)=3$，终点为 $(2,4)$。一条最短轨迹是先从中心向上做无操作，再向右、向右、向下依次写入三个目标值，共四步。

最短轨迹可能不唯一，只需输出最短长度。初始时刻不能直接操作起点，必须先执行一次移动后才能对落点操作。

```text
3 3
5
U I 1
U I 2
R D 1
D I 3
R I 1
3
0 3 -1
0 0 4
0 0 0
5 5
6
R I 2
R D 1
U I 3
L I 1
D D 2
R I 4
4
0 0 0 0 0
0 0 0 1 3
0 0 0 0 3
0 0 0 0 0
0 0 0 0 0
```

## 思路分析

第一步：模拟原轨迹，得到真正需要复现的结果

从中心开始依次执行 $K$ 条指令。每一步先尝试移动；若越界就保留原位置；随后把 I 或 D 造成的净变化累加到当前位置。模拟结束后得到原终点 end ，以及每个格子的最终净值。

第二步：把数值问题转成访问目标格问题

在本文采用的构造语义下，新轨迹的操作参数没有上限。一个格子最终为正，就在第一次到达时执行一次 I ；最终为负，就执行一次 D 。因此只需要访问所有最终非零的格子，具体净值不必进入搜索状态。

把这些非零格子记为目标集合 $T$。题目保证 $\lvert T\rvert\le12$，可以给每个目标分配一个二进制位，用 mask 表示已经到达过哪些目标。

第三步：定义状态并使用 BFS

搜索状态是 (当前位置, mask) 。每次向四邻格移动一步；如果落到第 $i$ 个目标格，就执行对应操作并更新：

$$mask'=mask\mid 2^i.$$

所有边的代价都是一步，所以使用 BFS。第一次到达 (end, full_mask) 时，当前层数就是最短轨迹长度。

第四步：处理起点不能直接操作

BFS 的初始状态是 (center, 0) ，即使中心本身是非零目标，也不会在时间 $0$ 自动置位。由于 $n,m\ge3$，中心不是边界，无法用越界移动原地操作；必须先离开中心再走回来，落回中心时才会完成该目标。这个初始化恰好落实了题目的起点约束。

越界移动只会原地消耗一步。对于最短轨迹，它不会比在首次到达边界目标时直接完成操作更优，因此 BFS 只扩展网格内的四邻格。

## 题解代码

### Python 实现

```python
# 题目：Agent 执行轨迹压缩
# 算法：BFS / 队列
# 模式：ACM（stdin/stdout）
# 复杂度：时间 模拟原轨迹为 O(K)；BFS 最多访问 n m2^t 个状态，每个状态扩展四个方向，总复杂度为 O(K+n m\,2^t)；空间 访问标记和队列最多保存 O(n m\,2^t) 个状态

import sys
from collections import deque

input = sys.stdin.readline

n, m = map(int, input().split())
step_count = int(input())
start_row, start_col = n // 2, m // 2
row, col = start_row, start_col
delta = {}

directions = {
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
}

# 遍历 _
for _ in range(step_count):
    move, operation, param_text = input().split()
    param = int(param_text)
    dr, dc = directions[move]
    next_row, next_col = row + dr, col + dc
    # 条件判断
    if 0 <= next_row < n and 0 <= next_col < m:
        row, col = next_row, next_col

    # 条件判断
    if operation == "I":
        delta[(row, col)] = delta.get((row, col), 0) + param
    # 条件判断
    elif operation == "D":
        delta[(row, col)] = delta.get((row, col), 0) - param

end_id = row * m + col
targets = [cell for cell, value in delta.items() if value != 0]
target_index = {cell: index for index, cell in enumerate(targets)}
state_count = 1 << len(targets)
full_mask = state_count - 1

# 核心函数：shortest_path
def shortest_path():
    start_id = start_row * m + start_col
    visited = [bytearray(state_count) for _ in range(n * m)]
    visited[start_id][0] = 1
    queue = deque([(start_id, 0)])
    distance = 0

    # 循环处理
    while queue:
        # 遍历 _
        for _ in range(len(queue)):
            cell_id, mask = queue.popleft()
            # 条件判断
            if cell_id == end_id and mask == full_mask:
                # 返回结果
                return distance

            current_row, current_col = divmod(cell_id, m)
            for dr, dc in directions.values():
                next_row = current_row + dr
                next_col = current_col + dc
                # 条件判断
                if not (0 <= next_row < n and 0 <= next_col < m):
                    continue

                next_mask = mask
                bit_index = target_index.get((next_row, next_col))
                # 条件判断
                if bit_index is not None:
                    next_mask |= 1 << bit_index

                next_id = next_row * m + next_col
                # 条件判断
                if not visited[next_id][next_mask]:
                    visited[next_id][next_mask] = 1
                    queue.append((next_id, next_mask))
        distance += 1

    # 返回结果
    return -1


print(shortest_path())
```

## 复杂度分析

设最终非零目标格数量为 $t$，其中 $t\le12$。

时间复杂度 ：模拟原轨迹为 $O(K)$；BFS 最多访问 $n\times m\times2^t$ 个状态，每个状态扩展四个方向，总复杂度为 $O(K+n m\,2^t)$。最坏扩展次数约为 $225\times4096\times4\approx3.7\times10^6$。

空间复杂度 ：访问标记和队列最多保存 $O(n m\,2^t)$ 个状态。

### Java 实现

```java
// 题目：Agent 执行轨迹压缩
// 算法：BFS / 队列
// 模式：ACM（stdin/stdout）
// 复杂度：时间 模拟原轨迹为 O(K)；BFS 最多访问 n m2^t 个状态，每个状态扩展四个方向，总复杂度为 O(K+n m 2^t)；空间 访问标记和队列最多保存 O(n m 2^t) 个状态

import java.io.*;
import java.util.*;

public class Main {
    // 主函数：读取输入并输出答案
    public static void main(String[] args) throws IOException {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt(), m = sc.nextInt();
        int stepCount = sc.nextInt();
        int startRow = n / 2, startCol = m / 2;
        int row = startRow, col = startCol;
        Map<Integer,Integer> delta = new HashMap<>();
        Map<String,int[]> dirs = new HashMap<>();
        dirs.put("U", new int[]{-1, 0}); dirs.put("D", new int[]{1, 0}); dirs.put("L", new int[]{0, -1}); dirs.put("R", new int[]{0, 1});
        // 枚举位置 i
        for (int i = 0; i < stepCount; i++) {
            String move = sc.next(); String op = sc.next(); int param = sc.nextInt();
            int[] d = dirs.get(move);
            int nr = row + d[0], nc = col + d[1];
            // 条件判断
            if (nr >= 0 && nr < n && nc >= 0 && nc < m) { row = nr; col = nc; }
            // 条件判断
            if (op.equals("I")) { int key = row * m + col; delta.put(key, delta.getOrDefault(key, 0) + param); }
            else if (op.equals("D")) { int key = row * m + col; delta.put(key, delta.getOrDefault(key, 0) - param); }
        }
        int endId = row * m + col;
        List<Integer> targets = new ArrayList<>();
        // 循环处理
        for (Map.Entry<Integer,Integer> en : delta.entrySet()) if (en.getValue() != 0) targets.add(en.getKey());
        Map<Integer,Integer> targetIndex = new HashMap<>();
        // 枚举位置 i
        for (int i = 0; i < targets.size(); i++) targetIndex.put(targets.get(i), i);
        int stateCount = 1 << targets.size();
        int fullMask = stateCount - 1;
        int startId = startRow * m + startCol;
        boolean[][] visited = new boolean[n * m][stateCount];
        ArrayDeque<int[]> queue = new ArrayDeque<>();
        visited[startId][0] = true;
        queue.add(new int[]{startId, 0});
        int distance = 0; int answer = -1;
        int[][] dirList = {{-1,0},{1,0},{0,-1},{0,1}};
        // 循环处理
        while (!queue.isEmpty()) {
            int size = queue.size();
            // 循环处理
            for (int q = 0; q < size; q++) {
                int[] cur = queue.poll();
                int cellId = cur[0], mask = cur[1];
                // 条件判断
                if (cellId == endId && mask == fullMask) { answer = distance; System.out.println(answer); return; }
                int cr = cellId / m, cc = cellId % m;
                // 循环处理
                for (int[] d : dirList) {
                    int nr = cr + d[0], nc = cc + d[1];
                    // 条件判断
                    if (nr < 0 || nr >= n || nc < 0 || nc >= m) continue;
                    int nextMask = mask;
                    Integer bi = targetIndex.get(nr * m + nc);
                    // 条件判断
                    if (bi != null) nextMask |= 1 << bi;
                    int nid = nr * m + nc;
                    // 条件判断
                    if (!visited[nid][nextMask]) { visited[nid][nextMask] = true; queue.add(new int[]{nid, nextMask}); }
                }
            }
            distance++;
        }
        System.out.println(-1);
    }
}
```
