# Java 集合（Collection）学习笔记

## 一、集合框架概述

Java 集合框架位于 `java.util` 包下，主要分为两大体系：

【 Collection 体系 】

                                ┌─────────────────┐
                                │ Iterable (接口) │
                                └────────┬────────┘
                                         │
                                ┌────────┴────────┐
                                │Collection (接口)│
                                └────────┬────────┘
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
            ┌───────┴───────┐    ┌───────┴───────┐    ┌───────┴───────┐
            │  List (接口)  │    │  Set (接口)   │    │ Queue (接口)  │
            └───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        ┌───────────┼───────────┐        │          ┌─────────┴─────────┐
        │           │           │        │          │                   │
    ┌───┴─────┐ ┌───┴────┐ ┌────┴───┐    │    ┌─────┴─────┐       ┌─────┴─────┐
    │ArrayList│ │ Vector │ │Linked- │    │    │Priority-  │       │   Deque   │
    └─────────┘ └───┬────┘ │List * │    │    │Queue      │       │  (接口)   │
                    │      └────────┘    │    └───────────┘       └─────┬─────┘
                 ┌──┴──┐                 │                    ┌─────────┴─────────┐
                 │Stack│                 │                    │                   │
                 └─────┘                 │              ┌─────┴─────┐       ┌─────┴─────┐
                                         │              │ArrayDeque │       │Linked-    │
                                         │              └───────────┘       │List * │
                                         │                                  └───────────┘
                 ┌───────────────────────┼──────────────────────┐
                 │                       │                      │
           ┌─────┴─────┐           ┌─────┴─────┐          ┌─────┴─────┐
           │  HashSet  │           │ SortedSet │          │  EnumSet  │
           └─────┬─────┘           │  (接口)   │          └───────────┘
                 │                 └─────┬─────┘
         ┌───────┴───────┐         ┌─────┴─────┐
         │ LinkedHashSet │         │  TreeSet  │
         └───────────────┘         └───────────┘
    
         (*注: LinkedList 同时实现了 List 和 Deque 接口，故在两处体系中均有体现)

【 Map 体系 】

                                ┌───────────────┐
                                │  Map (接口)   │
                                └───────┬───────┘
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
            │    HashMap    │   │   SortedMap   │   │   Hashtable   │
            └───────┬───────┘   │    (接口)     │   └───────┬───────┘
                    │           └───────┬───────┘           │
            ┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
            │ LinkedHashMap │   │    TreeMap    │   │  Properties   │
            └───────────────┘   └───────────────┘   └───────────────┘

Iterable (接口) - 顶层迭代接口
└── Collection (接口) - 单列集合顶层接口
    │
    ├── List (接口) ── 有序集合，允许元素重复
    │   ├── ArrayList (实现类) ── 基于动态数组，查询快，增删慢
    │   ├── Vector (实现类) ── 基于动态数组，线程安全（老旧，不推荐）
    │   │   └── Stack (实现类) ── 栈，后进先出
    │   └── LinkedList (实现类) ── 基于双向链表，增删快 (跨界实现了Deque)
    │
    ├── Set (接口) ── 无序集合，不允许元素重复
    │   ├── HashSet (实现类) ── 基于 HashMap 的 key 实现
    │   │   └── LinkedHashSet (实现类) ── 额外维护双向链表，保证插入/访问顺序
    │   ├── SortedSet (接口) ── 支持按元素自然规则排序的集合
    │   │   └── TreeSet (实现类) ── 基于红黑树实现，元素自动排序
    │   └── EnumSet (实现类) ── 专为枚举设计的位向量集合，效率极高
    │
    └── Queue (接口) ── 队列，先进先出
        ├── PriorityQueue (实现类) ── 优先级队列（基于小顶堆/大顶堆）
        └── Deque (接口) ── 双端队列（两端皆可进出）
            ├── ArrayDeque (实现类) ── 基于循环数组实现（推荐当作栈/队列使用）
            └── LinkedList (实现类) ── (见上文 List 体系)

Map (接口) ── 键值对双列集合，独立体系
├── HashMap (实现类) ── 基于哈希表（数组+链表/红黑树），查询最快
│   └── LinkedHashMap (实现类) ── 维护了双向链表，记录键值对的插入顺序
├── SortedMap (接口) ── 支持按键排序的 Map
│   └── TreeMap (实现类) ── 基于红黑树实现，Key 自动排序
└── Hashtable (实现类) ── 线程安全哈希表（老旧，不允许 null 键值）
    └── Properties (实现类) ── 键值对强制为 String，常用于读取 .properties 配置文件


| 接口 | 特点 | 常用实现类 |
|------|------|-----------|
| **List** | 有序、可重复、有索引 | `ArrayList`, `LinkedList` |
| **Set** | 无序（部分有序）、不可重复 | `HashSet`, `TreeSet`, `LinkedHashSet` |
| **Queue** | 队列，先进先出（FIFO） | `LinkedList`, `ArrayDeque`, `PriorityQueue` |
| **Deque** | 双端队列 | `ArrayDeque`, `LinkedList` |
| **Map** | 键值对，key 不可重复 | `HashMap`, `TreeMap`, `LinkedHashMap` |

