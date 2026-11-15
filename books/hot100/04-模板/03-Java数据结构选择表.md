# Hot 100 数据结构选择表

[返回总目录](../../../README.md)

<section class="language-panel java-template-panel" data-lang-scope="true" data-lang="java" markdown="1">

## Java 数据结构选择

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

</section>

<section class="language-panel python-basic-panel" data-lang-scope="true" data-lang="python" markdown="1">

## Python 模式：Python 容器选择

`dict` 和 `set` 负责映射与去重，`deque` 负责双端队首操作，`heapq` 负责动态极值。

### 通过一个频次例子区分容器

输入 `nums = [1,1,1,2,2,3]` 时，`Counter` 得到 `{1:3, 2:2, 3:1}`。若找前 2 个高频元素，可先放 `(3,1)`、`(2,2)` 进容量 2 的小顶堆；再放 `(1,3)` 后堆有 3 项，弹出最小的 `(1,3)`，保留的是频次最高的两项。

`dict.get(key, [])` 只返回默认列表，不会把它写回字典；需要自动创建时应使用 `setdefault`、`defaultdict`，或显式先赋值。

### 栈和队列看从哪一端操作

列表模拟栈：`stack.append(x)` 入栈，`stack.pop()` 从末尾删除。BFS 需要从最早进入的一端取出，所以使用 `deque.popleft()`；从头部反复删除普通列表会让每次操作搬移元素。

### 可运行示例：频次表 + 容量 k 小顶堆

```python
from collections import Counter
import heapq


def top_k_frequent(nums: list[int], k: int) -> list[int]:
    counts = Counter(nums)
    heap = []
    for value, frequency in counts.items():
        heapq.heappush(heap, (frequency, value))
        if len(heap) > k:
            heapq.heappop(heap)
    answer = [0] * k
    for index in range(k - 1, -1, -1):
        answer[index] = heapq.heappop(heap)[1]
    return answer
```


### 模板动作与 Python 3.12 范围

`Counter` 扫描 n 个元素建立频次，平均 O(n)。设不同数值个数为 m，每个频次进入容量 k 的最小堆，维护成本 O(m log k)；最后输出 k 项。频次表占 O(m)，堆占 O(k)。

判题环境限定为 Python 3.12 / CPython；该版本标准库 `heapq` 以最小堆接口工作。需要最大堆时可存入负值，或使用自定义包装器。

堆中放 `(frequency, value)` 时，频次相同的候选还能继续比较整数 value，不会落到不可比较的普通对象上。

### 常用操作

| 操作 | 示例 | 在示例中的用途 |
|---|---|---|
| `Counter` | `counts = Counter(nums)` | 一次建立频次映射 |
| `deque` | `queue = deque([root])` | 建立均摊 O(1) 的两端操作队列 |
| `heapq.heappush` | `heapq.heappush(heap, item)` | 把一个候选加入堆 |

</section>
