# Java 数据结构选择表

[返回总目录](../../../README.md)

| 需要 | 推荐结构 | 关键操作 | 常见坑 |
|---|---|---|---|
| 键到值、计数、定位 | `HashMap<K,V>` | `getOrDefault`、`merge`、`computeIfAbsent` | `getOrDefault` 不会自动写回 |
| 去重、O(1) 存在性 | `HashSet<E>` | `add`、`contains`、`remove` | 不保证遍历顺序 |
| 尾部动态追加 | `ArrayList<E>` | `add`、`get`、`remove(size-1)` | `remove(int)` 与 `remove(Object)` 重载 |
| 栈 | `ArrayDeque<E>` | `push`、`pop`、`peek` | 不允许 `null` |
| 队列 | `ArrayDeque<E>` | `offer`、`poll`、`peek` | 不建议 `LinkedList` 作为默认选择 |
| 双端/单调队列 | `ArrayDeque<E>` | `offerLast`、`pollFirst`、`peekLast` | 明确队首队尾语义 |
| 动态极值、Top K | `PriorityQueue<E>` | `offer`、`poll`、`peek` | 默认是小顶堆 |
| 有序键与边界查询 | `TreeMap<K,V>` | `floorKey`、`ceilingKey` | O(log n)，不要误认为 O(1) |

优先使用接口类型声明变量，例如 `Map<Integer, Integer> map = new HashMap<>();`。完整 API 见 [Java 刷题速查](../01-基础/01-Java刷题速查.md)。