---

## 二、Collection 接口（所有单列集合的根接口）

### 2.1 通用方法

```java
Collection<String> c = new ArrayList<>();

c.add("A");          // 添加元素
c.addAll(other);     // 添加另一集合的所有元素
c.remove("A");       // 移除指定元素
c.removeAll(other);  // 移除另一集合中包含的所有元素
c.clear();           // 清空
c.size();            // 元素个数
c.isEmpty();         // 是否为空
c.contains("A");     // 是否包含指定元素
c.containsAll(other);// 是否包含另一集合的所有元素
c.toArray();         // 转为 Object[]
c.toArray(new T[0]);// 转为指定类型数组
```

```java
Collection<String> c = new ArrayList<>();
c.add("a");
c.add("b");
c.add("c");

System.out.println(c.size());          // 3
System.out.println(c.contains("b"));   // true
System.out.println(c.isEmpty());       // false

Object[] arr = c.toArray();
System.out.println(Arrays.toString(arr)); // [a, b, c]

c.remove("b");
System.out.println(c);                 // [a, c]
```

---

## 三、List（列表）

**特点：** 有序（按插入顺序）、可重复、每个元素有索引。

### 3.1 ArrayList —— 底层数组，查询快，增删慢

```java
// 创建
List<String> list = new ArrayList<>();           // 初始容量10
List<String> list2 = new ArrayList<>(20);        // 指定初始容量
List<String> list3 = new ArrayList<>(list);      // 用已有集合构造

// 常用方法（List 特有）
list.add("A");              // 末尾添加
list.add(0, "B");           // 指定索引插入（后面的元素后移）
list.get(0);                // 获取指定索引元素
list.set(0, "C");           // 修改指定索引元素
list.remove(0);             // 删除指定索引元素
list.remove("A");           // 删除第一个匹配的元素
list.indexOf("A");          // 查找元素首次出现的索引，没有返回 -1
list.lastIndexOf("A");      // 查找元素最后出现的索引
list.subList(0, 2);         // 截取 [0,2) 子列表（注意：视图，不是新列表）
```

**完整示例：**
```java
List<Integer> list = new ArrayList<>();

// 添加
list.add(10);
list.add(20);
list.add(30);
list.add(1, 15);       // 在索引1处插入15
System.out.println(list);  // [10, 15, 20, 30]

// 获取与修改
System.out.println(list.get(2));   // 20
list.set(2, 25);
System.out.println(list);          // [10, 15, 25, 30]

// 删除
list.remove(1);              // 删除索引1的元素（15）
list.remove(Integer.valueOf(30)); // 删除元素30
System.out.println(list);    // [10, 25]

// 查找
System.out.println(list.indexOf(25));  // 1
System.out.println(list.contains(10)); // true
```

### 3.2 LinkedList —— 底层双向链表，增删快，查询慢

`LinkedList` 同时实现了 `List`、`Deque`、`Queue` 接口。

```java
LinkedList<Integer> list = new LinkedList<>();

// List 方法
list.add(1);
list.add(2);
list.addFirst(0);        // 头部添加
list.addLast(3);         // 尾部添加
System.out.println(list);// [0, 1, 2, 3]

System.out.println(list.getFirst());  // 0
System.out.println(list.getLast());   // 3

list.removeFirst();      // 删除头
list.removeLast();       // 删除尾
System.out.println(list);// [1, 2]
```

### 3.3 ArrayList vs LinkedList 对比

| 对比维度 | ArrayList | LinkedList |
|---------|-----------|------------|
| 底层结构 | 动态数组 | 双向链表 |
| 随机访问 `get(i)` | **O(1)** ✅ | O(n) ❌ |
| 末尾添加 | **O(1) 均摊** ✅ | O(1) ✅ |
| 中间插入/删除 | O(n) ❌ | **O(1)** ✅（前提是已知位置） |
| 头部插入/删除 | O(n) ❌ | **O(1)** ✅ |
| 内存占用 | 较小（只需存数据） | 较大（还需存前后指针） |
| **刷题推荐** | **90% 场景用这个** | 当作**双端队列**时用 |

> **刷题建议：** 大部分场景用 `ArrayList`。需要频繁在头部操作或做队列/栈时用 `LinkedList` 或 `ArrayDeque`。

---

## 四、Set（集合）

**特点：** 元素不可重复。

| 实现类 | 顺序 | 底层 | 特点 |
|-------|------|------|------|
| `HashSet` | 无序 | HashMap | 最快，O(1) |
| `LinkedHashSet` | 插入顺序 | 链表+哈希表 | 可保持插入顺序 |
| `TreeSet` | 自然顺序/比较器 | 红黑树 | 自动排序，O(log n) |

