# Java 数组学习笔记

## 一、数组基础

### 1.1 什么是数组

**数组**是存储同一种类型数据的容器，长度固定，索引从 0 开始。

```java
// 数组的特点：
// 1. 存储相同类型的数据
// 2. 长度一旦确定不可改变
// 3. 通过索引访问，索引从 0 开始
// 4. 连续的内存空间
```

### 1.2 数组的声明与初始化

```java
// ===== 一维数组 =====

// 方式1：声明并分配空间
int[] arr1 = new int[5];        // 默认值：[0, 0, 0, 0, 0]

// 方式2：声明并初始化（静态初始化）
int[] arr2 = {1, 2, 3, 4, 5};

// 方式3：声明 + new + 初始化
int[] arr3 = new int[]{1, 2, 3, 4, 5};

// 方式4：先声明，后分配空间
int[] arr4;
arr4 = new int[3];

// ===== 二维数组 =====
int[][] matrix1 = new int[3][4];             // 3行4列，默认值 0
int[][] matrix2 = {{1,2}, {3,4}, {5,6}};    // 3行2列
int[][] matrix3 = new int[3][];              // 只指定行数，列数可以不同
matrix3[0] = new int[2];
matrix3[1] = new int[3];
matrix3[2] = new int[1];

// ===== 其他声明方式（不推荐）=====
int arr5[] = {1, 2, 3};          // C 风格，可读性差
int[] arr6[] = {{1,2}, {3,4}};   // 混合风格，容易混淆
```

```java
public class InitDemo {
    public static void main(String[] args) {
        int[] a = new int[3];          // [0, 0, 0]
        boolean[] b = new boolean[3];  // [false, false, false]
        String[] c = new String[3];    // [null, null, null]
        char[] d = new char[3];        // ['\0', '\0', '\0'] (空字符)

        int[] e = {10, 20, 30};
        System.out.println(e[0]);      // 10
        System.out.println(e[2]);      // 30
        System.out.println(e.length);  // 3
    }
}
```

---

## 二、数组常用操作

### 2.1 遍历

```java
int[] arr = {1, 2, 3, 4, 5};

// 方式1：普通 for 循环（带索引）
for (int i = 0; i < arr.length; i++) {
    System.out.println(arr[i]);
}

// 方式2：增强 for-each（无需索引）
for (int num : arr) {
    System.out.println(num);
}

// 方式3：Java 8+ Stream
Arrays.stream(arr).forEach(System.out::println);
```

### 2.2 填充

```java
int[] arr = new int[5];

Arrays.fill(arr, 10);              // [10, 10, 10, 10, 10]

Arrays.fill(arr, 1, 4, 100);       // [10, 100, 100, 100, 10] 填充 [1,4)

int[][] matrix = new int[3][3];
for (int[] row : matrix) {
    Arrays.fill(row, -1);          // 二维数组逐行填充
}
```

### 2.3 复制

```java
int[] src = {1, 2, 3, 4, 5};

// 方式1：Arrays.copyOf —— 从头复制指定长度
int[] copy1 = Arrays.copyOf(src, 3);          // [1, 2, 3]
int[] copy2 = Arrays.copyOf(src, 7);          // [1, 2, 3, 4, 5, 0, 0]（多出的补 0）

// 方式2：Arrays.copyOfRange —— 复制指定范围 [from, to)
int[] copy3 = Arrays.copyOfRange(src, 1, 4);  // [2, 3, 4]

// 方式3：System.arraycopy —— 复制到已有数组（最快）
int[] dest = new int[5];
System.arraycopy(src, 0, dest, 0, src.length); // [1, 2, 3, 4, 5]

// 方式4：clone()
int[] copy4 = src.clone();                    // [1, 2, 3, 4, 5]

// 方式5：for 循环手动复制
int[] copy5 = new int[src.length];
for (int i = 0; i < src.length; i++) {
    copy5[i] = src[i];
}
```

### 2.4 排序

