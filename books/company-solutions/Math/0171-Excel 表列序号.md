# 171. Excel 表列序号

| 题目信息 | 内容 |
|---|---|
| 难度 | 简单 |
| 核心模式 | 26 进制解析（1 起始） |
| 时间复杂度 | O(n) |
| 空间复杂度 | O(1) |

## 题目与约束

给你一个字符串 `columnTitle` ，表示 Excel 表格中的列名称。返回 该列名称对应的列序号 。

例如：

```
A -> 1
B -> 2
C -> 3
...
Z -> 26
AA -> 27
AB -> 28 
...
```

 

示例 1:

输入: columnTitle = "A"  
输出: 1

示例 2:

输入: columnTitle = "AB"  
输出: 28

示例 3:

输入: columnTitle = "ZY"  
输出: 701

 

提示：

- `1 <= columnTitle.length <= 7`

- `columnTitle` 仅由大写英文组成

- `columnTitle` 在范围 `["A", "FXSHRXW"]` 内

[🔗 前往力扣原题验证 →](https://leetcode.cn/problems/excel-sheet-column-number/)

## 核心不变量

> 从左到右扫描，累计值 = 累计值 × 26 + 当前字符代表的 `1~26`。每读入一位，就把之前所有高位整体左移一位（乘 26），再加上当前位。

## 完整推导

### 思路推导

1. **直觉与痛点（本质是什么进制？）**

   这道题是「168. Excel 表列名称」的**逆运算**：把形如 `"AB"` 的 26 进制字符串，还原成十进制数字。区别在于每一位的取值是 `1~26`（A=1、Z=26），而不是 `0~25`。

2. **破局思路（秦九韶 / 逐位累乘）**

   从左往右逐位处理，把当前结果乘以 26（相当于把已读部分整体抬高一位），再加上当前字符对应的数值 `c - 'A' + 1`。

   公式：`res = res * 26 + (c - 'A' + 1)`。

3. **关键例子（验证一遍就懂）**

   - `"AB"`：`res = 0`；读 `A`：`0 * 26 + 1 = 1`；读 `B`：`1 * 26 + 2 = 28`。✅
   - `"ZY"`：读 `Z`：`0 * 26 + 26 = 26`；读 `Y`：`26 * 26 + 25 = 701`。✅

   由于每一位都要 `+1`（A 从 1 开始），这与普通 26 进制"最后一位不加 1"完全不同，务必注意。

### Java 实现（titleToNumber）

```java
class Solution {
    public int titleToNumber(String columnTitle) {
        int res = 0;
        for (int i = 0; i < columnTitle.length(); i++) {
            // 当前字符的数值：A -> 1, B -> 2, ..., Z -> 26
            int val = columnTitle.charAt(i) - 'A' + 1;
            // 之前的结果整体左移一位（乘 26），再加上当前位
            res = res * 26 + val;
        }
        return res;
    }
}
```

### 复杂度

- 时间：`O(n)`，`n` 为字符串长度，只需一次线性扫描。
- 空间：`O(1)`，只用一个累加变量。

### 易错点与扩展（面试高频考点）

1. **字母值要 `+1`**：`A` 代表 `1` 而不是 `0`，写成 `c - 'A'` 会把所有结果系统性地算错。
2. **注意进位是乘 26**：每读一位要先把旧结果乘 26，别漏乘。
3. **不会溢出**：最大 `"FXSHRXW"` 恰为 `2^31 - 1`，用 `int` 足够，用 `long` 更保险也无妨。
4. **`"A"` 的边界**：单字符时 `0 * 26 + 1 = 1`，无需特判即可正确处理。
5. **与「168. Excel 表列名称」互为逆运算**：171 是字符串转数字，168 是数字转字符串，两个方向一起理解"1 起始进制"最透彻。

## 力扣原题

[171. Excel 表列序号](https://leetcode.cn/problems/excel-sheet-column-number/)

### C++ 实现

```cpp
#include <string>
using namespace std;

class Solution {
public:
    int titleToNumber(string columnTitle) {
        long long res = 0;
        for (char c : columnTitle) {
            int val = c - 'A' + 1;   // A -> 1, ..., Z -> 26
            res = res * 26 + val;    // 旧结果左移一位再加当前位
        }
        return (int)res;
    }
};
```

### Python 实现

```python
class Solution:
    def titleToNumber(self, columnTitle: str) -> int:
        res = 0
        for c in columnTitle:
            val = ord(c) - ord('A') + 1   # A -> 1, ..., Z -> 26
            res = res * 26 + val          # 旧结果左移一位再加当前位
        return res
```
