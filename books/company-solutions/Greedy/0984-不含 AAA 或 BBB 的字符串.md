# 984. 不含 AAA 或 BBB 的字符串

| 题目信息 | 内容 |
|---|---|
| 难度 | 中等 |
| 核心模式 | 贪心：优先放剩余较多的字母，凑成三连时改放另一个 |
| 时间复杂度 | O(a + b) |
| 空间复杂度 | O(a + b)（结果字符串） |

## 题目与约束

给定两个整数 `a` 和 `b` ，返回 任意 字符串 `s` ，要求满足：

- `s` 的长度为 `a + b`，且正好包含 `a` 个 `'a'` 字母与 `b` 个 `'b'` 字母；

- 子串 `'aaa'` 没有出现在 `s` 中；

- 子串 `'bbb'` 没有出现在 `s` 中。

 

示例 1：

输入：a = 1, b = 2  
输出："abb"  
解释："abb", "bab" 和 "bba" 都是正确答案。

示例 2：

输入：a = 4, b = 1  
输出："aabaa"

 

提示：

- `0 <= a, b <= 100`

- 对于给定的 `a` 和 `b`，保证存在满足要求的 `s` 

​​​

[🔗 前往力扣原题验证 →](https://leetcode.cn/problems/string-without-aaa-or-bbb/)

## 核心不变量

> 题目保证有解，即两字母数量差距受限；每一步都优先写"当前剩余较多"的字母，只有它已在末尾连写两个时才改写另一个，就永远不会形成三连。

## 完整推导

### 思路推导

1. **直觉与痛点（最朴素的想法）**
   想不出现 `aaa` / `bbb`，最自然的做法是尽量让两个字母交替出现。但两个字母数量可能相差较大（如 `a=4, b=1`），此时必须允许同一字母偶尔连写两个，只是绝不能到三个。

2. **破局思路（贪心：谁多写谁）**
   每一步比较剩余的 `a` 与 `b`：谁多就把谁放到末尾。放之前先看末尾是否已经连续两个都是该字母——如果是，再放它就会变成三连，于是这一步改放另一个字母来"打断"。

3. **为什么贪心可行**
   由于题目保证有解，两字母数量差不会超过另一方的两倍。"较多者优先 + 末尾已两连就换"这套规则能让数量始终保持"至多相差一个合理上界"，不会走到"只剩某字母却被迫三连"的死局。

   小例子：`a=4, b=1`。依次放 `a`、`a`（此时末尾 `"aa"`）→ 再想放 `a` 会成三连，改放 `b` → 之后继续放 `a`、`a`，得到 `"aabaa"`。

### Java 实现（strWithout3a3b）

```java
class Solution {
    public String strWithout3a3b(int a, int b) {
        StringBuilder sb = new StringBuilder();
        while (a > 0 || b > 0) {
            int len = sb.length();
            // 末尾是否已经连续出现两个相同字母
            boolean tailAA = len >= 2 && sb.charAt(len - 1) == 'a' && sb.charAt(len - 2) == 'a';
            boolean tailBB = len >= 2 && sb.charAt(len - 1) == 'b' && sb.charAt(len - 2) == 'b';

            if (a >= b) {
                if (tailAA) {        // 再放 a 就成三连，改放 b
                    sb.append('b');
                    b--;
                } else {
                    sb.append('a');
                    a--;
                }
            } else {
                if (tailBB) {        // 再放 b 就成三连，改放 a
                    sb.append('a');
                    a--;
                } else {
                    sb.append('b');
                    b--;
                }
            }
        }
        return sb.toString();
    }
}
```

### 复杂度

- 时间：O(a + b)。循环恰好执行 `a + b` 次，每次只做 O(1) 的判断与追加。
- 空间：O(a + b)。结果字符串长度为 `a + b`；若不计返回值，额外空间仅常数个变量。

### 易错点与扩展（面试高频考点）

1. **三连判断要看"末尾两个"**：只有当前末尾已经有连续两个相同字母时才算"再放会成三连"，用 `len >= 2` 防止越界，这一点最容易写错。
2. **比较用 `>=` 还是 `>`**：`a >= b` 时优先放 `a`，保证相等时也有明确、稳定的选择；配合三连检查即可覆盖所有情况。
3. **死循环 / 数量变负**：只有在题目保证有解的输入下，`tailAA` 分支放 `b` 才不会让 `b` 越界；若允许无解输入，需要先判断 `a > 2*(b+1)` 之类的可行性，直接返回空串。
4. **另一种等价写法**：先按数量较多者为主、每轮在较多者一侧输出"两个 + 一个"分组拼接，再用少量剩余补尾；本质与逐字符贪心一致。
5. **扩展**：把"禁止连续 k 个"一般化后，可用"按比例插空"（类似任务调度、安排任务 LeetCode 621）的思路构造，关注 `maxCount` 与间隔的分段。

## 力扣原题

[984. 不含 AAA 或 BBB 的字符串](https://leetcode.cn/problems/string-without-aaa-or-bbb/)

### C++ 实现

```cpp
#include <string>
using namespace std;

class Solution {
public:
    string strWithout3a3b(int a, int b) {
        string res;
        while (a > 0 || b > 0) {
            int len = res.size();
            bool tailAA = len >= 2 && res[len - 1] == 'a' && res[len - 2] == 'a';
            bool tailBB = len >= 2 && res[len - 1] == 'b' && res[len - 2] == 'b';
            if (a >= b) {
                if (tailAA) { res.push_back('b'); b--; }
                else        { res.push_back('a'); a--; }
            } else {
                if (tailBB) { res.push_back('a'); a--; }
                else        { res.push_back('b'); b--; }
            }
        }
        return res;
    }
};
```

### Python 实现

```python
class Solution:
    def strWithout3a3b(self, a: int, b: int) -> str:
        res = []
        while a > 0 or b > 0:
            tail_aa = len(res) >= 2 and res[-1] == 'a' and res[-2] == 'a'
            tail_bb = len(res) >= 2 and res[-1] == 'b' and res[-2] == 'b'
            if a >= b:
                if tail_aa:       # 再放 a 会成三连，改放 b
                    res.append('b')
                    b -= 1
                else:
                    res.append('a')
                    a -= 1
            else:
                if tail_bb:       # 再放 b 会成三连，改放 a
                    res.append('a')
                    a -= 1
                else:
                    res.append('b')
                    b -= 1
        return ''.join(res)
```