```java
int[] arr = {5, 3, 1, 4, 2};

// 升序（默认）
Arrays.sort(arr);                     // [1, 2, 3, 4, 5]

// 部分排序
int[] arr2 = {5, 3, 1, 4, 2};
Arrays.sort(arr2, 0, 3);              // [1, 3, 5, 4, 2] 只排 [0,3)

// 降序（需要 Integer[]）
Integer[] arr3 = {5, 3, 1, 4, 2};
Arrays.sort(arr3, Collections.reverseOrder()); // [5, 4, 3, 2, 1]

// 自定义排序（二维数组按某列排序）
int[][] intervals = {{1, 3}, {2, 6}, {8, 10}, {15, 18}};
Arrays.sort(intervals, (a, b) -> a[0] - b[0]);  // 按第一列升序
Arrays.sort(intervals, (a, b) -> b[0] - a[0]);  // 按第一列降序
```

### 2.5 查找

```java
int[] arr = {1, 3, 5, 7, 9};

// 线性查找 —— 未排序时使用
int target = 5;
for (int i = 0; i < arr.length; i++) {
    if (arr[i] == target) {
        System.out.println("找到，索引: " + i);  // 2
    }
}

// 二分查找 —— 必须先排序！
Arrays.sort(arr);  // 确保有序
int index = Arrays.binarySearch(arr, 5);   // 2（找到返回索引）
int index2 = Arrays.binarySearch(arr, 4);  // -3（找不到返回 -(插入点+1)）

// 查找最大值/最小值
int max = Arrays.stream(arr).max().getAsInt();
int min = Arrays.stream(arr).min().getAsInt();
```

---

## 三、数组与集合互转

### 3.1 int[] ↔ List<Integer>

```java
// ===== int[] → List<Integer> =====

// 方法1：Stream（推荐）
int[] arr = {1, 2, 3, 4, 5};
List<Integer> list1 = Arrays.stream(arr)
    .boxed()
    .collect(Collectors.toList());
System.out.println(list1);  // [1, 2, 3, 4, 5]

// 方法2：for 循环
List<Integer> list2 = new ArrayList<>();
for (int num : arr) {
    list2.add(num);
}

// ===== List<Integer> → int[] =====
List<Integer> list = Arrays.asList(1, 2, 3, 4, 5);
int[] arr1 = list.stream()
    .mapToInt(Integer::intValue)
    .toArray();
System.out.println(Arrays.toString(arr1));  // [1, 2, 3, 4, 5]
```

### 3.2 String[] ↔ List<String>

```java
// ===== String[] → List<String> =====
String[] strs = {"A", "B", "C"};

// Arrays.asList() — 返回固定大小视图，不可增删！
List<String> list1 = Arrays.asList(strs);
// list1.add("D");  // ❌ 抛 UnsupportedOperationException

// 想要可变的 List：
List<String> list2 = new ArrayList<>(Arrays.asList(strs));
list2.add("D");  // ✅ 可以

// ===== List<String> → String[] =====
List<String> list = new ArrayList<>(Arrays.asList("A", "B", "C"));
String[] arr = list.toArray(new String[0]);
// 或
String[] arr2 = list.toArray(new String[list.size()]);
```

### 3.3 int[][] ↔ List<List<Integer>>

```java
// ===== int[][] → List<List<Integer>> =====
int[][] matrix = {{1, 2, 3}, {4, 5, 6}};

List<List<Integer>> list = new ArrayList<>();
for (int[] row : matrix) {
    list.add(Arrays.stream(row).boxed().collect(Collectors.toList()));
}
System.out.println(list);  // [[1, 2, 3], [4, 5, 6]]

// ===== List<List<Integer>> → int[][] =====
List<List<Integer>> list2 = Arrays.asList(
    Arrays.asList(1, 2, 3),
    Arrays.asList(4, 5, 6)
);
int[][] arr = list2.stream()
    .map(row -> row.stream().mapToInt(Integer::intValue).toArray())
    .toArray(int[][]::new);
```

---

## 四、数组常用算法模板

### 4.1 双指针