### 4.1 HashSet —— 最常用，无序

```java
Set<Integer> set = new HashSet<>();

set.add(3);
set.add(1);
set.add(2);
set.add(3);            // 重复元素，不会添加
System.out.println(set);   // 可能输出 [1, 2, 3]（无序）

// 常用方法
set.contains(1);       // true
set.remove(1);         // 移除
set.size();            // 2
set.isEmpty();         // false
set.clear();           // 清空

// 遍历
for (Integer x : set) {
    System.out.println(x);
}
```

### 4.2 TreeSet —— 自动排序

```java
TreeSet<Integer> ts = new TreeSet<>();
ts.add(5);
ts.add(1);
ts.add(9);
ts.add(3);
System.out.println(ts);  // [1, 3, 5, 9] 自动升序

// TreeSet 特有方法
System.out.println(ts.first());      // 最小值：1
System.out.println(ts.last());       // 最大值：9
System.out.println(ts.lower(5));     // 小于5的最大值：3
System.out.println(ts.higher(5));    // 大于5的最小值：9
System.out.println(ts.ceiling(4));   // >=4 的最小值：5
System.out.println(ts.floor(4));     // <=4 的最大值：3
```

### 4.3 Set 的去重原理

- **HashSet：** 先比较 `hashCode()`，再比较 `equals()`
- **TreeSet：** 依赖 `compareTo()` / `compare()`，返回 0 视为重复

> **重要：** 如果向 Set 中存放自定义对象，必须正确重写 `hashCode()` 和 `equals()`（HashSet）或实现 `Comparable`（TreeSet）。

---

## 五、Queue 与 Deque（队列与双端队列）

### 5.1 Queue —— 队列（先进先出）

```java
Queue<Integer> q = new LinkedList<>();  // 或 ArrayDeque

q.offer(1);          // 入队（推荐，不会抛异常）
q.offer(2);
q.offer(3);

System.out.println(q.peek());     // 查看队头：1（不删除）
System.out.println(q.poll());     // 出队：1（删除并返回）
System.out.println(q.poll());     // 2
System.out.println(q.poll());     // 3
System.out.println(q.poll());     // null（队列为空）

// 异常版本
q.add(1);            // 入队，失败抛异常
q.element();         // 查看队头，失败抛异常
q.remove();          // 出队，失败抛异常
```

> **`offer/poll/peek` vs `add/remove/element`：** 前者在失败时返回特殊值（null/false），后者抛异常。刷题用前者更安全。

### 5.2 Deque —— 双端队列（可用作栈或队列）

**推荐 `ArrayDeque`**，性能优于 `LinkedList` 和 `Stack`。

```java
Deque<Integer> deque = new ArrayDeque<>();

// 作为栈（后进先出 LIFO）—— 推荐
deque.push(1);        // 压栈：头部插入
deque.push(2);
deque.push(3);
System.out.println(deque);    // [3, 2, 1]

System.out.println(deque.peek());  // 查看栈顶：3
System.out.println(deque.pop());   // 出栈：3
System.out.println(deque.pop());   // 2
System.out.println(deque.pop());   // 1

// 作为队列（先进先出 FIFO）
deque.offer(1);       // 尾部添加
deque.offer(2);
System.out.println(deque.poll());  // 头部取出：1

// 双端操作
deque.addFirst(0);
deque.addLast(3);
System.out.println(deque.removeFirst());  // 0
System.out.println(deque.removeLast());   // 3
```

### 5.3 PriorityQueue —— 优先队列（堆）

底层是小顶堆（默认），可自定义比较器实现大顶堆。

```java
// 小顶堆（默认）
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
minHeap.offer(5);
minHeap.offer(1);
minHeap.offer(3);

System.out.println(minHeap.peek());   // 1（最小值在堆顶）
System.out.println(minHeap.poll());   // 1
System.out.println(minHeap.poll());   // 3
System.out.println(minHeap.poll());   // 5

// 大顶堆（自定义比较器）
PriorityQueue<Integer> maxHeap = new PriorityQueue<>((a, b) -> b - a);
maxHeap.offer(5);
maxHeap.offer(1);
maxHeap.offer(3);

System.out.println(maxHeap.peek());   // 5（最大值在堆顶）
```

**Top-K 问题经典写法：**
```java
// 找数组中最大的 k 个数 —— 用小顶堆
int[] nums = {3, 2, 1, 5, 6, 4};
int k = 3;
PriorityQueue<Integer> pq = new PriorityQueue<>();  // 小顶堆
for (int num : nums) {
    pq.offer(num);
    if (pq.size() > k) pq.poll();  // 保持堆中只有 k 个元素
}
// 堆中就是最大的 k 个数
System.out.println(pq);   // [4, 5, 6]
```

---

## 六、Map（映射）

**特点：** 键值对存储，key 不可重复。

