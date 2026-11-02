# 037 判断牌型

## 题目描述

五张牌每张牌由牌大小和花色组成：牌大小`2~10`、`J`、`Q`、`K`、`A`，花色四种分别是红桃、黑桃、梅花、方块。

判断牌型：
- 牌型一 同花顺：同一花色的顺子，如红桃2、红桃3、红桃4、红桃5、红桃6。
- 牌型二 四条：四张相同数字+单张，如红桃A、黑桃A、梅花A、方块A、黑桃2。
- 牌型三 葫芦：三张相同数字+一对，如红桃5、黑桃5、梅花5、方块9、梅花9。
- 牌型四 同花：同一种花色，如方块3、方块7、方块10、方块J、方块2。
- 牌型五 顺子：花色不一样的顺子，如红桃2、黑桃3、红桃4、红桃5、方块6。
- 牌型六 三条：三张相同+两张单张。
- 牌型七 其他

## 输入描述

输入由5行组成，每行是一张牌大小和花色。牌大小为`2~10`、`J`、`Q`、`K`、`A`，花色分别用字符`H`、`S`、`C`、`D`表示红桃、黑桃、梅花、方块。

## 输出描述

输出牌型序号，五张牌符合多种牌型时，取最大的牌型序号输出。

五张牌中不会出现数字大小和花色完全相同的牌，编号小的牌型较大，包含`A`的合法顺子只有`10 J Q  K A`、`A 2 3 4 5`，类似`KA234`不是合法顺子。

## 示例描述

### 示例一

**输入：**

```text
4 H
5 S
6 C
7 D
8 D
```

**输出：**

```text
5
```

### 示例二

**输入：**

```text
9 S
5 S
6 S
7 S
8 S
```

**输出：**

```text
1
```

## 解题思路

**基本思路：** 

1. 遍历5张牌：存储牌大小`nums`、牌花色`colors`。
2. 编写牌型函数：同花`check_tonghua`、顺子`check_shunzi`、四条`check_four`、葫芦`check_hulu`、三条`check_three`。
3. 依次判断牌型，顺序为同花顺、四条、葫芦、同花、顺子、三条、其他。当同花和顺子两个条件同时成立，即为同花顺。
4. 返回牌型结果。

## 解题代码

```Python
from collections import Counter


# 同花
def check_tonghua(colors):
    # 判断花色是否一致
    return len(set(colors)) == 1


# 顺子
def check_shunzi(cards, nums):
    if "".join(nums) == "2345A":
        return True
    # 检查是否构成顺子
    for i in range(1, len(nums)):
        if cards[nums[i - 1]] + 1 != cards[nums[i]]:
            return False

    return True


# 四条
def check_four(nums):
    num_count = Counter(nums)
    return 4 in num_count.values()


# 葫芦
def check_hulu(nums):
    num_count = Counter(nums)

    # 检查是否存在三张相同牌值的牌和两张相同牌值的牌
    values = num_count.values()
    return len(values) == 2 and (2 in values or 3 in values)


# 三条
def check_three(nums):
    num_count = Counter(nums)
    # 判断是否有三张相同牌值得牌
    return 3 in num_count.values()


def solve_method(pokers):
    cards = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13,
             "A": 14}
    nums = []
    colors = []
    for poker in pokers:
        nums.append(poker[0])
        colors.append(poker[1])

    nums = sorted(nums, key=lambda x: cards[str(x)])
    shunzi_checked = check_shunzi(cards, nums)
    tonghua_checked = check_tonghua(colors)
    if shunzi_checked and tonghua_checked:
        return 1
    elif check_four(nums):
        return 2
    elif check_hulu(nums):
        return 3
    elif tonghua_checked:
        return 4
    elif shunzi_checked:
        return 5
    elif check_three(nums):
        return 6
    else:
        return 7


if __name__ == '__main__':
    pokers = [["4", "H"],
              ["5", "S"],
              ["6", "C"],
              ["7", "D"],
              ["8", "D"]]
    assert solve_method(pokers) == 5

    pokers = [["9", "S"],
              ["5", "S"],
              ["6", "S"],
              ["7", "S"],
              ["8", "S"]]
    assert solve_method(pokers) == 1
```