```java
// ===== 两数之和（有序数组）=====
public int[] twoSumSorted(int[] nums, int target) {
    int left = 0, right = nums.length - 1;
    while (left < right) {
        int sum = nums[left] + nums[right];
        if (sum == target) {
            return new int[]{left, right};
        } else if (sum < target) {
            left++;
        } else {
            right--;
        }
    }
    return new int[]{-1, -1};
}
// 输入: nums = [2, 7, 11, 15], target = 9
// 输出: [0, 1]
```

### 4.2 前缀和

```java
// preSum[i] = nums[0] + nums[1] + ... + nums[i-1]
// 区间 [l, r] 的和 = preSum[r+1] - preSum[l]

class PrefixSum {
    private int[] preSum;

    public PrefixSum(int[] nums) {
        preSum = new int[nums.length + 1];
        for (int i = 0; i < nums.length; i++) {
            preSum[i + 1] = preSum[i] + nums[i];
        }
    }

    /** 查询区间 [l, r] 的和 */
    public int rangeSum(int l, int r) {
        return preSum[r + 1] - preSum[l];
    }
}

// 示例
int[] nums = {1, 2, 3, 4, 5};
PrefixSum ps = new PrefixSum(nums);
System.out.println(ps.rangeSum(1, 3));  // 2+3+4 = 9
System.out.println(ps.rangeSum(0, 4));  // 1+2+3+4+5 = 15
```

### 4.3 差分数组

```java
// 适用于"多次区间增减，最后查结果"的场景

class Difference {
    private int[] diff;

    public Difference(int[] nums) {
        diff = new int[nums.length];
        diff[0] = nums[0];
        for (int i = 1; i < nums.length; i++) {
            diff[i] = nums[i] - nums[i - 1];
        }
    }

    /** 区间 [l, r] 增加 val */
    public void increment(int l, int r, int val) {
        diff[l] += val;
        if (r + 1 < diff.length) {
            diff[r + 1] -= val;
        }
    }

    /** 返回最终结果 */
    public int[] result() {
        int[] res = new int[diff.length];
        res[0] = diff[0];
        for (int i = 1; i < diff.length; i++) {
            res[i] = res[i - 1] + diff[i];
        }
        return res;
    }
}

// 示例
int[] nums = {0, 0, 0, 0, 0};
Difference df = new Difference(nums);
df.increment(1, 3, 2);      // [0, 2, 2, 2, 0]
df.increment(0, 2, -1);     // [-1, 1, 1, 2, 0]
System.out.println(Arrays.toString(df.result()));
```

### 4.4 滑动窗口

```java
// ===== 长度最小的子数组（和 ≥ target）=====
public int minSubArrayLen(int target, int[] nums) {
    int left = 0, sum = 0;
    int minLen = Integer.MAX_VALUE;

    for (int right = 0; right < nums.length; right++) {
        sum += nums[right];               // 扩大窗口
        while (sum >= target) {           // 满足条件，缩小窗口
            minLen = Math.min(minLen, right - left + 1);
            sum -= nums[left];
            left++;
        }
    }
    return minLen == Integer.MAX_VALUE ? 0 : minLen;
}
// 输入: target = 7, nums = [2,3,1,2,4,3]
// 输出: 2（子数组 [4,3]）
```

### 4.5 反转数组

```java
public void reverse(int[] arr) {
    int left = 0, right = arr.length - 1;
    while (left < right) {
        int temp = arr[left];
        arr[left] = arr[right];
        arr[right] = temp;
        left++;
        right--;
    }
}

// 反转部分
public void reverseRange(int[] arr, int l, int r) {
    while (l < r) {
        int temp = arr[l];
        arr[l] = arr[r];
        arr[r] = temp;
        l++;
        r--;
    }
}
```

### 4.6 二维数组遍历