| 实现类 | 顺序 | 底层 | key 比较 |
|-------|------|------|---------|
| `HashMap` | 无序 | 数组 + 链表/红黑树 | hashCode + equals |
| `LinkedHashMap` | 插入顺序或访问顺序 | 链表 + 哈希表 | hashCode + equals |
| `TreeMap` | key 的自然顺序/比较器 | 红黑树 | compareTo/compare |

### 6.1 HashMap —— 最常用

```java
Map<String, Integer> map = new HashMap<>();

// 增/改
map.put("Apple", 10);
map.put("Banana", 20);
map.put("Apple", 30);     // key 相同会覆盖 value
System.out.println(map);  // {Apple=30, Banana=20}

// 查
System.out.println(map.get("Apple"));         // 30
System.out.println(map.get("Orange"));        // null（不存在）
System.out.println(map.getOrDefault("Orange", 0));  // 0（不存在返回默认值）

// 判断
System.out.println(map.containsKey("Apple")); // true
System.out.println(map.containsValue(20));    // true
System.out.println(map.isEmpty());            // false

// 删
map.remove("Apple");       // 删除 key 为 Apple 的键值对

// 数量
System.out.println(map.size());   // 1
```

### 6.2 遍历 Map

```java
Map<String, Integer> map = new HashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

// 方式1：遍历 entrySet（推荐，效率最高）
for (Map.Entry<String, Integer> entry : map.entrySet()) {
    System.out.println(entry.getKey() + " -> " + entry.getValue());
}
// 输出：
// A -> 1
// B -> 2
// C -> 3

// 方式2：遍历 keySet
for (String key : map.keySet()) {
    System.out.println(key + " -> " + map.get(key));
}

// 方式3：遍历 values（只需要 value 时）
for (Integer value : map.values()) {
    System.out.println(value);
}

// 方式4：Java 8 forEach（Lambda 写法）
map.forEach((k, v) -> System.out.println(k + " -> " + v));
```

### 6.3 HashMap 常用技巧

```java
// 计数经典写法
String s = "aabbbcccc";
Map<Character, Integer> count = new HashMap<>();

for (char c : s.toCharArray()) {
    count.put(c, count.getOrDefault(c, 0) + 1);
}
System.out.println(count);  // {a=2, b=3, c=4}

// 或者更短的写法
for (char c : s.toCharArray()) {
    count.merge(c, 1, Integer::sum);
}
```

### 6.4 TreeMap —— 有序 Map

```java
TreeMap<String, Integer> tm = new TreeMap<>();
tm.put("C", 3);
tm.put("A", 1);
tm.put("B", 2);

System.out.println(tm);  // {A=1, B=2, C=3} 自动按 key 排序

// TreeMap 特有方法
System.out.println(tm.firstKey());      // A（最小 key）
System.out.println(tm.lastKey());       // C（最大 key）
System.out.println(tm.lowerKey("B"));   // A（小于 B 的最大 key）
System.out.println(tm.higherKey("B"));  // C（大于 B 的最小 key）
System.out.println(tm.ceilingKey("B")); // B（>= B 的最小 key）
System.out.println(tm.floorKey("B"));   // B（<= B 的最大 key）
```

### 6.5 LinkedHashMap —— 保持插入顺序

```java
Map<String, Integer> map = new LinkedHashMap<>();
map.put("C", 3);
map.put("A", 1);
map.put("B", 2);

System.out.println(map);  // {C=3, A=1, B=2} 保持插入顺序
```

### 6.6 HashMap 的常见遍历对比

| 遍历方式 | 推荐度 | 原因 |
|---------|-------|------|
| `entrySet()` for-each | ⭐⭐⭐⭐⭐ | 一次拿到 key 和 value，效率最高 |
| `keySet()` + `get()` | ⭐⭐⭐ | 需要额外查一次，略慢 |
| `forEach()` lambda | ⭐⭐⭐⭐ | 简洁，性能与 entrySet 相当 |

---

## 七、Collections 工具类

`Collections` 是操作集合的静态工具方法类。

```java
List<Integer> list = new ArrayList<>(Arrays.asList(3, 1, 4, 1, 5, 9));

// 排序
Collections.sort(list);                      // 升序：[1, 1, 3, 4, 5, 9]
Collections.sort(list, Collections.reverseOrder()); // 降序：[9, 5, 4, 3, 1, 1]

// 反转
Collections.reverse(list);

// 打乱顺序（洗牌）
Collections.shuffle(list);

// 最大/最小值
System.out.println(Collections.max(list));   // 9
System.out.println(Collections.min(list));   // 1

// 二分查找（必须先排序）
Collections.sort(list);
System.out.println(Collections.binarySearch(list, 4));  // 返回索引

// 填充
Collections.fill(list, 0);   // 全部填充为 0

// 复制
List<Integer> dest = new ArrayList<>(Collections.nCopies(6, 0));
Collections.copy(dest, list);  // 把 list 复制到 dest

// 频率
System.out.println(Collections.frequency(list, 1));  // 1 出现的次数

// 不可变集合
List<Integer> unmodifiable = Collections.unmodifiableList(list);
// unmodifiable.add(10);  // 抛 UnsupportedOperationException

// 空集合
List<String> empty = Collections.emptyList();
Set<String> emptySet = Collections.emptySet();
Map<String, String> emptyMap = Collections.emptyMap();

// 单元素集合
List<Integer> single = Collections.singletonList(100);
Set<Integer> singleSet = Collections.singleton(100);
Map<String, String> singleMap = Collections.singletonMap("key", "value");
```

