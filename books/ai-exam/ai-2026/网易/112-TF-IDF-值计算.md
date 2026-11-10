# TF-IDF 值计算

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/netease/algo-20260919/ · 网易 · 2026-09-19 · 算法岗

## 题目描述

某电商平台计划借助大语言模型改善用户的购物体验，在训练模型之前，先用传统机器学习中的 TF-IDF 方法对训练数据做一次摸底分析。TF-IDF 是信息检索与文本挖掘中常用的加权技术。
其中词频 TF 表示为「词 $w$ 在某条语句中出现的次数」除以「该语句中的总词数」；逆文档频率 IDF 表示为
其中 $N$ 是语料库中语句的总数，$N_{w}$ 是语料库中包含单词 $w$ 的语句总数。TF-IDF 表示为 TF 与 IDF 的乘积。
注意：$\log$ 为自然对数，单词按空格切分且区分大小写。

## 输入描述

输入是两个 list，各占一行，均为 Python 列表字面量，可以用 eval 函数还原。第一个 list 中的每个元素表示一条训练语句，每条语句里的词用空格隔开；第二个 list 长度为 $2$，第一个元素表示某条训练语句在第一个 list 中的索引，第二个元素表示该语句中的某个词汇。
语句总数 $N$ 满足 $1 \le N \le 100$，每条语句包含 $1$ 到 $20$ 个单词，每个单词由 $1$ 到 $10$ 个英文字母组成；给定的索引合法，给定的词汇一定出现在该语句中。

## 输出描述

给出在给定语句和给定 Word 下该 Word 的 TF-IDF 值，结果为 float，保留小数点后 3 位（与 round 函数的格式一致）。

## 样例 1

输入
输出
样例解释 ：第 1 条语句中 Apple 的 TF-IDF 值为 $0.424$。

```text
['An Apple orange Apple','Chinese is an banana','Chinese KongFu','Apple is not pen']
[0, 'Apple']
0.424
```

## 思路分析

第一步：先看清两个计数口径。 题面把 TF 和 IDF 的公式都给了，剩下的事情只有一件事——分清分子分母统计的是什么。TF 的分子是「词 $w$ 在某一条语句内出现的次数」，分母是「这条语句的词数」；IDF 里的 $N_{w}$ 是「含 $w$ 的语句条数」，不是全语料里 $w$ 的出现总次数。两处都属于计数，但一个数词、一个数句，一旦混用就会算错。
第二步：切词并严格区分大小写。 每条语句按空格切成词列表，比较时逐词精确匹配。样例里第 1 句同时出现了 An 和 an ，题面明确说明区分大小写，所以这两个是不同的词，不能顺手做 lower() 归一。
第三步：算 TF。 设给定索引为 $k$、给定词为 $w$，目标语句是 $d_k$，则
其中 $\operatorname{count}(w, d_k)$ 是 $w$ 在 $d_k$ 中的出现次数，$\lvert d_k\rvert$ 是 $d_k$ 的词数。如果 $w$ 在目标句里出现了两次，分子就是 $2$。
第四步：算 IDF，注意去重。 $N_{w}$ 统计语句条数，同一句里出现多次也只记一次，所以每条语句先转成集合再判断成员：
分母上的 $+1$ 是对 $N_{w}$ 做平滑；外层再 $+1$，保证对数的真数始终大于 $1$，即使 $N_{w}+1>N$ 时 IDF 也为正，不会出现负权重。若把全语料的出现总次数当作 $N_{w}$，一句里重复出现的词会被多算，IDF 随之偏小。
第五步：乘起来并按格式输出。 两者相乘后取 3 位小数，直接打印浮点数即可，末尾的 $0$ 会被省略，例如 $0.5$ 不会写成 $0.500$。
手动模拟样例 ：语料共 $N=4$ 条语句； Apple 出现在第 1 条和第 4 条语句中，所以 $N_{w}=2$；目标语句是第 1 条，词数为 $4$， Apple 在其中出现 $2$ 次，于是 $TF=2/4=0.5$，$IDF=\ln(4/3+1)=\ln(7/3)\approx0.8473$，乘积约为 $0.4237$，保留 3 位小数得 $0.424$，与样例一致。

## 题解代码

### Python 实现

```python
import ast
import math
import sys

input = sys.stdin.readline


# 统计包含 word 的语句条数，同一句里出现多次只算一次
def count_docs(docs, word):
    count = 0
    for words in docs:
        # 先转集合再判断成员，一句里出现几次都只记 1
        if word in set(words):
            count += 1
    return count


# 计算 word 在第 idx 条语句中的 TF-IDF 值
def tf_idf(sentences, idx, word):
    # 按空格切词，比较时区分大小写，apple 与 Apple 是两个词
    docs = [sentence.split() for sentence in sentences]
    n = len(docs)

    # TF：目标句中该词的出现次数 / 目标句的词数
    target = docs[idx]
    tf = target.count(word) / len(target)

    # IDF：分母 +1 做平滑，外层再 +1 保证对数的真数大于 1、结果为正
    nw = count_docs(docs, word)
    idf = math.log(n / (nw + 1) + 1)
    return tf * idf


def solve():
    # 两行输入都是 Python 列表字面量，用 literal_eval 安全还原
    sentences = ast.literal_eval(input())
    query = ast.literal_eval(input())
    idx, word = int(query[0]), query[1]
    # 输出与 round(x, 3) 的格式一致，例如 0.424、0.5
    print(round(tf_idf(sentences, idx, word), 3))


if __name__ == "__main__":
    solve()
```

## 复杂度分析

时间复杂度 ：$O(L)$，其中 $L$ 是全部语句的总词数。瓶颈是切词与逐句建集合，每个词只被处理常数次；统计 $N_{w}$ 必须看遍所有语句，不可能更快。
空间复杂度 ：$O(L)$，存放切分后的词列表与用于判重的集合。

## 易错点

TF 的分子是目标句内的出现次数，IDF 的 $N_{w}$ 是含该词的语句条数，两个口径不能混用。 切词后必须区分大小写， An 与 an 是两个词。 输出用 round(x, 3) 的格式，末尾的 $0$ 会被省略；手工格式化成固定三位小数反而与样例不符。
