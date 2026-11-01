# 50. Pow(x, n)

| 题目信息 | 内容 |
|---|---|
| 难度 | 中等 |
| 核心模式 | 快速幂（递归分治） |
| 时间复杂度 | O(log n) |
| 空间复杂度 | O(log n) |

## 题目与约束

实现 `pow(x, n)`，即计算 `x` 的整数 `n` 次幂函数（即 `x^n`）。

**示例 1：**

```
输入：x = 2.00000, n = 10
输出：1024.00000
```

**示例 2：**

```
输入：x = 2.10000, n = 3
输出：9.26100
```

**示例 3：**

```
输入：x = 2.00000, n = -2
输出：0.25000
解释：2^-2 = 1/2^2 = 1/4 = 0.25
```

**提示：**

- `-100.0 < x < 100.0`
- `-2^31 <= n <= 2^31 - 1`
- `n` 是一个整数
- 要么 `x` 不为零，要么 `n > 0`
- `-10^4 <= x^n <= 10^4`

## 核心不变量

> 把指数按「折半」递归：`x^n = (x^{n/2})^2`，奇数时再补乘一个 `x`；负指数先转成 `1/x` 与 `-n`（用 long 承接 `-n`，防止 `-2^31` 取反溢出）。

## 完整推导

### 思路推导

1. **直觉与痛点（为什么不能直接乘 n 次？）**

   最朴素的做法是循环乘 `n` 次，但 `n` 可达 `2^31 - 1`（约 21 亿），乘这么多次一定超时。必须找到让指数「快速变小」的规律。

2. **破局思路（折半）**

   注意到 `x^8 = (x^4)^2`、`x^4 = (x^2)^2`、`x^2 = (x^1)^2`。也就是说，算 `x^n` 可以先算 `x^{n/2}`，再把它平方；若 `n` 是奇数，平方后再乘一个 `x`。每递归一层指数就减半，只需约 `log₂ n` 层即可完成。以 `x=2, n=10` 为例：`2^10 = (2^5)^2`，`2^5 = (2^2)^2·2`，逐层回带得到 `1024`。

3. **关键追问（负指数与边界怎么处理？）**

   负指数满足 `x^{-n} = 1 / x^n`，先把 `x` 取倒数、指数取正即可。陷阱在于 `n = -2^31`：它的相反数 `2^31` 超出 `int` 上限，直接 `-n` 会溢出成负数。因此要先用 `long` 承接 `n`，再取反。另外 `n = 0` 时任何非零 `x` 都返回 `1.0`，作为递归出口。

### Java 实现（myPow）

```java
class Solution {
    public double myPow(double x, int n) {
        // 用 long 承接，防止 n == Integer.MIN_VALUE 时 -n 溢出
        long N = n;
        if (N < 0) {
            x = 1 / x;   // 负指数转正：x^(-N) = (1/x)^N
            N = -N;
        }
        return fastPow(x, N);
    }

    // 快速幂：x^n = (x^(n/2))^2，奇数再补乘 x
    private double fastPow(double x, long n) {
        if (n == 0) {
            return 1.0;
        }
        double half = fastPow(x, n / 2);
        if (n % 2 == 0) {
            return half * half;
        }
        return half * half * x;
    }
}
```

### 复杂度

- 时间：`O(log n)`，每层递归把指数折半，递归深度约 `log₂|n|`。
- 空间：`O(log n)`，递归调用栈的深度；若改写为迭代快速幂可做到 `O(1)`。

### 易错点与扩展（面试高频考点）

1. **`Integer.MIN_VALUE` 取反溢出**：`-(-2^31)` 在 `int` 下仍是 `-2^31`，必须用 `long` 承接后再取反。
2. **`x = 0` 与负指数**：题目保证「要么 x 非零，要么 n > 0」，但当 `x = 0` 且 `n < 0` 时数学上无意义，可提前返回按约定值处理。
3. **别写成朴素循环**：`n` 达 21 亿，`O(n)` 必超时，要能立刻说出快速幂。
4. **精度问题**：返回 `double`，直接按浮点乘即可，无需处理舍入；`half * half` 只算一次，避免重复递归。
5. **扩展（迭代快速幂）**：`while (n > 0) { if (n & 1) res *= base; base *= base; n >>= 1; }`，时间同为 `O(log n)`、空间 `O(1)`，是面试更常写的版本。

## 力扣原题

[50. Pow(x, n)](https://leetcode.cn/problems/powx-n/)

### C++ 实现

```cpp
class Solution {
public:
    double myPow(double x, int n) {
        long long N = n;          // 防止 -INT_MIN 溢出
        if (N < 0) {
            x = 1 / x;
            N = -N;
        }
        return fastPow(x, N);
    }

private:
    double fastPow(double x, long long n) {
        if (n == 0) return 1.0;
        double half = fastPow(x, n / 2);
        if (n % 2 == 0) return half * half;
        return half * half * x;
    }
};
```

### Python 实现

```python
class Solution:
    def myPow(self, x: float, n: int) -> float:
        def fast_pow(base: float, exp: int) -> float:
            if exp == 0:
                return 1.0
            half = fast_pow(base, exp // 2)
            if exp % 2 == 0:
                return half * half
            return half * half * base

        if n < 0:
            return fast_pow(1 / x, -n)
        return fast_pow(x, n)
```