---

## 八、Arrays 工具类

对**数组**进行操作的工具类。

```java
int[] arr = {3, 1, 4, 1, 5, 9};

// 排序
Arrays.sort(arr);                              // 全排
System.out.println(Arrays.toString(arr));      // [1, 1, 3, 4, 5, 9]

// 部分排序
int[] arr2 = {3, 1, 4, 1, 5, 9};
Arrays.sort(arr2, 0, 3);                       // 只排 [0,3)
System.out.println(Arrays.toString(arr2));     // [1, 3, 4, 1, 5, 9]

// 二分查找（必须先排序）
Arrays.sort(arr);
System.out.println(Arrays.binarySearch(arr, 4));   // 索引

// 填充
Arrays.fill(arr, 0);
System.out.println(Arrays.toString(arr));      // [0, 0, 0, 0, 0, 0]

// 复制
int[] copy = Arrays.copyOf(arr, 3);            // 复制前3个
int[] copyRange = Arrays.copyOfRange(arr, 1, 4); // 复制 [1,4)

// 比较
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};
System.out.println(Arrays.equals(a, b));       // true（比较内容）

// 转 List（注意：是固定长度的视图，不可增删）
List<String> list = Arrays.asList("A", "B", "C");
// list.add("D");  // ❌ 抛 UnsupportedOperationException
// List<Integer> list2 = Arrays.asList(1, 2, 3); // 泛型可自动推断

// 对对象数组排序（自定义比较器）
String[] words = {"banana", "apple", "cat"};
Arrays.sort(words, (x, y) -> x.length() - y.length());
System.out.println(Arrays.toString(words));   // [cat, apple, banana]
```

**特别注意 `Arrays.asList()`：**

```java
// ❌ 坑：基本类型数组
int[] nums = {1, 2, 3};
List<int[]> list = Arrays.asList(nums);   // 得到的是 List<int[]>，不是 List<Integer>！
System.out.println(list.size());          // 1（整个数组作为一个元素）

// ✅ 应使用包装类型
Integer[] nums2 = {1, 2, 3};
List<Integer> list2 = Arrays.asList(nums2);  // 正确
System.out.println(list2);                   // [1, 2, 3]

// ❌ 坑：返回的 List 不支持增删
List<String> list3 = Arrays.asList("A", "B");
// list3.add("C");  // 抛异常！

// ✅ 如果要可变，包装一下
List<String> list4 = new ArrayList<>(Arrays.asList("A", "B"));
list4.add("C");  // 可以
```

---

## 九、排序：Comparable vs Comparator

### 9.1 Comparable —— 自然排序（内部比较器）

让类本身实现 `Comparable` 接口，定义"默认"比较规则。

```java
public class Student implements Comparable<Student> {
    String name;
    int score;

    public Student(String name, int score) {
        this.name = name;
        this.score = score;
    }

    @Override
    public int compareTo(Student other) {
        // 按分数升序（分数相等则按姓名）
        if (this.score != other.score) {
            return this.score - other.score;    // 升序
        }
        return this.name.compareTo(other.name); // 字符串自然排序
    }

    @Override
    public String toString() {
        return name + "=" + score;
    }
}

// 使用
List<Student> students = Arrays.asList(
    new Student("小明", 85),
    new Student("小红", 92),
    new Student("小刚", 85)
);
Collections.sort(students);
System.out.println(students);  // [小刚=85, 小明=85, 小红=92]
```

### 9.2 Comparator —— 定制排序（外部比较器）

```java
List<Student> students = Arrays.asList(
    new Student("小明", 85),
    new Student("小红", 92),
    new Student("小刚", 85)
);

// 按分数降序（Lambda 写法）
students.sort((a, b) -> b.score - a.score);
System.out.println(students);  // [小红=92, 小明=85, 小刚=85]

// 链式比较
students.sort(Comparator
    .comparingInt((Student s) -> s.score)
    .reversed()
    .thenComparing(s -> s.name)
);

// PriorityQueue 自定义比较器
PriorityQueue<Student> pq = new PriorityQueue<>(
    (a, b) -> b.score - a.score  // 大顶堆（按分数降序）
);
```

### 9.3 升序降序记忆口诀

