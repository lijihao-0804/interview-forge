# LeetCode Hot 100：Java 基础语法、常用类与 API 速查

> 目的：刷 Hot 100 时快速查“该用哪个类、方法叫什么、返回什么、空集合时怎样”。  
> 适用：Java 17+；示例已使用本机 JDK 25 编译验证，核心 API 均为长期稳定的 Java Collections Framework API。  
> 建议：刷题代码优先简洁和正确，但不要用容易整数溢出的比较器、含糊的栈/队列端点或未经确认的新 API。

## 目录

- [1. 常用 import 与 LeetCode 模板](#1-常用-import-与-leetcode-模板)
- [2. 基本类型、包装类型与溢出](#2-基本类型包装类型与溢出)
- [3. 数组](#3-数组)
- [4. String、char 与 StringBuilder](#4-stringchar-与-stringbuilder)
- [5. Java 集合总览](#5-java-集合总览)
- [6. List](#6-list)
- [7. HashMap、HashSet 与有序映射](#7-hashmaphashset-与有序映射)
- [8. Queue：offer、poll、peek 到底怎么选](#8-queueofferpollpeek-到底怎么选)
- [9. Deque：栈、队列与双端队列](#9-deque栈队列与双端队列)
- [10. PriorityQueue：堆](#10-priorityqueue堆)
- [11. Comparator 与排序](#11-comparator-与排序)
- [12. Arrays、Collections 与二分](#12-arrayscollections-与二分)
- [13. 常用数学、字符和位运算](#13-常用数学字符和位运算)
- [14. 链表与二叉树节点](#14-链表与二叉树节点)
- [15. DFS、BFS 与图](#15-dfsbfs-与图)
- [16. 并查集](#16-并查集)
- [17. 二分查找模板](#17-二分查找模板)
- [18. 双指针、滑动窗口与前缀和](#18-双指针滑动窗口与前缀和)
- [19. 回溯](#19-回溯)
- [20. 动态规划](#20-动态规划)
- [21. 单调栈、单调队列与堆模板](#21-单调栈单调队列与堆模板)
- [22. Java 刷题高频坑](#22-java-刷题高频坑)
- [23. Hot 100 题型与数据结构选择](#23-hot-100-题型与数据结构选择)
- [24. 一页 API 速记](#24-一页-api-速记)
- [25. 原有专题笔记与官方文档](#25-原有专题笔记与官方文档)

---

## 1. 常用 import 与 LeetCode 模板

### 1.1 省事写法

```java
import java.util.*;

class Solution {
    public int[] solve(int[] nums) {
        return nums;
    }
}
```

LeetCode 中 `java.util.*` 足够覆盖大多数集合、数组工具和比较器。正式项目更推荐显式 import，但刷题不必纠结。

### 1.2 常用类所在包

| 类/接口 | 包 | 用途 |
|---|---|---|
| `Arrays` | `java.util` | 数组排序、填充、比较、二分 |
| `Collections` | `java.util` | List 排序、反转、最值 |
| `ArrayList` | `java.util` | 动态数组 |
| `LinkedList` | `java.util` | 链表/Deque 实现，但刷题队列更推荐 ArrayDeque |
| `HashMap` / `HashSet` | `java.util` | 哈希映射/集合 |
| `TreeMap` / `TreeSet` | `java.util` | 有序映射/集合 |
| `Queue` / `Deque` | `java.util` | 队列/双端队列 |
| `ArrayDeque` | `java.util` | 推荐的栈和普通队列实现 |
| `PriorityQueue` | `java.util` | 小顶堆/大顶堆 |
| `Comparator` | `java.util` | 自定义排序 |
| `StringBuilder` | `java.lang` | 可变字符串，无需 import |
| `Math` / `Character` | `java.lang` | 数学/字符工具，无需 import |

### 1.3 main 验证模板

LeetCode 只提交 `Solution`，本地验证可加：

```java
import java.util.*;

public class Main {
    public static void main(String[] args) {
        int[] nums = {3, 1, 2};
        Arrays.sort(nums);
        System.out.println(Arrays.toString(nums));
    }
}
```

输出：

```text
[1, 2, 3]
```

---

## 2. 基本类型、包装类型与溢出

### 2.1 基本类型

| 类型 | 常用范围/用途 |
|---|---|
| `int` | 一般下标、计数、题目数值 |
| `long` | 求和、乘法、中间结果可能超过约 21 亿 |
| `double` | 浮点计算 |
| `char` | UTF-16 code unit，英文字符题很常用 |
| `boolean` | 状态 |

Hot 100 最常见错误之一是中间计算溢出：

```java
int a = 1_500_000_000;
int b = 2;

long wrong = a * b;          // 先按 int 计算，已经溢出
long right = (long) a * b;   // 先转 long

System.out.println(wrong);
System.out.println(right);
```

输出：

```text
-1294967296
3000000000
```

以下场景优先考虑 `long`：

- 数组所有元素求和；
- 两数/三数乘积；
- 前缀和；
- 二分答案中的距离、容量、天数；
- 比较器里做减法；
- `mid` 参与其他加法或乘法。

### 2.2 包装类型

泛型不能使用基本类型：

```java
List<Integer> list = new ArrayList<>();
Map<Character, Integer> count = new HashMap<>();
```

自动装箱/拆箱：

```java
Integer boxed = 10;  // int -> Integer
int value = boxed;   // Integer -> int
```

注意 `null` 拆箱会抛出 `NullPointerException`：

```java
Integer value = null;
// int x = value; // NPE
```

### 2.3 Integer 比较

包装类型比较数值使用 `equals()`，不要依赖 `==` 的缓存行为：

```java
Integer a = 1000;
Integer b = 1000;
System.out.println(a.equals(b));
System.out.println(a == b);
```

典型输出：

```text
true
false
```

刷题时拆箱为 `int` 后比较最清楚。

---

## 3. 数组

### 3.1 创建和初始化

```java
int[] nums = new int[5];            // 默认全 0
int[] values = {3, 1, 4};
int[][] grid = new int[3][4];       // 3 行 4 列
boolean[] visited = new boolean[10];
```

长度：

```java
System.out.println(values.length);
System.out.println(grid.length);       // 行数
System.out.println(grid[0].length);    // 列数
```

输出：

```text
3
3
4
```

数组是 `.length` 字段；字符串是 `.length()` 方法；集合是 `.size()` 方法。

### 3.2 遍历

需要下标：

```java
for (int i = 0; i < nums.length; i++) {
    nums[i] += 1;
}
```

只读元素：

```java
for (int num : nums) {
    System.out.println(num);
}
```

增强 for 中修改局部变量不会修改基本类型数组元素：

```java
int[] nums = {1, 2};
for (int num : nums) {
    num *= 10;
}
System.out.println(Arrays.toString(nums));
```

输出：

```text
[1, 2]
```

### 3.3 Arrays 常用方法

```java
int[] nums = {4, 2, 3, 1};

Arrays.sort(nums);
System.out.println(Arrays.toString(nums));

Arrays.fill(nums, 7);
System.out.println(Arrays.toString(nums));

int[] copy = Arrays.copyOf(nums, nums.length);
System.out.println(Arrays.equals(nums, copy));
```

输出：

```text
[1, 2, 3, 4]
[7, 7, 7, 7]
true
```

区间方法通常是左闭右开 `[from, to)`：

```java
int[] nums = {5, 4, 3, 2, 1};
Arrays.sort(nums, 1, 4);
System.out.println(Arrays.toString(nums));
```

输出：

```text
[5, 2, 3, 4, 1]
```

### 3.4 二维数组填充

```java
int[][] dist = new int[3][4];
for (int[] row : dist) {
    Arrays.fill(row, -1);
}
```

`Arrays.fill(dist, ...)` 只能给每一行引用赋同一个值，不适合直接填二维基本数据。

### 3.5 数组转 List 的坑

基本类型数组：

```java
int[] nums = {1, 2, 3};
List<int[]> wrong = Arrays.asList(nums); // 只有 1 个元素：整个 int[]
System.out.println(wrong.size());
```

输出：

```text
1
```

需要 `List<Integer>`：

```java
List<Integer> list = Arrays.stream(nums).boxed().toList();
System.out.println(list);
```

输出：

```text
[1, 2, 3]
```

`Stream.toList()` 返回的 List 不保证可修改。需要修改：

```java
List<Integer> mutable = new ArrayList<>(
    Arrays.stream(nums).boxed().toList()
);
```

---

## 4. String、char 与 StringBuilder

### 4.1 String 常用方法

```java
String s = "abcabc";

System.out.println(s.length());
System.out.println(s.charAt(2));
System.out.println(s.substring(1, 4));
System.out.println(s.indexOf("bc"));
System.out.println(s.lastIndexOf("bc"));
System.out.println(s.startsWith("ab"));
System.out.println(s.contains("ca"));
```

输出：

```text
6
c
bca
1
4
true
true
```

`substring(begin, end)` 也是左闭右开。

### 4.2 字符与数字转换

```java
char c = '7';
int digit = c - '0';
char back = (char) ('0' + digit);

System.out.println(digit);
System.out.println(back);
```

输出：

```text
7
7
```

安全判断：

```java
Character.isDigit(c);
Character.isLetter(c);
Character.toLowerCase(c);
```

英文小写字母频次数组：

```java
int[] count = new int[26];
String s = "banana";
for (char c : s.toCharArray()) {
    count[c - 'a']++;
}
System.out.println(count['a' - 'a']);
```

输出：

```text
3
```

只有确定输入是 `a-z` 时才能直接 `c - 'a'`。

### 4.3 String 比较

内容比较：

```java
String a = new String("abc");
String b = new String("abc");
System.out.println(a.equals(b));
System.out.println(a == b);
```

输出：

```text
true
false
```

字典序：

```java
System.out.println("abc".compareTo("abd") < 0);
```

输出：

```text
true
```

### 4.4 StringBuilder

```java
StringBuilder sb = new StringBuilder();
sb.append("ab").append(123);
sb.insert(2, "-");
sb.setCharAt(0, 'A');

System.out.println(sb);
System.out.println(sb.reverse());
System.out.println(sb.deleteCharAt(0));
```

输出：

```text
Ab-123
321-bA
21-bA
```

常用方法：

| 方法 | 作用 |
|---|---|
| `append(x)` | 尾部添加 |
| `insert(index, x)` | 指定位置插入 |
| `delete(start, end)` | 删除左闭右开区间 |
| `deleteCharAt(index)` | 删除一个 char |
| `setCharAt(index, c)` | 修改字符 |
| `charAt(index)` | 读取字符 |
| `reverse()` | 原地反转并返回自身 |
| `length()` | 当前长度 |
| `setLength(n)` | 修改长度，回溯时可截断 |
| `toString()` | 转 String |

回溯中恢复长度：

```java
int oldLength = sb.length();
sb.append("abc");
// dfs(...)
sb.setLength(oldLength);
```

### 4.5 split 与正则表达式

`String.split()` 参数是正则：

```java
String s = "a.b.c";
System.out.println(Arrays.toString(s.split("\\.")));
```

输出：

```text
[a, b, c]
```

点号在正则中有特殊含义，必须转义。简单按空白分隔：`text.trim().split("\\s+")`。

---

## 5. Java 集合总览

```text
Collection
├─ List：ArrayList、LinkedList
├─ Set：HashSet、LinkedHashSet、TreeSet
└─ Queue
   ├─ Deque：ArrayDeque、LinkedList
   └─ PriorityQueue

Map（不继承 Collection）：HashMap、LinkedHashMap、TreeMap
```

| 需求 | 推荐 |
|---|---|
| 动态数组 | `ArrayList` |
| 计数、查找、去重 | `HashMap` / `HashSet` |
| 栈 | `Deque<E> stack = new ArrayDeque<>()` |
| 普通队列/BFS | `Queue<E> queue = new ArrayDeque<>()` |
| 双端队列 | `Deque<E> deque = new ArrayDeque<>()` |
| 堆/Top K | `PriorityQueue` |
| 自动按键排序 | `TreeMap` / `TreeSet` |

`ArrayDeque` 不允许 `null`。`poll()`/`peek()` 返回 `null` 时可明确表示空。

---

## 6. List

### 6.1 ArrayList 常用方法

```java
List<Integer> list = new ArrayList<>();
list.add(10);
list.add(0, 5);
list.set(1, 20);

System.out.println(list.get(0));
System.out.println(list.remove(1));
System.out.println(list);
```

输出：

```text
5
20
[5]
```

### 6.2 `remove(int)` 与 `remove(Object)`

```java
List<Integer> list = new ArrayList<>(List.of(10, 20, 30));
list.remove(1);                   // 删除下标 1，即 20
list.remove(Integer.valueOf(30)); // 删除值 30
System.out.println(list);
```

输出：

```text
[10]
```

### 6.3 subList 是视图

```java
List<Integer> list = new ArrayList<>(List.of(1, 2, 3, 4));
List<Integer> view = list.subList(1, 3);
view.set(0, 20);
System.out.println(list);
```

输出：

```text
[1, 20, 3, 4]
```

需要独立副本：`new ArrayList<>(list.subList(1, 3))`。

---

## 7. HashMap、HashSet 与有序映射

### 7.1 HashMap 高频方法

```java
Map<String, Integer> count = new HashMap<>();
count.put("a", 1);
count.put("b", 2);

System.out.println(count.get("a"));
System.out.println(count.getOrDefault("c", 0));
System.out.println(count.containsKey("b"));
System.out.println(count.remove("b"));
```

输出：

```text
1
0
true
2
```

### 7.2 计数

```java
String s = "banana";
Map<Character, Integer> count = new HashMap<>();
for (char c : s.toCharArray()) {
    count.put(c, count.getOrDefault(c, 0) + 1);
    // 或：count.merge(c, 1, Integer::sum);
}
```

### 7.3 分组：computeIfAbsent

```java
Map<Integer, List<Integer>> graph = new HashMap<>();
graph.computeIfAbsent(1, key -> new ArrayList<>()).add(2);
graph.computeIfAbsent(1, key -> new ArrayList<>()).add(3);
System.out.println(graph);
```

输出：

```text
{1=[2, 3]}
```

不要写 `getOrDefault(key, new ArrayList<>()).add(x)`，键不存在时新 List 没放回 Map。

### 7.4 遍历 Map

```java
for (Map.Entry<String, Integer> entry : map.entrySet()) {
    String key = entry.getKey();
    int value = entry.getValue();
}
```

### 7.5 HashSet

```java
Set<Integer> seen = new HashSet<>();
System.out.println(seen.add(5));
System.out.println(seen.add(5));
System.out.println(seen.contains(5));
```

输出：

```text
true
false
true
```

`add()` 返回是否真的新增，可直接判重：`if (!seen.add(value))`。

### 7.6 TreeMap / TreeSet

```java
TreeMap<Integer, String> map = new TreeMap<>();
map.put(10, "a");
map.put(30, "b");

System.out.println(map.floorKey(25));
System.out.println(map.ceilingKey(25));
```

输出：

```text
10
30
```

| 方法 | 含义 |
|---|---|
| `lowerKey(k)` | 严格小于 k 的最大键 |
| `floorKey(k)` | 小于等于 k 的最大键 |
| `higherKey(k)` | 严格大于 k 的最小键 |
| `ceilingKey(k)` | 大于等于 k 的最小键 |

---

## 8. Queue：offer、poll、peek 到底怎么选

### 8.1 六个方法成组记忆

| 操作 | 抛异常版本 | 返回特殊值版本 | 推荐刷题 |
|---|---|---|---|
| 入队 | `add(e)` | `offer(e)` 返回 boolean | `offer` |
| 出队 | `remove()` | `poll()` 空时返回 null | `poll` |
| 看队头 | `element()` | `peek()` 空时返回 null | `peek` |

口诀：

```text
offer：尝试放进去
poll：取出并删除
peek：偷看但不删除
```

```java
Queue<Integer> queue = new ArrayDeque<>();
queue.offer(10);
queue.offer(20);

System.out.println(queue.peek());
System.out.println(queue.poll());
System.out.println(queue.poll());
System.out.println(queue.poll());
```

输出：

```text
10
10
20
null
```

### 8.2 remove 的重载

`Queue.remove()`：删除队头，空时抛异常。  
`Collection.remove(Object)`：删除指定元素，返回 boolean。

### 8.3 BFS 分层

```java
Queue<TreeNode> queue = new ArrayDeque<>();
queue.offer(root);

while (!queue.isEmpty()) {
    int size = queue.size();
    for (int i = 0; i < size; i++) {
        TreeNode node = queue.poll();
        if (node.left != null) queue.offer(node.left);
        if (node.right != null) queue.offer(node.right);
    }
}
```

进入本层循环前固定 `size`，因为处理中会继续入队。

---

## 9. Deque：栈、队列与双端队列

### 9.1 栈推荐 ArrayDeque

`java.util.Stack` 是旧的同步 `Vector` 子类。刷题推荐：

```java
Deque<Integer> stack = new ArrayDeque<>();
stack.push(1);   // 等价 addFirst
stack.push(2);

System.out.println(stack.peek());
System.out.println(stack.pop()); // 等价 removeFirst，空时抛异常
```

输出：

```text
2
2
```

若希望空时返回 null：`offerFirst / pollFirst / peekFirst`。

### 9.2 普通队列

```java
Deque<Integer> queue = new ArrayDeque<>();
queue.offerLast(1);
queue.offerLast(2);
System.out.println(queue.pollFirst());
```

输出：

```text
1
```

### 9.3 Deque 成对方法

| 端点 | 插入异常版 | 插入特殊值版 | 删除异常版 | 删除特殊值版 | 查看异常版 | 查看特殊值版 |
|---|---|---|---|---|---|---|
| First | `addFirst` | `offerFirst` | `removeFirst` | `pollFirst` | `getFirst` | `peekFirst` |
| Last | `addLast` | `offerLast` | `removeLast` | `pollLast` | `getLast` | `peekLast` |

### 9.4 ArrayDeque 不允许 null

因此 `poll/peek` 返回 null 可以可靠表示为空。树 BFS 只在节点非 null 时入队。

---

## 10. PriorityQueue：堆

### 10.1 默认小顶堆

```java
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
minHeap.offer(3);
minHeap.offer(1);
minHeap.offer(2);

System.out.println(minHeap.peek());
System.out.println(minHeap.poll());
```

输出：

```text
1
1
```

### 10.2 大顶堆

```java
PriorityQueue<Integer> maxHeap =
    new PriorityQueue<>(Comparator.reverseOrder());
```

### 10.3 数组比较器

```java
PriorityQueue<int[]> heap = new PriorityQueue<>(
    Comparator.comparingInt(a -> a[0])
);
heap.offer(new int[]{5, 100});
heap.offer(new int[]{2, 200});
System.out.println(Arrays.toString(heap.poll()));
```

输出：

```text
[2, 200]
```

不要用 `(a, b) -> a - b`，可能整数溢出。使用 `Integer.compare(a, b)`、`Long.compare(a, b)` 或 `Comparator.comparingInt`。

### 10.4 复杂度

| 操作 | 复杂度 |
|---|---|
| `offer/add` | $O(\log n)$ |
| `poll/remove()` 队头 | $O(\log n)$ |
| `peek` | $O(1)$ |
| `contains(x)` | $O(n)$ |
| `remove(x)` 指定元素 | $O(n)$ |

遍历 PriorityQueue 不保证整体有序。要按序输出就不断 `poll()`。

### 10.5 Top K

找最大的 K 个：维护大小为 K 的小顶堆。

```java
PriorityQueue<Integer> heap = new PriorityQueue<>();
for (int num : nums) {
    heap.offer(num);
    if (heap.size() > k) heap.poll();
}
// heap.peek() 是第 k 大
```

---

## 11. Comparator 与排序

### 11.1 基本类型数组

```java
int[] nums = {3, 1, 2};
Arrays.sort(nums);
```

基本类型数组不能传 Comparator。降序可排序后反转，或使用 `Integer[]`。

### 11.2 二维数组

```java
int[][] intervals = {{1, 3}, {2, 2}, {1, 2}};
Arrays.sort(intervals, (a, b) -> {
    int byStart = Integer.compare(a[0], b[0]);
    if (byStart != 0) return byStart;
    return Integer.compare(a[1], b[1]);
});
System.out.println(Arrays.deepToString(intervals));
```

输出：

```text
[[1, 2], [1, 3], [2, 2]]
```

链式写法：

```java
Arrays.sort(intervals,
    Comparator.comparingInt((int[] a) -> a[0])
              .thenComparingInt(a -> a[1]));
```

### 11.3 List 排序

```java
list.sort(Comparator.naturalOrder());
list.sort(Comparator.reverseOrder());
Collections.sort(list);
```

---

## 12. Arrays、Collections 与二分

### 12.1 高频方法

```java
Arrays.sort(nums);
Arrays.fill(nums, -1);
Arrays.equals(a, b);
Arrays.toString(nums);
Arrays.deepToString(matrix);
Arrays.copyOf(nums, newLength);
Arrays.copyOfRange(nums, from, to); // 左闭右开
Arrays.binarySearch(nums, target);

Collections.sort(list);
Collections.reverse(list);
Collections.swap(list, i, j);
Collections.min(list);
Collections.max(list);
```

### 12.2 binarySearch 返回值

数组必须先按相同规则排序。

```java
int[] nums = {1, 3, 5, 7};
System.out.println(Arrays.binarySearch(nums, 5));
System.out.println(Arrays.binarySearch(nums, 4));
```

输出：

```text
2
-3
```

未找到时返回 `-(insertionPoint) - 1`。还原插入点：

```java
int result = Arrays.binarySearch(nums, target);
int insertionPoint = result >= 0 ? result : -result - 1;
```

---

## 13. 常用数学、字符和位运算

### 13.1 Math

```java
Math.max(a, b);
Math.min(a, b);
Math.abs(x);
Math.sqrt(x);       // double
Math.pow(a, b);     // double
Math.ceil(x);
Math.floor(x);
```

`Math.abs(Integer.MIN_VALUE)` 仍会溢出并返回负数，因为其正值无法用 int 表示。可能触边界时先转 long。

### 13.2 安全计算 mid

```java
int mid = left + (right - left) / 2;       // 偏左
int midRight = left + (right - left + 1) / 2; // 偏右
```

`(left + right) / 2` 可能溢出。

### 13.3 char 判断

```java
Character.isDigit(c);
Character.isLetter(c);
Character.isLetterOrDigit(c);
Character.toLowerCase(c);
Character.toUpperCase(c);
```

### 13.4 位运算

| 表达式 | 含义 |
|---|---|
| `x & 1` | 判断奇偶 |
| `x & (x - 1)` | 删除最低位的 1 |
| `x & -x` | 取最低位的 1（lowbit） |
| `1 << k` | 第 k 位对应值 |
| `(mask >> k) & 1` | 读取第 k 位 |
| `mask | (1 << k)` | 把第 k 位置 1 |
| `mask & ~(1 << k)` | 把第 k 位置 0 |
| `a ^ a` | 0 |
| `a ^ 0` | a |

Java 的 `>>` 保留符号位，`>>>` 高位补 0。

```java
int x = 0b101100;
System.out.println(Integer.bitCount(x));
System.out.println(Integer.numberOfLeadingZeros(x));
```

输出：

```text
3
26
```

### 13.5 整除与取模

Java 整数除法向 0 截断：

```java
System.out.println(-5 / 2);
System.out.println(-5 % 2);
System.out.println(Math.floorDiv(-5, 2));
System.out.println(Math.floorMod(-5, 2));
```

输出：

```text
-2
-1
-3
1
```

---

## 14. 链表与二叉树节点

LeetCode 通常预定义：

```java
class ListNode {
    int val;
    ListNode next;
    ListNode() {}
    ListNode(int val) { this.val = val; }
    ListNode(int val, ListNode next) {
        this.val = val;
        this.next = next;
    }
}

class TreeNode {
    int val;
    TreeNode left;
    TreeNode right;
    TreeNode() {}
    TreeNode(int val) { this.val = val; }
    TreeNode(int val, TreeNode left, TreeNode right) {
        this.val = val;
        this.left = left;
        this.right = right;
    }
}
```

### 14.1 虚拟头节点

统一处理删除头节点、合并链表：

```java
ListNode dummy = new ListNode(0, head);
ListNode prev = dummy;
// 操作 prev.next
return dummy.next;
```

### 14.2 反转链表

```java
ListNode reverse(ListNode head) {
    ListNode prev = null;
    ListNode curr = head;

    while (curr != null) {
        ListNode next = curr.next;
        curr.next = prev;
        prev = curr;
        curr = next;
    }
    return prev;
}
```

必须先保存 `next`，否则断链后找不到后续节点。

### 14.3 快慢指针

```java
ListNode slow = head;
ListNode fast = head;

while (fast != null && fast.next != null) {
    slow = slow.next;
    fast = fast.next.next;
}
```

可找中点、判断环。循环条件顺序避免先访问 `fast.next` 导致 NPE。

---

## 15. DFS、BFS 与图

### 15.1 DFS 递归

```java
void dfs(TreeNode node) {
    if (node == null) return;

    // 前序位置
    dfs(node.left);
    // 中序位置
    dfs(node.right);
    // 后序位置
}
```

深度非常大时递归可能 `StackOverflowError`，可改显式栈。

### 15.2 迭代 DFS

```java
Deque<TreeNode> stack = new ArrayDeque<>();
stack.push(root);

while (!stack.isEmpty()) {
    TreeNode node = stack.pop();
    // 处理 node

    // 先压右再压左，弹出时先访问左
    if (node.right != null) stack.push(node.right);
    if (node.left != null) stack.push(node.left);
}
```

### 15.3 邻接表

节点编号 0～n-1：

```java
List<Integer>[] graph = new ArrayList[n];
for (int i = 0; i < n; i++) {
    graph[i] = new ArrayList<>();
}

for (int[] edge : edges) {
    int u = edge[0], v = edge[1];
    graph[u].add(v);
    graph[v].add(u); // 无向图才加反向边
}
```

会有泛型数组警告，但刷题常用。也可用 `List<List<Integer>>`。

### 15.4 图 BFS

```java
Queue<Integer> queue = new ArrayDeque<>();
boolean[] visited = new boolean[n];

queue.offer(start);
visited[start] = true; // 入队时标记，防止重复入队

while (!queue.isEmpty()) {
    int node = queue.poll();
    for (int next : graph[node]) {
        if (!visited[next]) {
            visited[next] = true;
            queue.offer(next);
        }
    }
}
```

### 15.5 拓扑排序

```java
int[] indegree = new int[n];
Queue<Integer> queue = new ArrayDeque<>();

for (int i = 0; i < n; i++) {
    if (indegree[i] == 0) queue.offer(i);
}

int visitedCount = 0;
while (!queue.isEmpty()) {
    int node = queue.poll();
    visitedCount++;
    for (int next : graph[node]) {
        if (--indegree[next] == 0) {
            queue.offer(next);
        }
    }
}

boolean hasCycle = visitedCount != n;
```

---

## 16. 并查集

用于动态连通性、连通分量、冗余边。

```java
class UnionFind {
    private final int[] parent;
    private final int[] size;
    private int count;

    UnionFind(int n) {
        parent = new int[n];
        size = new int[n];
        count = n;
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }
    }

    int find(int x) {
        if (parent[x] != x) {
            parent[x] = find(parent[x]); // 路径压缩
        }
        return parent[x];
    }

    boolean union(int a, int b) {
        int rootA = find(a);
        int rootB = find(b);
        if (rootA == rootB) return false;

        if (size[rootA] < size[rootB]) {
            int temp = rootA;
            rootA = rootB;
            rootB = temp;
        }
        parent[rootB] = rootA;
        size[rootA] += size[rootB];
        count--;
        return true;
    }

    boolean connected(int a, int b) {
        return find(a) == find(b);
    }

    int count() {
        return count;
    }
}
```

路径压缩 + 按大小合并后，均摊复杂度接近 $O(1)$，严格说是 $O(\alpha(n))$。

---

## 17. 二分查找模板

### 17.1 查找确切值

```java
int binarySearch(int[] nums, int target) {
    int left = 0, right = nums.length - 1;

    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (nums[mid] == target) return mid;
        if (nums[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}
```

### 17.2 lowerBound：第一个大于等于 target

使用左闭右开 `[left, right)`：

```java
int lowerBound(int[] nums, int target) {
    int left = 0, right = nums.length;

    while (left < right) {
        int mid = left + (right - left) / 2;
        if (nums[mid] < target) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    return left;
}
```

返回值可以等于 `nums.length`，表示所有元素都小于 target。

### 17.3 upperBound：第一个严格大于 target

```java
int upperBound(int[] nums, int target) {
    int left = 0, right = nums.length;
    while (left < right) {
        int mid = left + (right - left) / 2;
        if (nums[mid] <= target) left = mid + 1;
        else right = mid;
    }
    return left;
}
```

### 17.4 二分答案

当答案具有单调性：

```java
long left = minAnswer;
long right = maxAnswer;

while (left < right) {
    long mid = left + (right - left) / 2;
    if (check(mid)) {
        right = mid;
    } else {
        left = mid + 1;
    }
}
return left;
```

先明确 `check(x)` 是“x 是否已经可行”，再决定移动方向。

---

## 18. 双指针、滑动窗口与前缀和

### 18.1 相向双指针

```java
int left = 0, right = nums.length - 1;
while (left < right) {
    int sum = nums[left] + nums[right];
    if (sum == target) break;
    if (sum < target) left++;
    else right--;
}
```

通常要求数组已排序或有明确单调关系。

### 18.2 滑动窗口

```java
int left = 0;
for (int right = 0; right < s.length(); right++) {
    char in = s.charAt(right);
    // 把 in 加入窗口

    while (窗口不合法) {
        char out = s.charAt(left++);
        // 把 out 移出窗口
    }

    // 更新合法窗口答案
}
```

最关键的是明确：

- 窗口 `[left, right]` 表示什么；
- 何时扩张；
- 何时以及为什么收缩；
- 更新答案是在收缩前还是收缩后。

### 18.3 前缀和

```java
long[] prefix = new long[nums.length + 1];
for (int i = 0; i < nums.length; i++) {
    prefix[i + 1] = prefix[i] + nums[i];
}

// nums[left..right]，两端都包含
long rangeSum = prefix[right + 1] - prefix[left];
```

长度为 `n + 1` 可让空前缀为 0，减少边界判断。

---

## 19. 回溯

### 19.1 通用模板

```java
List<List<Integer>> result = new ArrayList<>();
List<Integer> path = new ArrayList<>();

void backtrack(int start, int[] nums) {
    result.add(new ArrayList<>(path)); // 必须复制快照

    for (int i = start; i < nums.length; i++) {
        path.add(nums[i]);
        backtrack(i + 1, nums);
        path.remove(path.size() - 1);
    }
}
```

若写 `result.add(path)`，所有结果引用同一个可变 List，最终内容错误。

### 19.2 去重

排序后，同一树层跳过相同选择：

```java
Arrays.sort(nums);
for (int i = start; i < nums.length; i++) {
    if (i > start && nums[i] == nums[i - 1]) continue;
    // 选择 nums[i]
}
```

`i > start` 表示同一层去重，不是禁止下一层再次选择相同值。

### 19.3 排列模板

```java
boolean[] used = new boolean[nums.length];

void permute(int[] nums) {
    if (path.size() == nums.length) {
        result.add(new ArrayList<>(path));
        return;
    }

    for (int i = 0; i < nums.length; i++) {
        if (used[i]) continue;
        used[i] = true;
        path.add(nums[i]);
        permute(nums);
        path.remove(path.size() - 1);
        used[i] = false;
    }
}
```

---

## 20. 动态规划

### 20.1 五个问题

写 DP 前回答：

1. `dp[i]` 或 `dp[i][j]` 表示什么；
2. 状态怎样转移；
3. 初始值是什么；
4. 遍历顺序为什么正确；
5. 最终答案在哪个状态。

### 20.2 一维 DP

```java
int[] dp = new int[n + 1];
dp[0] = 0;
dp[1] = 1;

for (int i = 2; i <= n; i++) {
    dp[i] = dp[i - 1] + dp[i - 2];
}
```

### 20.3 无穷大初始化

```java
int INF = Integer.MAX_VALUE / 4;
int[] dp = new int[n + 1];
Arrays.fill(dp, INF);
dp[0] = 0;
```

不要直接用 `Integer.MAX_VALUE` 后再 `+ 1`，会溢出为负数。

### 20.4 0-1 背包遍历方向

每个物品只能使用一次，容量倒序：

```java
for (int weight : weights) {
    for (int capacity = target; capacity >= weight; capacity--) {
        dp[capacity] = Math.max(
            dp[capacity],
            dp[capacity - weight] + value
        );
    }
}
```

完全背包允许重复使用，容量通常正序。

---

## 21. 单调栈、单调队列与堆模板

### 21.1 下一个更大元素：单调栈

栈中保存下标：

```java
int[] answer = new int[nums.length];
Arrays.fill(answer, -1);
Deque<Integer> stack = new ArrayDeque<>();

for (int i = 0; i < nums.length; i++) {
    while (!stack.isEmpty() && nums[stack.peek()] < nums[i]) {
        answer[stack.pop()] = nums[i];
    }
    stack.push(i);
}
```

保存下标可同时获得值和距离。

### 21.2 滑动窗口最大值：单调队列

Deque 保存下标，值从队头到队尾单调递减：

```java
Deque<Integer> deque = new ArrayDeque<>();

for (int right = 0; right < nums.length; right++) {
    while (!deque.isEmpty() && deque.peekFirst() <= right - k) {
        deque.pollFirst();
    }

    while (!deque.isEmpty() && nums[deque.peekLast()] <= nums[right]) {
        deque.pollLast();
    }
    deque.offerLast(right);

    if (right >= k - 1) {
        int maximum = nums[deque.peekFirst()];
    }
}
```

队头永远是当前窗口最大值下标。

### 21.3 双堆中位数

```java
PriorityQueue<Integer> left =
    new PriorityQueue<>(Comparator.reverseOrder()); // 较小一半，大顶堆
PriorityQueue<Integer> right =
    new PriorityQueue<>();                          // 较大一半，小顶堆
```

维护：`left.size() == right.size()` 或 `left` 多 1；并保证 `left.peek() <= right.peek()`。

---

## 22. Java 刷题高频坑

### 22.1 修改集合时并发修改异常

```java
for (Integer value : list) {
    if (value < 0) {
        list.remove(value); // 可能 ConcurrentModificationException
    }
}
```

使用 Iterator：

```java
Iterator<Integer> iterator = list.iterator();
while (iterator.hasNext()) {
    if (iterator.next() < 0) iterator.remove();
}
```

或 `list.removeIf(value -> value < 0)`。

### 22.2 HashMap key 必须稳定

数组默认按引用判断 `equals/hashCode`，不能直接用 `int[]` 当“内容键”。可转 String、List，或自定义不可变 Key 并实现 `equals/hashCode`。

### 22.3 Arrays.asList 固定大小

```java
List<Integer> list = Arrays.asList(1, 2, 3);
// list.add(4); // UnsupportedOperationException
```

需要修改：`new ArrayList<>(Arrays.asList(...))`。

`List.of(...)` 也不可修改，并且不允许 null。

### 22.4 ArrayDeque 不允许 null

树层序遍历不要把 null 子节点入队。需要标记层时使用 size 分层或其他非 null 哨兵。

### 22.5 equals/hashCode

HashMap/HashSet 根据 `hashCode` 找桶，再用 `equals` 判断相等。自定义键若重写一个，通常必须同时重写另一个。

### 22.6 char 不是完整 Unicode 字符

`char` 是 UTF-16 code unit。Hot 100 大多限制 ASCII/英文字母，直接 char 足够；若处理 Emoji 等补充字符，需要 `codePoints()`。

### 22.7 递归栈

链表、偏斜树或大网格深度可能很大，Java 递归可能栈溢出。题目约束大时考虑迭代。

### 22.8 Stream 不一定更适合刷题

Stream 写法简洁，但可能产生装箱、难调试，并掩盖复杂度。核心算法循环通常使用普通 for 更直接。

### 22.9 HashMap/HashSet 顺序不保证

输出或算法依赖顺序时使用排序、`LinkedHashMap` 或 `TreeMap`，不要依赖一次运行观察到的 HashMap 顺序。

### 22.10 Comparator 契约

比较器必须满足反对称、传递和相等一致性。不要随机返回、不要用可能溢出的减法。

---

## 23. Hot 100 题型与数据结构选择

| 题型信号 | 常用结构/方法 |
|---|---|
| 两数之和、频次、分组 | HashMap |
| 去重、是否出现 | HashSet |
| 有序数组找配对 | 双指针 |
| 最长/最短连续子串 | 滑动窗口 |
| 区间和、和为 K | 前缀和 + HashMap |
| 合并区间 | 排序 |
| 下一个更大、柱状图 | 单调栈 |
| 窗口最大值 | 单调队列 |
| Top K、第 K 大 | PriorityQueue / 快速选择 |
| 树层序、最短步数 | BFS + Queue |
| 树路径、连通块 | DFS/回溯 |
| 课程依赖 | 拓扑排序 |
| 动态连通性 | 并查集 |
| 有序查找/答案单调 | 二分 |
| 枚举选择方案 | 回溯 |
| 重叠子问题 + 最优子结构 | 动态规划 |

---

## 24. 一页 API 速记

```java
// List
list.add(x); list.get(i); list.set(i, x);
list.remove(i); list.remove(Integer.valueOf(x));
list.size(); list.isEmpty();

// Map
map.put(k, v); map.get(k); map.getOrDefault(k, 0);
map.containsKey(k); map.remove(k);
map.merge(k, 1, Integer::sum);
map.computeIfAbsent(k, key -> new ArrayList<>()).add(v);

// Set
set.add(x); set.contains(x); set.remove(x);

// Queue：记这三个
queue.offer(x); queue.poll(); queue.peek();

// Stack with Deque
stack.push(x); stack.pop(); stack.peek();
// 空时想返回 null：offerFirst / pollFirst / peekFirst

// Deque
deque.offerFirst(x); deque.offerLast(x);
deque.pollFirst(); deque.pollLast();
deque.peekFirst(); deque.peekLast();

// Heap
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
PriorityQueue<Integer> maxHeap =
    new PriorityQueue<>(Comparator.reverseOrder());
heap.offer(x); heap.poll(); heap.peek();

// Array / String / StringBuilder
nums.length; s.length(); list.size();
Arrays.sort(nums); Arrays.fill(nums, value);
s.charAt(i); s.substring(left, right); s.toCharArray();
sb.append(x); sb.deleteCharAt(i); sb.setLength(oldLength);

// Safe compare and mid
Integer.compare(a, b);
Long.compare(a, b);
int mid = left + (right - left) / 2;
```

### 最重要的记忆

```text
Queue：offer / poll / peek
Stack：push / pop / peek
Heap：offer / poll / peek

poll/pop 会删除；peek 不删除。
poll 空时 null；pop 空时抛异常。
PriorityQueue 默认小顶堆。
比较器不要写 a - b。
```

---

## 25. 原有专题笔记与官方文档

### 本地专题笔记

- [集合](00-%E9%9B%86%E5%90%88.md)
- [数组](00-%E6%95%B0%E7%BB%84.md)
- [字符串](00-%E5%AD%97%E7%AC%A6%E4%B8%B2.md)
- [排序](00-%E6%8E%92%E5%BA%8F%E6%96%B9%E5%BC%8F.md)
- [哈希表](01-%E5%93%88%E5%B8%8C%E8%A1%A8.md)
- [双指针](02-%E5%8F%8C%E6%8C%87%E9%92%88.md)
- [滑动窗口](03-%E6%BB%91%E5%8A%A8%E7%AA%97%E5%8F%A3.md)
- [链表](07-%E9%93%BE%E8%A1%A8.md)
- [二叉树](08-%E4%BA%8C%E5%8F%89%E6%A0%91.md)
- [图论](09-%E5%9B%BE%E8%AE%BA.md)
- [回溯](10-%E5%9B%9E%E6%BA%AF.md)
- [二分查找](11-%E4%BA%8C%E5%88%86%E6%9F%A5%E6%89%BE.md)
- [栈](12-%E6%A0%88.md)
- [堆](13-%E5%A0%86.md)
- [动态规划](15-%E5%8A%A8%E6%80%81%E8%A7%84%E5%88%92.md)

### Oracle JDK 25 官方文档

- [Collections Framework Overview](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/doc-files/coll-overview.html)
- [Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html)
- [Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)
- [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)
- [PriorityQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PriorityQueue.html)
- [HashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html)
- [HashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html)
- [Arrays](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html)
- [Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html)
- [String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [StringBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html)

---

## 最后的判断

Hot 100 的 Java 语法不在于记住所有 JDK API，而在于形成稳定习惯：哈希使用 Map/Set，BFS 使用 Queue，栈和单调结构使用 ArrayDeque，Top K 使用 PriorityQueue；所有区间明确开闭，所有比较避免溢出，所有中间求和考虑 long。每次写模板时理解不变量，比背一段代码更可靠。