```java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6},
    {7, 8, 9}
};

// ===== 按行遍历 =====
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        System.out.print(matrix[i][j] + " ");
    }
}
// 输出: 1 2 3 4 5 6 7 8 9

// ===== 按列遍历 =====
for (int j = 0; j < matrix[0].length; j++) {
    for (int i = 0; i < matrix.length; i++) {
        System.out.print(matrix[i][j] + " ");
    }
}
// 输出: 1 4 7 2 5 8 3 6 9

// ===== 对角线遍历 =====
for (int i = 0; i < matrix.length; i++) {
    System.out.print(matrix[i][i] + " ");  // 主对角线
}
// 输出: 1 5 9

// ===== 蛇形/螺旋遍历 =====
public List<Integer> spiralOrder(int[][] matrix) {
    List<Integer> result = new ArrayList<>();
    int top = 0, bottom = matrix.length - 1;
    int left = 0, right = matrix[0].length - 1;

    while (top <= bottom && left <= right) {
        // 向右
        for (int j = left; j <= right; j++) result.add(matrix[top][j]);
        top++;
        // 向下
        for (int i = top; i <= bottom; i++) result.add(matrix[i][right]);
        right--;
        // 向左
        if (top <= bottom) {
            for (int j = right; j >= left; j--) result.add(matrix[bottom][j]);
            bottom--;
        }
        // 向上
        if (left <= right) {
            for (int i = bottom; i >= top; i--) result.add(matrix[i][left]);
            left++;
        }
    }
    return result;
}
// 输入: matrix = [[1,2,3],[4,5,6],[7,8,9]]
// 输出: [1,2,3,6,9,8,7,4,5]
```

---

## 五、Arrays 工具类完整速查

```java
import java.util.Arrays;

int[] arr = {3, 1, 4, 1, 5, 9, 2, 6};
int[] arr2 = {1, 2, 3};

// === 排序 ===
Arrays.sort(arr);                           // 全排
Arrays.sort(arr, 0, 3);                     // 部分排序 [0,3)
Arrays.parallelSort(arr);                   // 并行排序（大数据量更快）

// === 查找 ===
Arrays.binarySearch(arr, 4);                // 二分查找（先排序）

// === 比较 ===
Arrays.equals(arr, arr2);                   // 比较内容是否相等
Arrays.deepEquals(new int[][]{arr}, new int[][]{arr2}); // 多维数组比较

// === 填充 ===
Arrays.fill(arr, 0);                        // 全部填充
Arrays.fill(arr, 1, 4, 0);                  // 部分填充 [1,4)

// === 复制 ===
Arrays.copyOf(arr, 3);                      // 复制前3个
Arrays.copyOfRange(arr, 1, 4);              // 复制 [1,4)

// === 转字符串 ===
Arrays.toString(arr);                       // [1, 2, 3, 4, ...]
Arrays.deepToString(new int[][]{arr, arr2}); // [[...], [...]]

// === 转 List ===
Arrays.asList("A", "B", "C");               // 返回固定大小 List（不可增删）
Arrays.asList(arr);                          // ⚠️ 基本类型数组不行！

// === Stream（Java 8+）===
Arrays.stream(arr).sum();                   // 求和
Arrays.stream(arr).average();               // 平均值
Arrays.stream(arr).max();                   // 最大值
Arrays.stream(arr).min();                   // 最小值
Arrays.stream(arr).count();                 // 元素个数
Arrays.stream(arr).filter(n -> n > 3).toArray();  // 过滤

// === 其他 ===
Arrays.hashCode(arr);                       // 计算哈希
Arrays.mismatch(arr, arr2);                 // 找到第一个不同位置的索引
Arrays.setAll(arr, i -> i * i);             // 按索引设置值
Arrays.parallelPrefix(arr, Integer::sum);   // 原地前缀和（并行）
```

---

## 六、刷题高频技巧

### 6.1 快速初始化

```java
// 一维
int[] arr = {5, 2, 8, 1, 9};
int[] arr2 = new int[]{5, 2, 8, 1, 9};

// 二维
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6}
};

// 全排列数组（用于测试）
int[] test = IntStream.range(0, 10).toArray();  // [0,1,2,...,9]
```

### 6.2 最大/最小值

```java
// 初始化变量
int maxVal = Integer.MIN_VALUE;
int minVal = Integer.MAX_VALUE;

for (int num : nums) {
    maxVal = Math.max(maxVal, num);
    minVal = Math.min(minVal, num);
}

// 或用 Stream
int max = Arrays.stream(nums).max().getAsInt();
int min = Arrays.stream(nums).min().getAsInt();
```