```
a - b > 0  → a > b → 升序（a 在 b 后面）
b - a > 0  → b > a → 降序（b 在 a 后面）

lambda 写法：
  (a, b) -> a - b    // 升序 （自然顺序）
  (a, b) -> b - a    // 降序 （逆序）
```

> **注意：** `a - b` 写法有**整数溢出**风险（如 `Integer.MIN_VALUE - 1`），更安全的写法：
> ```java
> (a, b) -> Integer.compare(a, b)    // 升序
> (a, b) -> Integer.compare(b, a)    // 降序
> ```

---

## 十、遍历方式总结

### 10.1 遍历 List

```java
List<String> list = Arrays.asList("A", "B", "C");

// 方式1：for 循环（带索引）
for (int i = 0; i < list.size(); i++) {
    System.out.println(list.get(i));
}

// 方式2：增强 for-each
for (String s : list) {
    System.out.println(s);
}

// 方式3：Iterator
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    System.out.println(it.next());
}

// 方式4：Java 8 forEach + Lambda
list.forEach(System.out::println);
```

### 10.2 遍历 Set

```java
Set<String> set = new HashSet<>(Arrays.asList("A", "B", "C"));

// 方式1：增强 for-each
for (String s : set) {
    System.out.println(s);
}

// 方式2：Iterator
Iterator<String> it = set.iterator();
while (it.hasNext()) {
    System.out.println(it.next());
}

// 方式3：forEach
set.forEach(System.out::println);
```

### 10.3 遍历 Map

```java
Map<String, Integer> map = new HashMap<>();
map.put("A", 1);
map.put("B", 2);

// ⭐ 方式1：entrySet（推荐）
for (Map.Entry<String, Integer> e : map.entrySet()) {
    System.out.println(e.getKey() + "=" + e.getValue());
}

// 方式2：keySet
for (String key : map.keySet()) {
    System.out.println(key + "=" + map.get(key));
}

// 方式3：values（只需要 value）
for (int val : map.values()) {
    System.out.println(val);
}

// 方式4：forEach
map.forEach((k, v) -> System.out.println(k + "=" + v));
```

---

## 十一、Java 8+ Stream API 快速入门

刷题中用 Stream 做简单的集合处理非常方便。

```java
List<Integer> nums = Arrays.asList(3, 1, 4, 1, 5, 9, 2, 6);

// 过滤
List<Integer> even = nums.stream()
    .filter(n -> n % 2 == 0)            // 只保留偶数
    .collect(Collectors.toList());
System.out.println(even);  // [4, 2, 6]

// 映射
List<String> strs = nums.stream()
    .map(n -> "数:" + n)
    .collect(Collectors.toList());
System.out.println(strs);  // [数:3, 数:1, 数:4, ...]

// 去重
List<Integer> distinct = nums.stream()
    .distinct()
    .collect(Collectors.toList());

// 排序
List<Integer> sorted = nums.stream()
    .sorted()
    .collect(Collectors.toList());

// 统计
int sum = nums.stream().mapToInt(Integer::intValue).sum();
double avg = nums.stream().mapToInt(Integer::intValue).average().orElse(0);
int max = nums.stream().mapToInt(Integer::intValue).max().orElse(0);

// List 转 Map
List<String> names = Arrays.asList("Alice", "Bob", "Charlie");
Map<String, Integer> nameMap = names.stream()
    .collect(Collectors.toMap(
        name -> name,               // key
        String::length              // value
    ));
System.out.println(nameMap);  // {Alice=5, Bob=3, Charlie=7}
```

---

## 十二、刷题常用集合技巧速查

### 12.1 快速创建集合

```java
// 快速创建 List
List<Integer> list = Arrays.asList(1, 2, 3);
List<Integer> list2 = List.of(1, 2, 3);  // Java 9+，不可变

// 快速创建 Set
Set<Integer> set = new HashSet<>(Arrays.asList(1, 2, 3));
Set<Integer> set2 = Set.of(1, 2, 3);         // Java 9+，不可变

// 快速创建 Map
Map<String, Integer> map = new HashMap<>() {{
    put("A", 1);
    put("B", 2);
}};
Map<String, Integer> map2 = Map.of("A", 1, "B", 2);  // Java 9+，不可变
```

### 12.2 数组与 List 互转

```java
// 数组 → List
String[] arr = {"A", "B", "C"};
List<String> list = new ArrayList<>(Arrays.asList(arr));

// List → 数组
List<Integer> nums = Arrays.asList(1, 2, 3);
Integer[] arr2 = nums.toArray(new Integer[0]);
int[] arr3 = nums.stream().mapToInt(Integer::intValue).toArray();  // 转基本类型数组
```

### 12.3 初始化带数据的 List

```java
// ArrayList 直接初始化
List<Integer> list = new ArrayList<>(Arrays.asList(1, 2, 3));
// Java 9+
List<Integer> list2 = new ArrayList<>(List.of(1, 2, 3));
```

### 12.4 统计频率

