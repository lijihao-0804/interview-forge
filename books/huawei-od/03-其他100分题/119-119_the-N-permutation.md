# 119 第N个排列

[🔗 力扣对应题：60. 排列序列 →](https://leetcode.cn/problems/permutation-sequence/)


## 题目描述

给定参数`n`，从1到n有n个整数`1,2,3,...n`，这n个数字共有`n!`种排列，按大小顺序升序列出所有排列情况，并一一标记。

当`n = 3`时，所有排列如下：

`123, 132, 213, 231, 312, 321`

给定`n`和`k`，返回第`k`个排列。

## 输入描述

第一行是`n`，表示整数的范围。

第二行是`k`，表示需要获取的第`k`个位置上的数。取值范围是`1 ~ n!`。

## 输出描述

输出排序为第`k`位置的数字。

## 示例描述

### 示例一

**输入：**

```text
3
3
```

**输出：**

```text
213
```

### 示例二

**输入：**

```text
2
2
```

**输出：**

```text
21
```

## 解题思路

**基本思路：** 使用`itertools`的`permutations`函数，来生成排列。

1. 生成从1~n的数列`arr`。
2. 使用`itertools`的`permutations`函数生成`arr`的全排列。
3. 获取全排列中第`k`个位置的排列。
4. 将该排列表示成整数，并返回结果。

## 复杂度分析

- 时间复杂度：O(n!·n)，思路为生成全排列（Python 实现）；Java 采用逐位确定法为 O(n^2)。
- 空间复杂度：O(n!)，需存储全排列（Java 实现为 O(n)）。

## 解题代码

```python
import itertools


def solve_method(n, k):
    arr = [i + 1 for i in range(n)]
    perms = list(itertools.permutations(arr))
    result = int("".join(str(x) for x in perms[k - 1]))
    return result


if __name__ == '__main__':
    assert solve_method(3, 3) == 213
    assert solve_method(2, 2) == 21
```

```java
import java.util.*;

public class Solution {
    // k-th permutation (1-based) of 1..n, manual implementation
    static long solve(int n, long k) {
        List<Integer> nums = new ArrayList<>();
        long[] fact = new long[n + 1];
        fact[0] = 1;
        for (int i = 1; i <= n; i++) fact[i] = fact[i - 1] * i;
        for (int i = 1; i <= n; i++) nums.add(i);
        k = k - 1; // convert to 0-based index
        StringBuilder sb = new StringBuilder();
        for (int i = n; i >= 1; i--) {
            long f = fact[i - 1];
            int idx = (int) (k / f);
            k = k % f;
            sb.append(nums.get(idx));
            nums.remove(idx);
        }
        return Long.parseLong(sb.toString());
    }

    public static void main(String[] args) {
        if (solve(3, 3) != 213) throw new RuntimeException("c1 " + solve(3, 3));
        if (solve(2, 2) != 21) throw new RuntimeException("c2 " + solve(2, 2));
        System.out.println("OK 119N");
    }
}
```

## 力扣原题

[🔗 力扣对应题：60. 排列序列 →](https://leetcode.cn/problems/permutation-sequence/)
