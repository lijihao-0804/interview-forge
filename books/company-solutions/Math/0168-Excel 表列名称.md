# 168. Excel 表列名称

| 题目信息 | 内容 |
|---|---|
| 难度 | 简单 |
| 核心模式 | 26 进制转换（1 起始的双射进制） |
| 时间复杂度 | O(log₂₆ n) |
| 空间复杂度 | O(log₂₆ n) |

## 题目与约束

给你一个整数 `columnNumber` ，返回它在 Excel 表中相对应的列名称。

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

 

示例 1：

输入：columnNumber = 1  
输出："A"

示例 2：

输入：columnNumber = 28  
输出："AB"

示例 3：

输入：columnNumber = 701  
输出："ZY"

示例 4：

输入：columnNumber = 2147483647  
输出："FXSHRXW"

 

提示：

- `1 <= columnNumber <= 231 - 1`

[🔗 前往力扣原题验证 →](https://leetcode.cn/problems/excel-sheet-column-title/)

## 核心不变量

> 这是"1~26"而非"0~25"的进制：每轮先把 `columnNumber` 减 1，把当前位映射到 `0~25`，再对 26 取模取字母、整除 26 进位。取出的字符是最低位，最后需反转。

## 完整推导

### 思路推导

1. **直觉与痛点（直接当 26 进制为什么会错？）**

   看起来像 26 进制，但普通 26 进制每一位是 `0~25`，而这里每一位是 `A~Z` 对应 `1~26`，**没有"0"这个数字**。如果直接 `n % 26`，当 `n = 26` 时 `26 % 26 = 0`，映射到 `'A' + 0 = 'A'`，可正确答案应该是 `"Z"`，显然错了。

2. **破局思路（先减 1 再取模）**

   关键动作：**每轮先把 `n` 减 1**，把 `1~26` 平移到 `0~25`，此时 `n % 26` 就恰好对应 `A~Z`；然后 `n /= 26` 继续处理高位。

   以 `n = 28` 为例：第一轮 `n-1 = 27`，`27 % 26 = 1 → 'B'`，`n = 27 / 26 = 1`；第二轮 `n-1 = 0`，`0 % 26 = 0 → 'A'`，`n = 0` 结束。收集到 `'B'`、`'A'`，反转后为 `"AB"`，正确。再验证 `n = 26`：`n-1 = 25`，`25 % 26 = 25 → 'Z'`，`n = 25 / 26 = 0` 直接结束，结果 `"Z"`，也正确。

3. **关键追问（顺序与反转）**

   每轮取出的都是**当前最低位**，所以拼接出来的字符串是"低位在前"，最后必须**反转**才是正确顺序。用 `StringBuilder` 追加后 `reverse()` 最简洁。

### Java 实现（convertToTitle）

```java
class Solution {
    public String convertToTitle(int columnNumber) {
        StringBuilder sb = new StringBuilder();
        while (columnNumber > 0) {
            // 先减 1：把 1~26 映射到 0~25，才能用 % 26 正确取字母
            columnNumber--;
            sb.append((char) ('A' + columnNumber % 26));
            columnNumber /= 26;
        }
        // 每轮先取的是低位，需要反转
        return sb.reverse().toString();
    }
}
```

### 复杂度

- 时间：`O(log₂₆ n)`，每轮把 `n` 除以 26，循环次数为 26 进制位数。
- 空间：`O(log₂₆ n)`，用于存放结果字符串（不计返回值则为 `O(1)`）。

### 易错点与扩展（面试高频考点）

1. **必须"先减 1"**：这是与普通 26 进制唯一的、也是最致命的区别，因为没有 0 这个"数字"。
2. **结果要反转**：取位从低位开始，忘记反转会把 `"AB"` 输出成 `"BA"`。
3. **边界 `n = 26`**：直接 `% 26` 会得到 `'A'`，正确应为 `'Z'`，是检验是否理解"减 1"的经典用例。
4. **`n = 1` 直接得 `"A"`**：`1 → 0 → 'A'`，无需额外特判。
5. **与「171. Excel 表列序号」互为逆运算**：168 是数字转字符串，171 是字符串转数字，建议对照复习双射进制。

## 力扣原题

[168. Excel 表列名称](https://leetcode.cn/problems/excel-sheet-column-title/)

### C++ 实现

```cpp
#include <string>
#include <algorithm>
using namespace std;

class Solution {
public:
    string convertToTitle(int columnNumber) {
        string res;
        while (columnNumber > 0) {
            columnNumber--;                     // 先减 1，映射为 0~25
            res += char('A' + columnNumber % 26);
            columnNumber /= 26;
        }
        reverse(res.begin(), res.end());        // 低位在前，需反转
        return res;
    }
};
```

### Python 实现

```python
class Solution:
    def convertToTitle(self, columnNumber: int) -> str:
        res = []
        while columnNumber > 0:
            columnNumber -= 1                   # 先减 1，映射为 0~25
            res.append(chr(ord('A') + columnNumber % 26))
            columnNumber //= 26
        return ''.join(reversed(res))           # 低位在前，需反转
```