```java
// 统计字符出现次数
String s = "aabbbcccc";
Map<Character, Integer> freq = new HashMap<>();
for (char c : s.toCharArray()) {
    freq.put(c, freq.getOrDefault(c, 0) + 1);
}
// freq = {a=2, b=3, c=4}

// 按频率排序
List<Character> chars = new ArrayList<>(freq.keySet());
chars.sort((a, b) -> freq.get(b) - freq.get(a));  // 按频率降序
System.out.println(chars);  // [c, b, a]
```

### 12.5 滑动窗口常用数据结构

```java
// 1. 维护窗口中的最大值
Deque<Integer> deque = new ArrayDeque<>();  // 单调队列

// 2. 维护窗口中的元素个数
Map<Integer, Integer> window = new HashMap<>();

// 3. 维护窗口中的元素（有序）
TreeSet<Integer> set = new TreeSet<>();
```

### 12.6 取最大/最小 k 个元素

```java
// 最小 k 个 → 大顶堆
PriorityQueue<Integer> maxHeap = new PriorityQueue<>((a, b) -> b - a);
int k = 3;
for (int num : nums) {
    maxHeap.offer(num);
    if (maxHeap.size() > k) maxHeap.poll();
}

// 最大 k 个 → 小顶堆
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
for (int num : nums) {
    minHeap.offer(num);
    if (minHeap.size() > k) minHeap.poll();
}
```

### 12.7 合并多个 List

```java
List<Integer> a = Arrays.asList(1, 2, 3);
List<Integer> b = Arrays.asList(4, 5);

List<Integer> merged = new ArrayList<>();
merged.addAll(a);
merged.addAll(b);
System.out.println(merged);  // [1, 2, 3, 4, 5]

// Java 8 Stream 方式
List<Integer> merged2 = Stream.of(a, b)
    .flatMap(Collection::stream)
    .collect(Collectors.toList());
```

---

## 十三、集合性能速查表

| 操作 | ArrayList | LinkedList | HashSet | TreeSet | HashMap | TreeMap |
|------|-----------|-----------|---------|---------|---------|---------|
| 插入 | O(1) 末尾 / O(n) 中间 | O(1) 头尾 / O(n) 中间 | O(1) | O(log n) | O(1) | O(log n) |
| 删除 | O(n) | O(1) 头尾 / O(n) 中间 | O(1) | O(log n) | O(1) | O(log n) |
| 查找 | O(1) 按索引 / O(n) 按值 | O(n) | O(1) | O(log n) | O(1) key / O(n) value | O(log n) |
| 有序 | ✅ 插入顺序 | ✅ 插入顺序 | ❌ | ✅ 排序 | ❌ | ✅ 排序 |

---

## 十四、完整综合示例