### 6.3 交换元素

```java
private void swap(int[] arr, int i, int j) {
    int temp = arr[i];
    arr[i] = arr[j];
    arr[j] = temp;
}
```

### 6.4 数组拷贝（用于回溯）

```java
// 回溯/递归中需要保存状态快照时
int[] state = {1, 2, 3};
int[] snapshot = state.clone();          // 深拷贝（一维）
int[] snapshot2 = Arrays.copyOf(state, state.length);
```

### 6.5 判断数组是否有序

```java
public boolean isSorted(int[] nums) {
    for (int i = 1; i < nums.length; i++) {
        if (nums[i] < nums[i - 1]) {
            return false;
        }
    }
    return true;
}

public boolean isSortedDesc(int[] nums) {
    for (int i = 1; i < nums.length; i++) {
        if (nums[i] > nums[i - 1]) {
            return false;
        }
    }
    return true;
}
```

### 6.6 二维数组按某列排序

```java
int[][] people = {{7, 0}, {4, 4}, {7, 1}, {5, 0}, {6, 1}, {5, 2}};

// 按第一列降序，第一列相同则按第二列升序
Arrays.sort(people, (a, b) -> a[0] != b[0] ? b[0] - a[0] : a[1] - b[1]);
// 结果: [[7,0],[7,1],[6,1],[5,0],[5,2],[4,4]]
```

### 6.7 计数数组（替代 HashMap）

```java
// 当数据范围确定且较小时，用数组比 HashMap 快得多

// 统计小写字母出现次数
String s = "leetcode";
int[] count = new int[26];
for (char c : s.toCharArray()) {
    count[c - 'a']++;
}
// count['l'-'a']=1, count['e'-'a']=3, ...

// 统计数字 0-100 出现次数
int[] nums = {3, 5, 3, 7, 2, 3, 8, 5};
int[] freq = new int[101];
for (int num : nums) {
    freq[num]++;
}
// freq[3]=3, freq[5]=2, ...
```

### 6.8 差分数组 + 前缀和（一次遍历统计）

```java
// 场景：多次区间增减操作后求最终结果
// 例：n 次操作，每次 [l, r] 区间加 val

int[] diff = new int[n + 1];    // 多开一位防止越界
for (int[] op : operations) {
    int l = op[0], r = op[1], val = op[2];
    diff[l] += val;
    diff[r + 1] -= val;
}

// 还原
int[] result = new int[n];
int cur = 0;
for (int i = 0; i < n; i++) {
    cur += diff[i];
    result[i] = cur;
}
```

---

## 七、大数乘除/溢出示警

```java
// ❌ 错误
int mid = (left + right) / 2;    // left+right 可能溢出！

// ✅ 正确
int mid = left + (right - left) / 2;

// ❌ 错误
int area = width * height;       // 结果可能超出 int 范围

// ✅ 正确
long area = (long) width * height;
```

---

## 八、数组时间复杂度速查

| 操作 | 时间复杂度 | 说明 |
|------|-----------|------|
| 随机访问 `arr[i]` | O(1) | 通过索引，最核心的优势 |
| 修改 `arr[i] = x` | O(1) | 直接赋值 |
| 遍历 | O(n) | 需要访问每个元素 |
| 查找（无序） | O(n) | 线性搜索 |
| 查找（有序，二分） | O(log n) | 前提是已排序 |
| 插入（末尾） | O(1) | 长度不可变，需新数组时才涉及 |
| 插入（中间） | O(n) | 需移动元素 |
| 删除 | O(n) | 需移动元素 |
| 排序 | O(n log n) | `Arrays.sort()` 双轴快排 |
| `Arrays.copyOf` | O(n) | 复制全部元素 |
| `System.arraycopy` | O(n) | 复制指定范围 |

---

> **一句话总结：** 数组是刷题基础中的基础 — 索引访问 O(1)、查找 O(n)、排序 O(n log n)。配合双指针、前缀和、滑动窗口等技巧可以解决大量高频题。数据范围较小时，数组比 HashMap 快得多，优先考虑。