```java
import java.util.*;
import java.util.stream.*;

public class CollectionDemo {
    public static void main(String[] args) {

        // ===== 1. List =====
        System.out.println("===== List =====");
        List<Integer> list = new ArrayList<>(Arrays.asList(3, 1, 4, 1, 5));
        list.add(9);
        list.remove(Integer.valueOf(1));   // 删除第一个 1
        System.out.println("List: " + list);                    // [3, 4, 1, 5, 9]
        System.out.println("get(2): " + list.get(2));           // 1
        System.out.println("indexOf(5): " + list.indexOf(5));   // 3

        // ===== 2. Set =====
        System.out.println("\n===== Set =====");
        Set<Integer> set = new HashSet<>(Arrays.asList(3, 1, 4, 1, 5, 9, 2, 6, 5));
        System.out.println("HashSet: " + set);                  // [1, 2, 3, 4, 5, 6, 9]（无序）
        System.out.println("contains(4): " + set.contains(4));  // true

        TreeSet<Integer> ts = new TreeSet<>(set);
        System.out.println("TreeSet: " + ts);                   // [1, 2, 3, 4, 5, 6, 9]
        System.out.println("ceiling(5): " + ts.ceiling(5));     // 5
        System.out.println("higher(5): " + ts.higher(5));       // 6

        // ===== 3. Queue =====
        System.out.println("\n===== Queue =====");
        Queue<Integer> q = new LinkedList<>();
        q.offer(10);
        q.offer(20);
        q.offer(30);
        System.out.println("Queue 出队: " + q.poll());          // 10
        System.out.println("Queue 出队: " + q.poll());          // 20
        System.out.println("Queue 出队: " + q.poll());          // 30

        // ===== 4. Stack (Deque) =====
        System.out.println("\n===== Stack =====");
        Deque<Integer> stack = new ArrayDeque<>();
        stack.push(1);
        stack.push(2);
        stack.push(3);
        while (!stack.isEmpty()) {
            System.out.print(stack.pop() + " ");               // 3 2 1
        }
        System.out.println();

        // ===== 5. PriorityQueue =====
        System.out.println("\n===== PriorityQueue =====");
        int[] nums = {4, 1, 7, 3, 8, 5};
        PriorityQueue<Integer> minHeap = new PriorityQueue<>();
        for (int n : nums) minHeap.offer(n);

        System.out.print("小顶堆出队: ");
        while (!minHeap.isEmpty()) {
            System.out.print(minHeap.poll() + " ");            // 1 3 4 5 7 8
        }
        System.out.println();

        // ===== 6. Map =====
        System.out.println("\n===== Map =====");
        Map<String, Integer> scores = new HashMap<>();
        scores.put("小明", 90);
        scores.put("小红", 85);
        scores.put("小刚", 95);
        scores.put("小明", 92);   // 覆盖

        System.out.println("小明的分数: " + scores.get("小明"));   // 92
        System.out.println("小花的分数(默认): " +
            scores.getOrDefault("小花", 0));                      // 0

        System.out.println("所有学生:");
        for (Map.Entry<String, Integer> e : scores.entrySet()) {
            System.out.println("  " + e.getKey() + " -> " + e.getValue());
        }

        // ===== 7. 计数应用 =====
        System.out.println("\n===== 计数 =====");
        String text = "hello world";
        Map<Character, Integer> freq = new HashMap<>();
        for (char c : text.toCharArray()) {
            freq.merge(c, 1, Integer::sum);
        }
        System.out.println(freq);
        // { =1, r=1, d=1, e=1, w=1, h=1, l=3, o=2}

        // ===== 8. 排序 =====
        System.out.println("\n===== 排序 =====");
        List<Integer> unsorted = new ArrayList<>(Arrays.asList(9, 3, 7, 1, 5));
        Collections.sort(unsorted);
        System.out.println("升序: " + unsorted);                 // [1, 3, 5, 7, 9]

        unsorted.sort(Collections.reverseOrder());
        System.out.println("降序: " + unsorted);                 // [9, 7, 5, 3, 1]

        // 按字符串长度排序
        List<String> words = Arrays.asList("banana", "apple", "cat", "dog");
        words.sort(Comparator.comparingInt(String::length));
        System.out.println("按长度排序: " + words);              // [cat, dog, apple, banana]

        // ===== 9. 不可变集合 =====
        System.out.println("\n===== 不可变集合 =====");
        List<Integer> immutable = List.of(1, 2, 3);
        // immutable.add(4);  // ❌ 编译不报错但运行抛异常
        System.out.println("不可变 List: " + immutable);

        Set<String> immutableSet = Set.of("A", "B", "C");
        Map<String, Integer> immutableMap = Map.of("x", 1, "y", 2);
        System.out.println("不可变 Map: " + immutableMap);

        // ===== 10. Stream 快速操作 =====
        System.out.println("\n===== Stream =====");
        List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);

        List<Integer> evenSquares = numbers.stream()
            .filter(n -> n % 2 == 0)                         // 只保留偶数
            .map(n -> n * n)                                 // 求平方
            .collect(Collectors.toList());
        System.out.println("偶数的平方: " + evenSquares);     // [4, 16, 36, 64, 100]

        int sum2 = numbers.stream()
            .mapToInt(Integer::intValue)
            .sum();
        System.out.println("总和: " + sum2);                  // 55
    }
}
```

**预期输出：**
```
===== List =====
List: [3, 4, 1, 5, 9]
get(2): 1
indexOf(5): 3

===== Set =====
HashSet: [1, 2, 3, 4, 5, 6, 9]
contains(4): true
TreeSet: [1, 2, 3, 4, 5, 6, 9]
ceiling(5): 5
higher(5): 6

===== Queue =====
Queue 出队: 10
Queue 出队: 20
Queue 出队: 30

===== Stack =====
3 2 1 

===== PriorityQueue =====
小顶堆出队: 1 3 4 5 7 8 

===== Map =====
小明的分数: 92
小花的分数(默认): 0
所有学生:
  小刚 -> 95
  小明 -> 92
  小红 -> 85

===== 计数 =====
{ =1, r=1, d=1, e=1, w=1, h=1, l=3, o=2}

===== 排序 =====
升序: [1, 3, 5, 7, 9]
降序: [9, 7, 5, 3, 1]
按长度排序: [cat, dog, apple, banana]

===== 不可变集合 =====
不可变 List: [1, 2, 3]
不可变 Map: {x=1, y=2}

===== Stream =====
偶数的平方: [4, 16, 36, 64, 100]
总和: 55
```

---

> **刷题核心记忆：**
> - `ArrayList` 用 90% 的场景
> - `HashMap` 计数、缓存、去重
> - `HashSet` 判重、集合运算
> - `ArrayDeque` 当栈/队列用（不用 Stack）
> - `PriorityQueue` Top-K、合并有序列表
> - `TreeMap` / `TreeSet` 需要有序/区间查找时用
> - `Arrays.sort()` / `Collections.sort()` 排序
> - `getOrDefault` 是计数的好帮手
