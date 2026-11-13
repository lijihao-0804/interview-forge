#!/usr/bin/env python3
"""Generate independently verified supplemental cases for ACM partition B.

The expected values in the generated JSON are produced by the small solvers
below.  Those solvers use brute force, elementary formulas, or direct semantic
simulations based on the Markdown statements.  Existing reference solutions are
deliberately not imported or executed here.
"""

from __future__ import annotations

import functools
import heapq
import itertools
import json
import math
import sys
from collections import Counter, deque
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "ai_exam" / "practice-cases-b.json"
MOD = 1_000_000_007


def ncase(
    input_text: str,
    expected: str,
    name: str,
    kind: str,
    verification: str,
) -> dict[str, str]:
    if kind not in {"boundary", "typical", "adversarial"}:
        raise ValueError(f"invalid kind: {kind}")
    return {
        "input": input_text.strip("\n"),
        "expected": expected.strip("\n"),
        "name": name,
        "kind": kind,
        "source": "supplemental",
        "verification": verification,
    }


def generated_case(
    input_text: str,
    solver: Callable[[str], str],
    name: str,
    kind: str,
    verification: str,
) -> dict[str, str]:
    return ncase(input_text, solver(input_text), name, kind, verification)


def fixed2(value: float) -> str:
    if abs(value) < 0.005:
        return "0.00"
    rounded = Decimal.from_float(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(rounded, ".2f")


# ---------------------------------------------------------------------------
# 050 Masked Fused RMSNorm


def solve_050(text: str) -> str:
    lines = text.splitlines()
    m, n, epsilon = lines[0].split()
    m, n, epsilon = int(m), int(n), float(epsilon)
    gamma = list(map(float, lines[1].split()))
    beta = list(map(float, lines[2].split()))
    out: list[str] = []
    for row in lines[3 : 3 + m]:
        tokens = row.split()
        length, alpha = int(tokens[0]), float(tokens[1])
        xs = list(map(float, tokens[2 : 2 + n]))
        rs = list(map(float, tokens[2 + n : 2 + 2 * n]))
        fused = [xs[i] + alpha * rs[i] for i in range(length)]
        energy = sum(v * v for v in fused)
        rms = math.sqrt(energy / max(length, 1) + epsilon)
        if length and rms == 0.0:
            raise ValueError("undefined RMSNorm case")
        values = [gamma[i] * fused[i] / rms + beta[i] for i in range(length)]
        values.extend([0.0] * (n - length))
        out.append(
            " ".join(map(fixed2, values)) + " | " + fixed2(rms) + " | " + fixed2(energy)
        )
    return "\n".join(out)


def cases_050() -> list[dict[str, str]]:
    verify = "独立按题意逐项计算融合值、能量和 RMS；期望由 solve_050 直接生成。"
    return [
        generated_case("1 2 0\n1 1\n7 8\n0 0 0 0 0 0", solve_050, "全 padding 且 eps 为零", "boundary", verify),
        generated_case("1 3 0\n1 1 1\n0 0 0\n1 2 2 0 0 0 0 0", solve_050, "单有效位零稳定项", "boundary", verify),
        generated_case("1 3 0.5\n1 2 -1\n0 1 5\n2 2 3 -4 0 -2 2 99", solve_050, "负残差与部分 padding", "adversarial", verify),
        generated_case("2 2 1\n2 1\n1 -1\n2 -1 1 1 -1 1\n1 1000 1 1 0 0", solve_050, "多样本及正负残差", "typical", verify),
        generated_case("1 4 0.0001\n3 2 1 -2\n0 1 -1 2\n3 0.5 1 2 3 4 4 3 2 1", solve_050, "大残差系数和共享位置参数", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 051 X-Means (only K=1 legal cases with a forced, unique clustered result)


def solve_051_k1(text: str) -> str:
    lines = text.splitlines()
    n, d = map(int, lines[0].split())
    points = [[Fraction(token) for token in lines[i].split()] for i in range(1, n + 1)]
    kmin, kmax = map(int, lines[n + 1].split())
    if (kmin, kmax) != (1, 1):
        raise ValueError("case generator only accepts K_min=K_max=1")
    center = [sum(row[j] for row in points) / n for j in range(d)]

    def fmt(value: Fraction) -> str:
        rounded = Decimal(value.numerator) / Decimal(value.denominator)
        rounded = rounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return "0.00" if rounded == 0 else format(rounded, ".2f")

    return "1\n" + " ".join(map(fmt, center)) + "\n" + " ".join(["0"] * n)


def cases_051() -> list[dict[str, str]]:
    verify = "K_min=K_max=1 时唯一中心必为全部点的均值；用 Fraction 精确求均值并自主舍入。"
    return [
        generated_case("1 1\n5.0\n1 1", solve_051_k1, "单个点单簇", "boundary", verify),
        generated_case("2 1\n0\n3\n1 1", solve_051_k1, "两个点单簇", "typical", verify),
        generated_case("3 2\n1 0\n1 2\n1 4\n1 1", solve_051_k1, "第一维并列的单簇", "adversarial", verify),
        generated_case("4 2\n-2 3\n1 -1\n4 0\n5 -4\n1 1", solve_051_k1, "负坐标单簇", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 052 ID3-style three-feature decision tree


def _entropy_from_counts(counts: Iterable[int]) -> float:
    values = list(counts)
    total = sum(values)
    return -sum((v / total) * math.log2(v / total) for v in values if v)


def _build_tree_052(rows: list[tuple[int, int, int, int]], available: tuple[int, ...]) -> object:
    total = len(rows)
    positives = sum(r[3] == 1 for r in rows)
    majority = int(positives > total - positives)
    if positives in (0, total) or not available:
        return majority
    base = _entropy_from_counts([total - positives, positives])
    best_feature = -1
    best_gain = -math.inf
    for feature in available:
        left = [r for r in rows if r[feature] == 0]
        right = [r for r in rows if r[feature] == 1]
        conditional = 0.0
        for part in (left, right):
            if part:
                p = sum(r[3] == 1 for r in part)
                conditional += len(part) / total * _entropy_from_counts([len(part) - p, p])
        gain = base - conditional
        if gain > best_gain + 1e-9:
            best_gain = gain
            best_feature = feature
    if best_gain <= 1e-9:
        return majority
    remain = tuple(f for f in available if f != best_feature)
    return (
        best_feature,
        _build_tree_052([r for r in rows if r[best_feature] == 0], remain),
        _build_tree_052([r for r in rows if r[best_feature] == 1], remain),
    )


def solve_052(text: str) -> str:
    lines = text.splitlines()
    n, m = map(int, lines[0].split())
    rows = [tuple(map(int, line.split())) for line in lines[1 : n + 1]]
    queries = [tuple(map(int, line.split())) for line in lines[n + 1 : n + 1 + m]]
    tree = _build_tree_052(rows, (0, 1, 2))
    answers: list[str] = []
    for query in queries:
        node = tree
        while isinstance(node, tuple):
            feature, left, right = node
            node = right if query[feature] else left
        answers.append(str(node))
    return "\n".join(answers)


def cases_052() -> list[dict[str, str]]:
    verify = "独立按信息增益定义建树，并用元组树逐项预测；不调用参考实现。"
    return [
        generated_case("2 3\n0 0 0 1\n1 1 1 1\n0 0 0\n1 0 1\n1 1 1", solve_052, "纯类叶子", "boundary", verify),
        generated_case("4 4\n0 0 1 0\n0 0 0 0\n1 1 0 1\n1 1 1 1\n0 1 1\n0 0 1\n1 0 0\n1 1 0", solve_052, "特征零为根且可完全分开", "typical", verify),
        generated_case("4 4\n0 0 1 0\n0 1 1 0\n1 0 0 1\n1 1 0 1\n0 0 1\n0 1 0\n1 0 1\n1 1 1", solve_052, "增益并列选小编号", "adversarial", verify),
        generated_case("4 4\n0 0 0 0\n0 1 1 1\n1 0 1 1\n1 1 0 0\n0 0 0\n0 1 0\n1 0 1\n1 1 1", solve_052, "三特征零增益时停为多数类", "adversarial", verify),
        generated_case("5 3\n0 0 0 0\n1 0 0 0\n0 1 0 1\n1 1 0 1\n0 0 1 1\n0 0 0\n1 0 1\n0 1 1", solve_052, "重复样本参与信息增益和多数表决", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 053 Naive Bayes self-training


def _decode_053(text: str, emit: dict[str, Counter[str]], prior: Counter[str], alpha: int) -> str:
    out: list[str] = []
    for observed in text:
        best: tuple[int, int, str] | None = None
        for truth in "abcdefghijklmnopqrstuvwxyz":
            numerator = (emit[truth][observed] + alpha) * (prior[truth] + alpha)
            denominator = sum(emit[truth].values()) + alpha * 26
            if best is None:
                best = (numerator, denominator, truth)
                continue
            bn, bd, bc = best
            lhs, rhs = numerator * bd, bn * denominator
            if lhs > rhs or (lhs == rhs and truth < bc):
                best = (numerator, denominator, truth)
        assert best is not None
        out.append(best[2])
    return "".join(out)


def _fit_nb_053(pairs: list[tuple[str, str]], alpha: int) -> tuple[dict[str, Counter[str]], Counter[str]]:
    emit = {c: Counter() for c in "abcdefghijklmnopqrstuvwxyz"}
    prior: Counter[str] = Counter()
    for observed, truth in pairs:
        if len(observed) != len(truth):
            raise ValueError("unequal training lengths")
        for o, c in zip(observed, truth):
            emit[c][o] += 1
            prior[c] += 1
    return emit, prior


def solve_053(text: str) -> str:
    lines = text.splitlines()
    n, m, t, alpha = map(int, lines[0].split())
    originals = [tuple(lines[i].split()) for i in range(1, n + 1)]
    unlabeled = lines[n + 1 : n + 1 + m]
    test = lines[n + 1 + m]
    emit, prior = _fit_nb_053(originals, alpha)
    for _ in range(t):
        pseudo = [_decode_053(sample, emit, prior, alpha) for sample in unlabeled]
        pairs = originals + list(zip(unlabeled, pseudo))
        emit, prior = _fit_nb_053(pairs, alpha)
    return _decode_053(test, emit, prior, alpha)


def cases_053() -> list[dict[str, str]]:
    verify = "独立实现整数交叉相乘的朴素贝叶斯，每轮重建计数并逐字符解码。"
    return [
        generated_case("1 0 0 1\nq q\nq", solve_053, "零轮自训练的已知映射", "boundary", verify),
        generated_case("1 0 0 2\nx a\nx", solve_053, "无观测时的平滑并列取字典序最小", "adversarial", verify),
        generated_case("1 2 1 1\nab ax\naz\naz\naz", solve_053, "一轮伪标注更新发射计数", "typical", verify),
        generated_case("2 1 3 2\nab ab\nbz ba\nabz\nabz", solve_053, "多轮替换伪标签而非累计", "adversarial", verify),
        generated_case("2 2 2 1\nax ab\nyy yy\naa\nyz\nay", solve_053, "不等长训练对与多个未标注串", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 054 KV Cache block allocation


def solve_054(text: str) -> str:
    lines = text.splitlines()
    m, k, n = map(int, lines[0].split())
    lengths = list(map(int, lines[1].split()))
    if len(lengths) != n:
        raise ValueError("wrong request count")
    blocks = [(length + k - 1) // k for length in lengths]
    best = 0
    for mask in range(1 << n):
        chosen = [blocks[i] for i in range(n) if mask >> i & 1]
        if sum(chosen) <= m:
            best = max(best, len(chosen))
    return str(best)


def cases_054() -> list[dict[str, str]]:
    verify = "枚举至多 8 个请求的全部接受子集，直接检查 Block 总量和数量。"
    return [
        generated_case("1 1 1\n1", solve_054, "单请求恰好占满", "boundary", verify),
        generated_case("2 4 3\n4 5 8", solve_054, "所有非空请求都超容量", "adversarial", verify),
        generated_case("5 3 5\n1 3 4 6 9", solve_054, "等 Block 需求和容量边界", "typical", verify),
        generated_case("4 2 4\n1 2 3 8", solve_054, "大请求必须被放弃", "adversarial", verify),
        generated_case("10 7 6\n7 8 14 21 22 70", solve_054, "一般容量与撤销收益", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 055 General discrete-feature information-gain tree


def _entropy_labels_055(labels: Iterable[int]) -> float:
    counts = Counter(labels)
    total = sum(counts.values())
    return -sum((v / total) * math.log2(v / total) for v in counts.values() if v)


def _majority_055(rows: list[tuple[int, ...]], feature_count: int) -> int:
    counts = Counter(row[-1] for row in rows)
    top = max(counts.values())
    return min(label for label, count in counts.items() if count == top)


def _build_tree_055(
    rows: list[tuple[int, ...]], feature_count: int, available: tuple[int, ...]
) -> object:
    labels = [row[-1] for row in rows]
    majority = _majority_055(rows, feature_count)
    if len(set(labels)) == 1 or not available:
        return majority
    base = _entropy_labels_055(labels)
    best_feature = -1
    best_gain = -math.inf
    for feature in available:
        groups: dict[int, list[int]] = {}
        for row in rows:
            groups.setdefault(row[feature], []).append(row[-1])
        conditional = sum(len(part) / len(rows) * _entropy_labels_055(part) for part in groups.values())
        gain = base - conditional
        if gain > best_gain + 1e-9:
            best_gain, best_feature = gain, feature
    if best_gain <= 1e-9:
        return majority
    remain = tuple(f for f in available if f != best_feature)
    branches: dict[int, object] = {}
    for value in sorted({row[best_feature] for row in rows}):
        part = [row for row in rows if row[best_feature] == value]
        branches[value] = _build_tree_055(part, feature_count, remain)
    return best_feature, branches, majority


def solve_055(text: str) -> str:
    data = iter(text.split())
    m = int(next(data))
    n = int(next(data))
    rows = [tuple(int(next(data)) for _ in range(m + 1)) for _ in range(n)]
    q = int(next(data))
    queries = [tuple(int(next(data)) for _ in range(m)) for _ in range(q)]
    tree = _build_tree_055(rows, m, tuple(range(m)))
    answers: list[str] = []
    for query in queries:
        node = tree
        while isinstance(node, tuple):
            feature, branches, fallback = node
            node = branches.get(query[feature], fallback)
        answers.append(str(node))
    return "\n".join(answers)


def cases_055() -> list[dict[str, str]]:
    verify = "独立按多取值信息增益递归建树；测试仅使用已见特征值，并避开未定义平票。"
    return [
        generated_case("2\n3\n0 0 0\n0 1 1\n1 0 1\n3\n0 0\n0 1\n1 1", solve_055, "两特征完全分开", "typical", verify),
        generated_case("2\n4\n0 0 5\n0 1 5\n1 0 8\n1 1 9\n2\n0 0\n1 1", solve_055, "多类别叶子", "typical", verify),
        generated_case("3\n4\n0 0 0 0\n0 1 1 0\n1 0 1 1\n1 1 0 1\n3\n0 0 0\n0 1 0\n1 0 1", solve_055, "增益并列时选索引较小特征", "adversarial", verify),
        generated_case("2\n5\n0 0 0\n0 0 0\n1 2 1\n2 1 1\n1 1 0\n3\n0 0\n1 2\n2 1", solve_055, "多取值和重复行", "typical", verify),
        generated_case("2\n4\n0 0 0\n1 0 0\n0 1 0\n1 1 1\n3\n0 0\n0 1\n1 1", solve_055, "无增益时退化为多数类", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 056 Pipeline partition


def solve_056(text: str) -> str:
    lines = text.splitlines()
    t = list(map(int, lines[0].split()))
    s = list(map(int, lines[1].split()))
    k = int(lines[2])
    n = len(t)
    if len(s) != n or not 1 <= k <= n:
        raise ValueError("invalid pipeline input")
    best = math.inf
    for cuts in itertools.combinations(range(1, n), k - 1):
        ends = list(cuts) + [n]
        begin = 0
        worst = 0
        for end in ends:
            stage = sum(t[begin:end]) + (s[end - 1] if end < n else 0)
            worst = max(worst, stage)
            begin = end
        best = min(best, worst)
    return str(best)


def cases_056() -> list[dict[str, str]]:
    verify = "枚举全部恰好 K 段的切分并直接取最大阶段耗时的最小值。"
    return [
        generated_case("7\n99\n1", solve_056, "单层单卡忽略末层通信", "boundary", verify),
        generated_case("4 9\n2 30\n2", solve_056, "两层两卡只有首层通信", "boundary", verify),
        generated_case("2 2 2 2\n1 100 1 1\n2", solve_056, "反向输入通信影响切分", "adversarial", verify),
        generated_case("1 2 3 4 5\n5 4 3 2 100\n1", solve_056, "必须全放一张卡", "typical", verify),
        generated_case("8 1 7 2 6\n3 3 2 8 9\n3", solve_056, "一般三阶段平衡", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 057 Delivery waiting time


def solve_057(text: str) -> str:
    data = iter(map(int, text.split()))
    groups = next(data)
    answers: list[str] = []
    for _ in range(groups):
        n, m = next(data), next(data)
        distances = [next(data) for _ in range(n)]
        answers.append(" ".join(str(max(0, d - m)) for d in distances))
    return "\n".join(answers)


def cases_057() -> list[dict[str, str]]:
    verify = "逐位置应用 max(0, d_i-m)，并独立处理多测试组。"
    return [
        generated_case("1\n1 0\n0", solve_057, "宿舍楼最小输入", "boundary", verify),
        generated_case("1\n3 10\n1 10 0", solve_057, "用户晚于外卖到达", "boundary", verify),
        generated_case("2\n2 5\n4 0\n4 0\n10 3 8 0", solve_057, "多组混合", "typical", verify),
        generated_case("1\n5 4\n4 5 1 8 0", solve_057, "非单调距离", "adversarial", verify),
        generated_case("1\n4 1000000000\n1000000000 999999999 1 0", solve_057, "大数边界", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 058 Strings without four equal consecutive letters


def solve_058(text: str) -> str:
    data = list(map(int, text.split()))
    total_cases = data[0]
    ns = data[1 : 1 + total_cases]
    answers = [str((26**n - 26) % MOD if n == 4 else None) for n in ns]
    limit = max(ns)
    # run1[v] counts valid strings whose last run has length v.
    run1, run2, run3 = 26, 0, 0
    by_length = {1: 26}
    for length in range(2, limit + 1):
        total = (run1 + run2 + run3) % MOD
        run1, run2, run3 = 25 * total % MOD, run1, run2
        by_length[length] = (run1 + run2 + run3) % MOD
    return "\n".join(str(by_length[n]) for n in ns)


def cases_058() -> list[dict[str, str]]:
    verify = "独立用末尾连续相同字符长度 1/2/3 的状态转移计数。"
    return [
        generated_case("1\n1", solve_058, "最小长度", "boundary", verify),
        generated_case("4\n2\n3\n4\n5", solve_058, "首次排除四连字符", "boundary", verify),
        generated_case("3\n6\n7\n10", solve_058, "较长重复边界", "typical", verify),
        generated_case("2\n25\n50", solve_058, "中等长度模运算", "typical", verify),
        generated_case("1\n200", solve_058, "大长度递推", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 059 CLIP contrastive loss


def solve_059(text: str) -> str:
    data = json.loads(text)
    images = data["image_embeds"]
    texts = data["text_embeds"]
    tau = float(data["temperature"])
    n = len(images)
    scores = [[sum(a * b for a, b in zip(images[i], texts[j])) / tau for j in range(n)] for i in range(n)]

    def cross_entropy(row: list[float], target: int) -> float:
        high = max(row)
        exp_row = [math.exp(v - high) for v in row]
        denom = sum(exp_row)
        return -(row[target] - high - math.log(denom))

    image_loss = sum(cross_entropy(scores[i], i) for i in range(n)) / n
    text_loss = sum(cross_entropy([scores[i][j] for i in range(n)], j) for j in range(n)) / n
    return f"{(image_loss + text_loss) / 2:.6f}"


def cases_059() -> list[dict[str, str]]:
    verify = "用标准库 math 独立计算相似度矩阵、稳定 softmax 两方向交叉熵和平均值。"
    return [
        generated_case('{"image_embeds": [[1.0]], "text_embeds": [[1.0]], "temperature": 0.5}', solve_059, "单样本损失为零", "boundary", verify),
        generated_case('{"image_embeds": [[1,0],[0,1]], "text_embeds": [[1,0],[0,1]], "temperature": 1.0}', solve_059, "二维正交嵌入", "typical", verify),
        generated_case('{"image_embeds": [[1,0],[1,0]], "text_embeds": [[1,0],[1,0]], "temperature": 1.0}', solve_059, "完全相同嵌入的最大混淆", "adversarial", verify),
        generated_case('{"image_embeds": [[0.6,0.8],[0.8,-0.6],[1,0]], "text_embeds": [[0.6,0.8],[1,0],[0.8,-0.6]], "temperature": 0.25}', solve_059, "三维非恒等匹配", "typical", verify),
        generated_case('{"image_embeds": [[1,0],[0,1],[0.6,0.8]], "text_embeds": [[1,0],[0.6,0.8],[0,1]], "temperature": 2.0}', solve_059, "高温缩放", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 060 Functional graph minimum board cost


def solve_060(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    costs = [0] + list(map(int, lines[1].split()))
    edges = [0] + list(map(int, lines[2].split()))
    best = math.inf
    for mask in range(1 << n):
        total = sum(costs[i] for i in range(1, n + 1) if mask >> (i - 1) & 1)
        if total >= best:
            continue
        valid = True
        for start in range(1, n + 1):
            seen: set[int] = set()
            cur = start
            while cur not in seen:
                seen.add(cur)
                if mask >> (cur - 1) & 1:
                    break
                cur = edges[cur]
            else:
                valid = False
                break
        if valid:
            best = total
    return str(best)


def cases_060() -> list[dict[str, str]]:
    verify = "枚举放板房间集合，逐个起点沿函数图行走并检查是否经过粘蝇板。"
    return [
        generated_case("1\n9\n1", solve_060, "单自环", "boundary", verify),
        generated_case("2\n7 3\n2 2", solve_060, "单二环", "boundary", verify),
        generated_case("5\n8 2 6 3 9\n2 3 2 5 4", solve_060, "两个独立环与树枝", "typical", verify),
        generated_case("4\n5 1 1 4\n1 2 3 3", solve_060, "并列最低代价", "adversarial", verify),
        generated_case("6\n10 20 3 30 4 5\n2 3 1 5 6 4", solve_060, "长链汇入多个环", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 061 Guard removal game


def solve_061(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    watch = [[] for _ in range(n + 1)]
    for line in lines[1 : n + 1]:
        parts = list(map(int, line.split()))
        node, count = parts[0], parts[1]
        watch[node] = [v for v in parts[2 : 2 + count] if 1 <= v <= n and v != node]

    @functools.lru_cache(maxsize=None)
    def best_remaining(mask: int) -> int:
        alive = [i for i in range(1, n + 1) if mask >> (i - 1) & 1]
        if not alive:
            return 0
        monitored = {
            i: {j for j in alive if i in watch[j]} for i in alive
        }
        choices: list[tuple[int, ...]] = []
        for i in alive:
            if not monitored[i]:
                choices.append((i,))
        for a, b in itertools.combinations(alive, 2):
            if monitored[a] == {b} and monitored[b] == {a}:
                choices.append((a, b))
        if not choices:
            return len(alive)
        result = len(alive)
        for killed in choices:
            new_mask = mask
            for node in killed:
                new_mask &= ~(1 << (node - 1))
            result = min(result, best_remaining(new_mask))
        return result

    remaining = best_remaining((1 << n) - 1)
    return "SUCCESS" if remaining == 0 else str(remaining)


def cases_061() -> list[dict[str, str]]:
    verify = "位掩码穷举所有合法单杀/双杀顺序并取最小剩余人数。"
    return [
        generated_case("1\n1 0", solve_061, "无人监视可单杀", "boundary", verify),
        generated_case("2\n1 1 2\n2 1 1", solve_061, "互为唯一监视的双杀", "typical", verify),
        generated_case("3\n1 1 2\n2 1 3\n3 1 1", solve_061, "三节点不能双杀的环", "adversarial", verify),
        generated_case("4\n1 0\n2 1 1\n3 1 2\n4 1 3", solve_061, "链式单杀剥离", "typical", verify),
        generated_case("5\n1 0\n2 1 3\n3 1 2\n4 1 5\n5 1 4", solve_061, "自由守卫加一个二环", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 062 Diagonal matrix traversal


def solve_062(text: str) -> str:
    data = iter(map(int, text.split()))
    rows, cols = next(data), next(data)
    matrix = [[next(data) for _ in range(cols)] for _ in range(rows)]
    result: list[int] = []
    for group in range(rows + cols - 1):
        difference = (rows - 1) - group
        low = max(0, difference)
        high = min(rows - 1, cols - 1 + difference)
        order = range(high, low - 1, -1) if group % 2 == 0 else range(low, high + 1)
        result.extend(matrix[row][row - difference] for row in order)
    return " ".join(map(str, result))


def cases_062() -> list[dict[str, str]]:
    verify = "按左下到右上的对角线逐条枚举，并按轮次交替上下方向。"
    return [
        generated_case("1 1\n5", solve_062, "单格矩阵", "boundary", verify),
        generated_case("1 4\n1 2 3 4", solve_062, "单行矩阵", "boundary", verify),
        generated_case("4 1\n1\n2\n3\n4", solve_062, "单列矩阵", "boundary", verify),
        generated_case("2 3\n1 2 3\n4 5 6", solve_062, "非方阵", "typical", verify),
        generated_case("3 3\n9 8 7\n6 5 4\n3 2 1", solve_062, "逆序方阵", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 063 Weighted interval scheduling


def solve_063(text: str) -> str:
    data = list(map(int, text.split()))
    n = data[0]
    tasks = [tuple(data[i : i + 3]) for i in range(1, 1 + 3 * n, 3)]
    best = 0
    for mask in range(1 << n):
        chosen = [tasks[i] for i in range(n) if mask >> i & 1]
        if all(a[1] <= b[0] or b[1] <= a[0] for a, b in itertools.combinations(chosen, 2)):
            best = max(best, sum(v for _, _, v in chosen))
    return str(best)


def cases_063() -> list[dict[str, str]]:
    verify = "枚举任务子集，按半开区间冲突定义逐一检查并取最大收益。"
    return [
        generated_case("1\n0 1 7", solve_063, "单任务", "boundary", verify),
        generated_case("3\n1 4 10\n4 7 20\n7 8 5", solve_063, "首尾相接可同时选择", "boundary", verify),
        generated_case("3\n1 10 100\n2 3 30\n4 5 40", solve_063, "等价加权取舍", "typical", verify),
        generated_case("5\n5 9 8\n0 2 3\n2 5 4\n9 10 100\n6 8 7", solve_063, "乱序输入", "adversarial", verify),
        generated_case("4\n1 5 1\n2 6 1\n3 7 1\n4 8 1", solve_063, "全部互相重叠", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 064 XOR-zero triangle triples


def solve_064(text: str) -> str:
    n = int(text)
    count = 0
    for a in range(1, n + 1):
        for b in range(a, n + 1):
            for c in range(b, n + 1):
                if a ^ b ^ c == 0 and a + b > c:
                    count += 1
    return str(count)


def cases_064() -> list[dict[str, str]]:
    verify = "直接枚举满足 a<=b<=c 的全部三元组，独立检查异或和严格三角不等式。"
    return [
        generated_case("1", solve_064, "最小 n", "boundary", verify),
        generated_case("2", solve_064, "仅含一和二", "boundary", verify),
        generated_case("6", solve_064, "首个合法三元组", "typical", verify),
        generated_case("10", solve_064, "重复边组合", "adversarial", verify),
        generated_case("20", solve_064, "较大穷举", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 065 Increasing-index and increasing-weight edge paths


def solve_065(text: str) -> str:
    data = list(map(int, text.split()))
    n, m = data[0], data[1]
    edges = [tuple(data[i : i + 3]) for i in range(2, 2 + 3 * m, 3)]

    @functools.lru_cache(maxsize=None)
    def extend(end: int, last_weight: int, next_index: int) -> int:
        best = 0
        for j in range(next_index, m):
            a, b, w = edges[j]
            if a == end and w > last_weight:
                best = max(best, 1 + extend(b, w, j + 1))
        return best

    answer = 0
    for i, (a, b, w) in enumerate(edges):
        answer = max(answer, 1 + extend(b, w, i + 1))
    return str(answer)


def cases_065() -> list[dict[str, str]]:
    verify = "从每条边起 DFS 枚举输入编号更大的可接边，同时要求权值严格上升。"
    return [
        generated_case("1 1\n1 1 0", solve_065, "单个自环", "boundary", verify),
        generated_case("2 2\n1 2 1\n2 1 2", solve_065, "两段后继路径", "typical", verify),
        generated_case("2 3\n1 2 5\n1 2 5\n1 2 6", solve_065, "重边与等权不可接", "adversarial", verify),
        generated_case("3 4\n1 2 3\n2 3 1\n3 1 2\n1 3 9", solve_065, "权值逆序阻挡", "adversarial", verify),
        generated_case("4 5\n1 2 1\n2 3 2\n1 4 1\n4 3 3\n3 1 4", solve_065, "两条候选支路", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 066 Queue versus stack output feasibility


def _stack_possible_066(source: str, target: str) -> bool:
    stack: list[str] = []
    i = 0
    for ch in target:
        while i < len(source) and (not stack or stack[-1] != ch):
            stack.append(source[i])
            i += 1
        if not stack or stack[-1] != ch:
            return False
        stack.pop()
    return i == len(source) and not stack


def solve_066(text: str) -> str:
    source, target = text.splitlines()[:2]
    queue_ok = source == target
    stack_ok = _stack_possible_066(source, target)
    if queue_ok and stack_ok:
        return "both"
    if queue_ok:
        return "queue"
    if stack_ok:
        return "stack"
    return "neither"


def cases_066() -> list[dict[str, str]]:
    verify = "队列直接比较字符串；栈用双指针边压入边匹配目标串。"
    return [
        generated_case("a\na", solve_066, "单字符两种模式均可", "boundary", verify),
        generated_case("abc\nabc", solve_066, "原顺序队列与栈均可", "typical", verify),
        generated_case("abcd\ndcba", solve_066, "完整逆序仅栈可行", "typical", verify),
        generated_case("abcd\ncdab", solve_066, "相同字符多重集但栈不可行", "adversarial", verify),
        generated_case("aabb\nbbaa", solve_066, "重复字符的栈逆序", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 067 Signed sum/difference equation rank


def solve_067(text: str) -> str:
    lines = text.splitlines()
    p, e = map(int, lines[0].split())
    matrix: list[list[Fraction]] = []
    for line in lines[1 : 1 + e]:
        kind, u, v, w = line.split()
        u, v, w = int(u) - 1, int(v) - 1, Fraction(int(w))
        row = [Fraction(0) for _ in range(p + 1)]
        row[u] += 1
        row[v] += 1 if kind == "S" else -1
        row[p] = w
        matrix.append(row)

    rank = 0
    for col in range(p):
        pivot = next((r for r in range(rank, len(matrix)) if matrix[r][col]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        scale = matrix[rank][col]
        matrix[rank] = [v / scale for v in matrix[rank]]
        for r in range(len(matrix)):
            if r != rank and matrix[r][col]:
                factor = matrix[r][col]
                matrix[r] = [a - factor * b for a, b in zip(matrix[r], matrix[rank])]
        rank += 1
    if any(all(row[c] == 0 for c in range(p)) and row[p] != 0 for row in matrix):
        return "NO\n-1"
    return f"YES\n{p - rank}"


def cases_067() -> list[dict[str, str]]:
    verify = "把方程写成有理数增广矩阵，精确高斯消元求秩和一致性；自由度即最少实测值数。"
    return [
        generated_case("1 0", solve_067, "单变量无约束", "boundary", verify),
        generated_case("3 0", solve_067, "三个变量均无约束", "boundary", verify),
        generated_case("2 2\nS 1 2 9\nD 1 2 -1", solve_067, "和差方程完全确定两值", "typical", verify),
        generated_case("1 1\nS 1 1 6", solve_067, "自相加固定变量", "adversarial", verify),
        generated_case("3 3\nD 1 2 2\nS 2 3 5\nD 1 1 0", solve_067, "一条冗余自差方程", "adversarial", verify),
        generated_case("4 3\nD 1 2 1\nD 2 3 1\nS 3 4 8", solve_067, "四变量秩三", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 068 Minimum suffix flips


def solve_068(text: str) -> str:
    lines = text.splitlines()
    m = int(lines[0])
    bits = list(map(int, lines[1].split()))
    if len(bits) != m:
        raise ValueError("wrong suffix bit count")
    parity = 0
    presses = 0
    for bit in bits:
        if bit ^ parity == 0:
            presses += 1
            parity ^= 1
    return str(presses)


def cases_068() -> list[dict[str, str]]:
    verify = "从左到右维护已翻转后缀的奇偶性，当前位为 0 时必须操作。"
    return [
        generated_case("1\n0", solve_068, "单段全灭", "boundary", verify),
        generated_case("1\n1", solve_068, "单段已亮", "boundary", verify),
        generated_case("5\n0 0 0 0 0", solve_068, "全灭交替后缀翻转", "typical", verify),
        generated_case("6\n1 0 0 1 0 1", solve_068, "一般交替状态", "typical", verify),
        generated_case("8\n1 1 1 1 1 1 1 1", solve_068, "全亮无需操作", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 069 Maximize minimum guardrail height


def _feasible_069(heights: list[int], operations: int, width: int, target: int) -> bool:
    delta = [0] * (len(heights) + 1)
    coverage = 0
    used = 0
    for i, height in enumerate(heights):
        coverage += delta[i]
        deficit = target - height
        if coverage < deficit:
            add = deficit - coverage
            used += add
            if used > operations:
                return False
            coverage += add
            end = min(len(heights), i + width)
            delta[end] -= add
    return True


def solve_069(text: str) -> str:
    lines = text.splitlines()
    length, operations, width = map(int, lines[0].split())
    heights = list(map(int, lines[1].split()))
    low, high = min(heights), max(heights) + operations
    while low < high:
        mid = (low + high + 1) // 2
        if _feasible_069(heights, operations, width, mid):
            low = mid
        else:
            high = mid - 1
    return str(low)


def cases_069() -> list[dict[str, str]]:
    verify = "对候选最小高度做左到右贪心覆盖，并用差分数组精确统计区间增量，外层二分答案。"
    return [
        generated_case("1 0 1\n7", solve_069, "零次施工", "boundary", verify),
        generated_case("1 3 1\n0", solve_069, "单段全额度施工", "boundary", verify),
        generated_case("5 3 2\n1 1 1 1 1", solve_069, "短区间覆盖全部", "typical", verify),
        generated_case("5 2 5\n3 0 4 1 5", solve_069, "超长区间上限截为全长", "adversarial", verify),
        generated_case("7 5 3\n2 7 1 8 3 6 4", solve_069, "一般高低起伏", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 070 Battery-constrained shortest time


def solve_070(text: str) -> str:
    data = iter(map(int, text.split()))
    stations, edge_count, battery = next(data), next(data), next(data)
    station_cost = [next(data) for _ in range(stations)]
    graph = [[] for _ in range(stations)]
    for _ in range(edge_count):
        u, v, energy, travel = next(data) - 1, next(data) - 1, next(data), next(data)
        graph[u].append((v, energy, travel))
        graph[v].append((u, energy, travel))
    inf = 10**30
    dist = [[inf] * (battery + 1) for _ in range(stations)]
    dist[0][battery] = 0
    queue: list[tuple[int, int, int]] = [(0, 0, battery)]
    while queue:
        cost, node, energy = heapq.heappop(queue)
        if cost != dist[node][energy]:
            continue
        if node == stations - 1:
            break
        if energy < battery:
            nc = cost + station_cost[node]
            if nc < dist[node][energy + 1]:
                dist[node][energy + 1] = nc
                heapq.heappush(queue, (nc, node, energy + 1))
        for nxt, need, travel in graph[node]:
            if energy >= need and cost + travel < dist[nxt][energy - need]:
                dist[nxt][energy - need] = cost + travel
                heapq.heappush(queue, (cost + travel, nxt, energy - need))
    answer = min(dist[-1])
    return str(answer if answer < inf else -1)


def cases_070() -> list[dict[str, str]]:
    verify = "在 (节点, 电量) 状态上做 Dijkstra；充电是逐格代价，行路扣电并加时间。"
    return [
        generated_case("2 1 2\n0 0\n1 2 2 9", solve_070, "满电恰好过单边", "boundary", verify),
        generated_case("3 2 3\n5 1 9\n1 2 2 4\n2 3 2 6", solve_070, "中途廉价充电", "typical", verify),
        generated_case("2 1 2\n0 0\n1 2 3 1", solve_070, "单边耗能超过容量", "adversarial", verify),
        generated_case("3 3 4\n0 0 0\n1 2 1 10\n1 3 4 1\n3 2 1 1", solve_070, "多条路径权衡能量", "typical", verify),
        generated_case("3 2 2\n0 9 0\n1 2 1 4\n2 3 1 5", solve_070, "一般路径", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 071 Safe adjacent swaps under bounded prefix sums


def solve_071(text: str) -> str:
    data = list(map(int, text.split()))
    n, capacity, initial = data[:3]
    changes = data[3 : 3 + n]
    count = 0
    for swap in range(n - 1):
        arr = changes[:]
        arr[swap], arr[swap + 1] = arr[swap + 1], arr[swap]
        level = initial
        safe = True
        for change in arr:
            level += change
            if not 0 <= level <= capacity:
                safe = False
                break
        count += safe
    return str(count)


def cases_071() -> list[dict[str, str]]:
    verify = "对每个相邻交换独立重放完整指令串，并检查闭区间前缀和约束。"
    return [
        generated_case("1 1 0\n0", solve_071, "n=1 无权交换", "boundary", verify),
        generated_case("2 5 2\n2 -2", solve_071, "交换同值仍计数", "boundary", verify),
        generated_case("3 2 1\n1 -1 1", solve_071, "容量边界上的上下移动", "boundary", verify),
        generated_case("5 6 3\n2 -4 3 1 -2", solve_071, "一般正负指令", "typical", verify),
        generated_case("6 10 5\n-5 10 -1 0 0 0", solve_071, "零值与越界混合", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 072 Centers plus roads via a virtual hub


def solve_072(text: str) -> str:
    lines = text.splitlines()
    n, m = map(int, lines[0].split())
    center_costs = list(map(int, lines[1].split()))
    edges: list[tuple[int, int, int]] = []
    for line in lines[2 : 2 + m]:
        u, v, w = map(int, line.split())
        edges.append((u - 1, v - 1, w))
    for i, cost in enumerate(center_costs):
        edges.append((n, i, cost))
    parent = list(range(n + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    total = 0
    joined = 0
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[rv] = ru
            total += w
            joined += 1
    if joined != n:
        raise ValueError("disconnected case")
    return str(total)


def cases_072() -> list[dict[str, str]]:
    verify = "把航空互通建成虚拟节点 0，用 Kruskal 求包含至少一个中心边的最小生成树。"
    return [
        generated_case("1 0\n17", solve_072, "单城仍须建中心", "boundary", verify),
        generated_case("3 0\n9 2 5", solve_072, "无公路只能选中心", "boundary", verify),
        generated_case("3 2\n10 10 10\n1 2 1\n2 3 1", solve_072, "低成本公路优先", "typical", verify),
        generated_case("4 3\n50 50 50 1\n1 2 40\n2 3 40\n3 4 40", solve_072, "公路与跨城中心权衡", "adversarial", verify),
        generated_case("4 4\n8 7 6 5\n1 2 2\n2 3 2\n3 4 2\n4 1 2", solve_072, "环形低费公路", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 073 Longest nearly-common interval segment


def solve_073(text: str) -> str:
    data = iter(map(int, text.split()))
    n = next(data)
    intervals = [(next(data), next(data)) for _ in range(n)]
    best = 0
    for left in range(n):
        for right in range(left, n):
            indices = list(range(left, right + 1))
            choices = [None] + indices
            for skipped in choices:
                kept = [intervals[i] for i in indices if i != skipped]
                if not kept:
                    continue
                low = max(a for a, _ in kept)
                high = min(b for _, b in kept)
                if low <= high:
                    best = max(best, right - left + 1)
                    break
    return str(best)


def cases_073() -> list[dict[str, str]]:
    verify = "枚举连续段与至多一个忽略项，用区间交集下界/上界判断共同整数是否存在。"
    return [
        generated_case("1\n5 7", solve_073, "单日无需忽略", "boundary", verify),
        generated_case("3\n1 2\n10 12\n3 4", solve_073, "隔一天形成最长段", "typical", verify),
        generated_case("4\n2 2\n2 2\n2 2\n9 9", solve_073, "同点区间与唯一离群日", "boundary", verify),
        generated_case("5\n1 5\n2 4\n8 9\n3 6\n4 7", solve_073, "一般区间交集", "typical", verify),
        generated_case("4\n1 1\n3 3\n1 1\n3 3", solve_073, "交替不相交区间", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 074 Walk every road and return, with arbitrary express shortcuts


def _express_costs_074(n: int, edges: list[tuple[int, int, int]]) -> list[list[int]]:
    inf = 10**18
    cost = [[inf] * n for _ in range(n)]
    for i in range(n):
        cost[i][i] = 0
    graph = [[] for _ in range(n)]
    for u, v, weight in edges:
        graph[u].append(v)
        graph[v].append(u)
        # A route with maximum edge id t may detour across edge t whenever
        # both endpoints of that edge and both route endpoints lie in the
        # same component of the prefix graph.
        component: set[int] = set()
        queue = [u]
        while queue:
            node = queue.pop()
            if node in component:
                continue
            component.add(node)
            queue.extend(graph[node])
        for a in component:
            for b in component:
                cost[a][b] = min(cost[a][b], weight)
    return cost


def solve_074(text: str) -> str:
    data = list(map(int, text.split()))
    groups = data[0]
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n, m = data[pos], data[pos + 1]
        pos += 2
        edge_rows: list[tuple[int, int, int]] = []
        for _ in range(m):
            u, v, w = data[pos] - 1, data[pos + 1] - 1, data[pos + 2]
            pos += 3
            edge_rows.append((u, v, w))
        express = _express_costs_074(n, edge_rows)
        full = (1 << m) - 1
        inf = 10**30
        dist = [[inf] * (1 << m) for _ in range(n)]
        dist[0][0] = 0
        queue = [(0, 0, 0)]
        while queue:
            cost, node, mask = heapq.heappop(queue)
            if cost != dist[node][mask]:
                continue
            for i, (u, v, w) in enumerate(edge_rows):
                if mask >> i & 1:
                    continue
                if node == u:
                    nxt, nmask = v, mask | (1 << i)
                elif node == v:
                    nxt, nmask = u, mask | (1 << i)
                else:
                    continue
                if cost + w < dist[nxt][nmask]:
                    dist[nxt][nmask] = cost + w
                    heapq.heappush(queue, (cost + w, nxt, nmask))
            for nxt in range(n):
                if nxt != node and express[node][nxt] < inf:
                    nc = cost + express[node][nxt]
                    if nc < dist[nxt][mask]:
                        dist[nxt][mask] = nc
                        heapq.heappush(queue, (nc, nxt, mask))
        answers.append(str(dist[0][full]))
    return "\n".join(answers)


def cases_074() -> list[dict[str, str]]:
    verify = "对 (景点, 已巡检边位掩码) 做 Dijkstra；快线代价由 Floyd 求路径最大输入编号的最小值。"
    return [
        generated_case("1\n2 1\n1 2 7", solve_074, "走一条边再快线返回", "boundary", verify),
        generated_case("1\n2 2\n1 2 4\n1 2 6", solve_074, "重边分别巡检", "typical", verify),
        generated_case("1\n3 3\n1 2 5\n2 3 5\n3 1 5", solve_074, "三角形欧拉回路", "typical", verify),
        generated_case("1\n4 4\n1 2 10\n2 3 10\n3 4 10\n1 1 1", solve_074, "自环与末号快线", "adversarial", verify),
        generated_case("2\n1 0\n3 2\n1 2 3\n2 3 4", solve_074, "单点零道路及一般两组", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 075 Minimum modulo assignment


def solve_075(text: str) -> str:
    data = iter(map(int, text.split()))
    groups = next(data)
    answers: list[str] = []
    for _ in range(groups):
        n, modulus = next(data), next(data)
        a = [next(data) for _ in range(n)]
        b = [next(data) for _ in range(n)]
        best = min(
            sum((a[i] + b[perm[i]]) % modulus for i in range(n))
            for perm in itertools.permutations(range(n))
        )
        answers.append(str(best))
    return "\n".join(answers)


def cases_075() -> list[dict[str, str]]:
    verify = "枚举 B 班所有排列，按定义计算取模矛盾值总和并取最小。"
    return [
        generated_case("1\n1 7\n3\n5", solve_075, "单对唯一排列", "boundary", verify),
        generated_case("1\n2 5\n0 4\n0 1", solve_075, "零与互补余数", "boundary", verify),
        generated_case("1\n3 6\n1 2 5\n5 4 1", solve_075, "需要跨序配对", "typical", verify),
        generated_case("1\n4 10\n0 1 2 3\n5 6 7 8", solve_075, "重复最优匹配值", "typical", verify),
        generated_case("2\n2 2\n0 1\n0 1\n3 10\n9 9 9\n9 9 9", solve_075, "多组并列最值", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 076 Minimum increments for equal residues on positions modulo L


def solve_076(text: str) -> str:
    lines = text.splitlines()
    n, modulus, window = map(int, lines[0].split())
    lower = list(map(int, lines[1].split()))
    groups = [[lower[i] for i in range(j, n, window)] for j in range(window)]
    best = 10**30
    for residues in itertools.product(range(modulus), repeat=window):
        if sum(residues) % modulus:
            continue
        cost = sum((residues[j] - value) % modulus for j, group in enumerate(groups) for value in group)
        best = min(best, cost)
    return str(best)


def cases_076() -> list[dict[str, str]]:
    verify = "枚举每组公共余数，直接验证余数总和为零并累加每项最小增量。"
    return [
        generated_case("1 3 1\n2", solve_076, "单窗口必须补到模零", "boundary", verify),
        generated_case("3 2 3\n0 1 0", solve_076, "整段单组", "boundary", verify),
        generated_case("5 3 2\n2 1 0 2 1", solve_076, "两个模类", "typical", verify),
        generated_case("6 4 3\n0 0 0 0 0 0", solve_076, "已全零下界", "typical", verify),
        generated_case("7 5 4\n4 3 2 1 0 4 3", solve_076, "递减下界一般情况", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 077 Minimum adjacent-switch presses


def solve_077(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(lines[pos])
        bits = list(map(int, lines[pos + 1].split()))
        pos += 2
        previous_press = 0
        presses = 0
        for bit in bits:
            press = bit ^ previous_press
            presses += press
            previous_press = press
        answers.append(str(presses))
    return "\n".join(answers)


def cases_077() -> list[dict[str, str]]:
    verify = "从左到右唯一确定每个开关是否必须按下，并用相邻翻转奇偶性模拟。"
    return [
        generated_case("1\n1\n1", solve_077, "单灯点亮", "boundary", verify),
        generated_case("1\n1\n0", solve_077, "单灯已熄灭", "boundary", verify),
        generated_case("1\n4\n0 0 0 0", solve_077, "全暗无需按键", "boundary", verify),
        generated_case("1\n6\n1 0 1 0 1 0", solve_077, "交替状态", "typical", verify),
        generated_case("2\n3\n0 1 1\n5\n1 1 1 1 1", solve_077, "多组一般状态", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 078 Dynamic prime-coloured infinite cells


def _is_prime_078(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def solve_078(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(lines[pos])
        instructions = lines[pos + 1].strip()[:n]
        pos += 2
        flipped: set[int] = set()

        def is_black(cell: int) -> bool:
            return _is_prime_078(cell) ^ (cell in flipped)

        for person in range(1, n + 1):
            cell = 1
            for index in range(person):
                want_black = instructions[index] == "1"
                cell += 1
                while is_black(cell) != want_black:
                    cell += 1
            if cell in flipped:
                flipped.remove(cell)
            else:
                flipped.add(cell)
        changed = sorted(flipped)
        answers.append(str(len(changed)))
        answers.append(" ".join(map(str, changed)))
    return "\n".join(answers)


def cases_078() -> list[dict[str, str]]:
    verify = "小指令串上直接重走每位人员的完整路径，逐个寻找动态棋盘右侧最近目标颜色。"
    return [
        generated_case("1\n1\n0", solve_078, "第一步到最近白格", "boundary", verify),
        generated_case("1\n1\n1", solve_078, "第一步到质数格", "boundary", verify),
        generated_case("1\n2\n11", solve_078, "翻转后重新计算路径", "typical", verify),
        generated_case("1\n3\n010", solve_078, "交替颜色指令", "typical", verify),
        generated_case("2\n4\n0000\n4\n1010", solve_078, "多组长路径小样本", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 079 Shortest removal sequence for a vine prefix


def solve_079(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(lines[pos])
        values = list(map(int, lines[pos + 1].split()))
        pos += 2
        queue = deque([(n, 0)])
        seen = {n}
        found = 0
        while queue:
            length, steps = queue.popleft()
            if length == 0:
                found = steps
                break
            prefix = values[:length]
            maximum, minimum = max(prefix), min(prefix)
            next_lengths = (
                length - 1 - prefix[::-1].index(maximum),
                length - 1 - prefix[::-1].index(minimum),
            )
            for nxt in next_lengths:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, steps + 1))
        answers.append(str(found))
    return "\n".join(answers)


def cases_079() -> list[dict[str, str]]:
    verify = "BFS 枚举每次最右最大/最小前缀截断后的前缀长度，首次到 0 即最短步数。"
    return [
        generated_case("1\n1\n5", solve_079, "单段直接剪掉", "boundary", verify),
        generated_case("1\n5\n1 2 3 4 5", solve_079, "单调递增多步", "typical", verify),
        generated_case("1\n5\n5 4 3 2 1", solve_079, "单调递减", "typical", verify),
        generated_case("1\n6\n4 2 4 2 4 1", solve_079, "最大并列取最右", "adversarial", verify),
        generated_case("2\n3\n1 3 2\n4\n3 1 3 1", solve_079, "多组往返选择", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 080 Sum of circular distinct-prefix lengths


def solve_080(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n, modulus = data[pos], data[pos + 1]
        pos += 2
        values = data[pos : pos + n]
        pos += n
        total = 0
        for start in range(n):
            prefix = 0
            seen: set[int] = set()
            for step in range(n):
                prefix = (prefix + values[(start + step) % n]) % modulus
                if prefix in seen:
                    break
                seen.add(prefix)
                total += 1
        answers.append(str(total))
    return "\n".join(answers)


def cases_080() -> list[dict[str, str]]:
    verify = "对每个起点直接累加环形序列，遇到重复前缀余数即停止，并累计步数。"
    return [
        generated_case("1\n1 2\n1", solve_080, "单元素", "boundary", verify),
        generated_case("1\n3 5\n0 0 0", solve_080, "全零立即重复", "boundary", verify),
        generated_case("1\n4 7\n1 2 3 4", solve_080, "一般互异前缀", "typical", verify),
        generated_case("1\n5 6\n2 -2 2 -2 3", solve_080, "负值标准余数", "adversarial", verify),
        generated_case("2\n3 3\n1 1 1\n4 10\n5 5 5 5", solve_080, "多组重复最早停止", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 081 Maximize product after decrements


def solve_081(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n, operations = data[pos], data[pos + 1]
        pos += 2
        values = tuple(data[pos : pos + n])
        pos += n

        @functools.lru_cache(maxsize=None)
        def best(state: tuple[int, ...], left: int) -> int:
            product = math.prod(state)
            if left == 0 or all(v == 1 for v in state):
                return product
            outcomes = []
            for i, value in enumerate(state):
                if value > 1:
                    nxt = list(state)
                    nxt[i] -= 1
                    outcomes.append(best(tuple(sorted(nxt)), left - 1))
            return max(outcomes)

        answer = best(tuple(sorted(values)), operations) % MOD
        answers.append(str(answer))
    return "\n".join(answers)


def cases_081() -> list[dict[str, str]]:
    verify = "对排序后的多重集合枚举每一步可减元素，动态规划求最大余数乘积。"
    return [
        generated_case("1\n1 0\n8", solve_081, "零次操作", "boundary", verify),
        generated_case("1\n3 10\n2 3 4", solve_081, "提前停到全一", "boundary", verify),
        generated_case("1\n3 3\n2 2 3", solve_081, "多元素削平", "typical", verify),
        generated_case("1\n4 2\n5 1 3 2", solve_081, "已有一不参与操作", "typical", verify),
        generated_case("2\n2 1\n2 2\n5 4\n1 1 2 3 5", solve_081, "并列元素与混合边界", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 082 Bracket-pair disappearance rounds


def solve_082(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(lines[pos])
        string = lines[pos + 1].strip()[:n]
        pos += 2
        stack: list[int] = []
        pair_positions: list[tuple[int, int, int]] = []
        for i, ch in enumerate(string):
            if ch == "(":
                stack.append(i)
                depth = len(stack)
            else:
                depth = len(stack)
                left = stack.pop()
                pair_positions.append((left, i, depth))
        max_depth = max(depth for _, _, depth in pair_positions)
        answer = [0] * n
        for left, right, depth in pair_positions:
            round_number = max_depth - depth + 1
            answer[left] = answer[right] = round_number
        answers.append(" ".join(map(str, answer)))
    return "\n".join(answers)


def cases_082() -> list[dict[str, str]]:
    verify = "自建括号栈求每对原始深度，并用嵌套链性质得到消失轮次 max_depth-depth+1。"
    return [
        generated_case("1\n2\n()", solve_082, "单对一轮消失", "boundary", verify),
        generated_case("1\n4\n(())", solve_082, "两层嵌套", "boundary", verify),
        generated_case("1\n6\n()()()", solve_082, "三个并列浅层", "typical", verify),
        generated_case("1\n8\n(()(()))", solve_082, "不平衡分支深度", "adversarial", verify),
        generated_case("2\n6\n((()))\n10\n((())()())", solve_082, "多组深嵌套", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 083 Maximum partition value


def solve_083(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n = data[pos]
        pos += 1
        values = data[pos : pos + n]
        pos += n

        @functools.lru_cache(maxsize=None)
        def dp(left: int) -> int:
            if left == n:
                return 0
            best = -1
            low = high = values[left]
            for right in range(left, n):
                low = min(low, values[right])
                high = max(high, values[right])
                best = max(best, (high - low) * (right - left + 1) + dp(right + 1))
            return best

        answers.append(str(dp(0)))
    return "\n".join(answers)


def cases_083() -> list[dict[str, str]]:
    verify = "对每个起点枚举所有非空连续子段，记忆化穷举全部合法划分。"
    return [
        generated_case("1\n1\n9", solve_083, "单元素划分", "boundary", verify),
        generated_case("1\n4\n2 2 2 4", solve_083, "仅一处波动", "boundary", verify),
        generated_case("1\n6\n1 3 2 5 4 6", solve_083, "连续段通常更优", "typical", verify),
        generated_case("1\n5\n5 4 3 2 1", solve_083, "单调递减", "typical", verify),
        generated_case("2\n1\n7\n8\n1 4 2 7 3 8 1 5", solve_083, "多组及不同波动", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 084 Order of a repeated-character permutation action


def _lcm(a: int, b: int) -> int:
    return a // math.gcd(a, b) * b


def solve_084(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(lines[pos])
        string = lines[pos + 1].strip()[:n]
        perm = [v - 1 for v in map(int, lines[pos + 2].split())]
        pos += 3
        seen = [False] * n
        order = 1
        for start in range(n):
            if seen[start]:
                continue
            cycle: list[int] = []
            cur = start
            while not seen[cur]:
                seen[cur] = True
                cycle.append(cur)
                cur = perm[cur]
            chars = [string[i] for i in cycle]
            period = len(chars)
            for shift in range(1, len(chars) + 1):
                if all(chars[i] == chars[(i + shift) % len(chars)] for i in range(len(chars))):
                    period = shift
                    break
            order = _lcm(order, period)
        answers.append(str(order % MOD))
    return "\n".join(answers)


def cases_084() -> list[dict[str, str]]:
    verify = "分解排列循环，并在每个循环上直接寻找字符序列的最小正移位，再求循环节 lcm。"
    return [
        generated_case("1\n1\na\n1", solve_084, "单点恒等排列", "boundary", verify),
        generated_case("1\n4\naaaa\n2 3 4 1", solve_084, "四环但字符周期一", "boundary", verify),
        generated_case("1\n5\nabcde\n2 3 1 5 4", solve_084, "长度三和二的两循环", "typical", verify),
        generated_case("1\n4\nabab\n2 3 4 1", solve_084, "循环内字符周期二", "adversarial", verify),
        generated_case("2\n3\naab\n2 1 3\n6\nxyzxyz\n2 3 4 5 6 1", solve_084, "多组循环节", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 085 Minimum split XOR


def solve_085(text: str) -> str:
    data = list(map(int, text.split()))
    return "\n".join(str(min(x ^ (n - x) for x in range(n + 1))) for n in data[1 : 1 + data[0]])


def cases_085() -> list[dict[str, str]]:
    verify = "在合法小范围内直接枚举全部 x，计算 x xor (n-x) 的最小值。"
    return [
        generated_case("1\n1", solve_085, "最小 n", "boundary", verify),
        generated_case("4\n2 3 4 5", solve_085, "小值边界", "boundary", verify),
        generated_case("4\n7 8 11 15", solve_085, "二进制边界", "typical", verify),
        generated_case("3\n16 17 31", solve_085, "2 的幂附近", "adversarial", verify),
        generated_case("2\n63 64", solve_085, "连续跨幂次", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 086 Maximum subarray-sum permutation (semantic checker: any optimal one)


def solve_086(text: str) -> str:
    n = int(text)
    weights = [(i + 1) * (n - i) for i in range(n)]

    # Exhaustively derive both the maximum and one legal maximizing permutation.
    # Lexicographic tie-breaking only makes the generated fixture deterministic.
    best_score = -1
    best_permutation: tuple[int, ...] | None = None
    for permutation in itertools.permutations(range(1, n + 1)):
        score = sum(value * weight for value, weight in zip(permutation, weights))
        if score > best_score or (score == best_score and permutation > best_permutation):
            best_score = score
            best_permutation = permutation
    assert best_permutation is not None
    return f"{best_score % MOD}\n{' '.join(map(str, best_permutation))}"


def cases_086() -> list[dict[str, str]]:
    verify = "枚举全部 n! 个排列并代入位置出现次数权重，独立取得最大总和；同分时固定选字典序最大的合法排列。"
    return [
        generated_case(
            "1",
            solve_086,
            "唯一长度一的排列",
            "boundary",
            verify,
        ),
        generated_case("2", solve_086, "长度二的两个相同权重", "boundary", verify),
        generated_case("3", solve_086, "奇数长度且中间权重唯一最大", "boundary", verify),
        generated_case("4", solve_086, "偶数长度且中心两权重并列", "typical", verify),
        generated_case("5", solve_086, "奇数长度五的位置权重", "typical", verify),
        generated_case("7", solve_086, "更大奇数长度的并列最优解", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 087 Minimum edits for gcd greater than one


def _primes_upto_087(limit: int) -> list[int]:
    if limit < 2:
        return []
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for p in range(2, int(limit**0.5) + 1):
        if sieve[p]:
            sieve[p * p : limit + 1 : p] = b"\x00" * (((limit - p * p) // p) + 1)
    return [i for i in range(2, limit + 1) if sieve[i]]


def solve_087(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    values = list(map(int, lines[1].split()))
    if len(values) != n:
        raise ValueError("wrong gcd array length")
    if n == 1:
        return "0" if values[0] > 1 else "1"
    primes = _primes_upto_087(max(values))
    if not primes:
        return str(n)
    maximum_kept = max(sum(value % p == 0 for value in values) for p in primes)
    return str(n - maximum_kept)


def cases_087() -> list[dict[str, str]]:
    verify = "枚举不超过最大值的质数，统计可保留的整除元素数，取可保留最多者。"
    return [
        generated_case("1\n1", solve_087, "单元素一需修改", "boundary", verify),
        generated_case("1\n2", solve_087, "单元素大于一无需修改", "boundary", verify),
        generated_case("3\n2 4 6", solve_087, "已有公共因子", "boundary", verify),
        generated_case("3\n1 1 1", solve_087, "全为一需全部修改", "adversarial", verify),
        generated_case("5\n6 10 15 7 9", solve_087, "多个质因子竞争", "typical", verify),
        generated_case("6\n35 49 22 26 2 3", solve_087, "二和七各自可保留不同数量", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 088 Closest threshold split sum


def solve_088(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    target = int(lines[1])
    rows = [tuple(map(int, line.split())) for line in lines[2 : 2 + n]]
    low = min(h for h, _, _ in rows) - 1
    high = max(h for h, _, _ in rows) + 1
    best = min(
        abs(sum(low_value if h < threshold else high_value for h, low_value, high_value in rows) - target)
        for threshold in range(low, high + 1)
    )
    return str(best)


def cases_088() -> list[dict[str, str]]:
    verify = "枚举所有分段会变化的整数阈值小范围，直接计算最终总和与目标差的绝对值。"
    return [
        generated_case("1\n5\n3 1 9", solve_088, "单元素阈值两侧", "boundary", verify),
        generated_case("2\n0\n1 -4 5\n2 3 -6", solve_088, "可精确达到负目标", "boundary", verify),
        generated_case("3\n10\n1 5 100\n2 3 50\n3 1 20", solve_088, "目标落在中间和值", "typical", verify),
        generated_case("4\n7\n2 0 1\n2 8 9\n5 -3 4\n5 10 10", solve_088, "阈值相等必须整体切换", "adversarial", verify),
        generated_case("5\n100\n-2 -10 1\n0 2 3\n4 -8 7\n9 1 -1\n12 5 20", solve_088, "含负门槛值与负值属性", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 089 First-descent adjacent swaps


def solve_089(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n, operations = data[pos], data[pos + 1]
        pos += 2
        perm = data[pos : pos + n]
        pos += n
        for _ in range(operations):
            descent = next((i for i in range(n - 1) if perm[i] > perm[i + 1]), None)
            if descent is None:
                break
            perm[descent], perm[descent + 1] = perm[descent + 1], perm[descent]
        answers.append(" ".join(map(str, perm)))
    return "\n".join(answers)


def cases_089() -> list[dict[str, str]]:
    verify = "按定义直接寻找最左下降并交换；小 k 用例只做有限次真实操作。"
    return [
        generated_case("1\n1 100\n1", solve_089, "单元素无相邻对", "boundary", verify),
        generated_case("1\n4 50\n1 2 3 4", solve_089, "已升序操作空转", "boundary", verify),
        generated_case("1\n4 1\n4 3 2 1", solve_089, "只交换最左逆序", "typical", verify),
        generated_case("1\n4 100\n4 3 2 1", solve_089, "大 k 收敛到升序", "typical", verify),
        generated_case("2\n3 0\n3 1 2\n5 3\n2 5 1 4 3", solve_089, "零次及一般三步", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 090 Minimum unit transfers to a palindrome


def _min_palindrome_moves_090(values: list[int]) -> int:
    n = len(values)
    total = sum(values)
    if n % 2 == 0 and total % 2:
        return -1
    pairs = [(values[i], values[n - 1 - i]) for i in range(n // 2)]
    best_units = math.inf

    def search(index: int, used_pair_sum: int, cost: int) -> None:
        nonlocal best_units
        if cost >= best_units:
            return
        if index == len(pairs):
            if n % 2 == 0:
                if 2 * used_pair_sum != total:
                    return
            else:
                center = total - 2 * used_pair_sum
                if center < 0:
                    return
                cost += abs(values[n // 2] - center)
            best_units = min(best_units, cost)
            return
        left, right = pairs[index]
        for target in range(total + 1):
            if 2 * (used_pair_sum + target) > total and n % 2 == 0:
                break
            search(index + 1, used_pair_sum + target, cost + abs(left - target) + abs(right - target))

    search(0, 0, 0)
    if best_units == math.inf or best_units % 2:
        raise AssertionError("palindrome total must be transferable in whole units")
    return best_units // 2


def solve_090(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n = data[pos]
        pos += 1
        values = data[pos : pos + n]
        pos += n
        answers.append(str(_min_palindrome_moves_090(values)))  # type: ignore[arg-type]
    return "\n".join(answers)


def cases_090() -> list[dict[str, str]]:
    verify = "枚举每对最终公共值的非负分配，直接最小化 L1 搬运量并除以二。"
    return [
        generated_case("1\n1\n7", solve_090, "单元素已是回文", "boundary", verify),
        generated_case("1\n2\n1 2", solve_090, "偶数长度奇数和不可行", "boundary", verify),
        generated_case("1\n4\n1 2 3 4", solve_090, "每对都需调整", "typical", verify),
        generated_case("1\n4\n1 2 2 5", solve_090, "成对耦合的反例", "adversarial", verify),
        generated_case("2\n3\n1 1 3\n5\n4 1 6 1 4", solve_090, "奇数长度多组", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 091 Maximum complete multipartite edge-weight sum


def solve_091(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n = data[pos]
        pos += 1
        weights = data[pos : pos + n]
        pos += n
        if n == 1:
            answers.append("0")
            continue
        best: int | None = None
        assignments = [0] * n

        def enumerate_groups(index: int, maximum_used: int) -> None:
            nonlocal best
            if index == n:
                if maximum_used < 1:
                    return  # fewer than two nonempty layers
                total = sum(
                    min(weights[i], weights[j])
                    for i in range(n)
                    for j in range(i + 1, n)
                    if assignments[i] != assignments[j]
                )
                best = total if best is None else max(best, total)
                return
            for group in range(maximum_used + 2):
                if group > maximum_used + 1:
                    break
                assignments[index] = group
                enumerate_groups(index + 1, max(maximum_used, group))

        assignments[0] = 0
        enumerate_groups(1, 0)
        if best is None:
            raise AssertionError("two-layer enumeration produced no candidate")
        answers.append(str(best))
    return "\n".join(answers)


def cases_091() -> list[dict[str, str]]:
    verify = "用受限增长串枚举全部无序分层，直接累加跨层 min(a_i,a_j) 并取最大。"
    verify_signed = "独立枚举受限增长串表示的全部无序分层，直接累加跨层 min(a_i,a_j)；允许整数权值为负，不做非负假设。"
    verify_large = "独立枚举受限增长串表示的全部无序分层，以 Python 任意精度整数直接累加跨层 min(a_i,a_j)。"
    return [
        generated_case("1\n1\n5", solve_091, "单节点无边", "boundary", verify),
        generated_case("1\n2\n3 3", solve_091, "两节点必须分两层", "boundary", verify),
        generated_case("1\n2\n1 2", solve_091, "两节点不等权时唯一交叉边", "boundary", verify),
        generated_case("1\n4\n1 2 3 4", solve_091, "递增权值", "typical", verify),
        generated_case("1\n5\n5 5 5 5 5", solve_091, "全相等权值", "adversarial", verify),
        generated_case("2\n3\n9 1 5\n6\n2 7 3 6 1 4", solve_091, "多组不同权值", "adversarial", verify),
        generated_case("1\n3\n-5 -4 -3", solve_091, "全负权值最小内部和", "adversarial", verify_signed),
        generated_case("1\n3\n-3 -1 2", solve_091, "混合符号删负内部边", "adversarial", verify_signed),
        generated_case(
            "1\n6\n1000000000 1000000000 1000000000 1000000000 1000000000 1000000000",
            solve_091,
            "十五亿级边权和",
            "boundary",
            verify_large,
        ),
    ]


# ---------------------------------------------------------------------------
# 092 Knives and shields


def solve_092(text: str) -> str:
    data = list(map(int, text.split()))
    pos = 0
    groups = data[pos]
    pos += 1
    answers: list[str] = []
    for _ in range(groups):
        n, knives, shields, shield_power = data[pos : pos + 4]
        pos += 4
        attacks = data[pos : pos + n]
        pos += n
        best = math.inf
        for actions in itertools.product((0, 1, 2), repeat=n):
            if actions.count(1) > knives or actions.count(2) > shields:
                continue
            damage = sum(
                0 if action == 1 else max(0, attacks[i] - shield_power) if action == 2 else attacks[i]
                for i, action in enumerate(actions)
            )
            best = min(best, damage)
        answers.append(str(best))
    return "\n".join(answers)


def cases_092() -> list[dict[str, str]]:
    verify = "对每轮刀/盾/不用三种策略枚举全部分配并检查资源上限。"
    return [
        generated_case("1\n1 0 0 1\n0", solve_092, "零伤害无道具", "boundary", verify),
        generated_case("1\n2 1 1 10\n5 100", solve_092, "刀应留给最大伤害", "typical", verify),
        generated_case("1\n3 0 2 5\n1 6 20", solve_092, "盾多于有效防守轮", "adversarial", verify),
        generated_case("1\n4 2 0 100\n9 8 7 6", solve_092, "只有刀需挑选两轮", "typical", verify),
        generated_case("2\n3 1 1 5\n10 20 2\n4 0 1 10\n100 20 20 10", solve_092, "多组资源分配", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 093 Strict window peaks


def solve_093(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n, distance = map(int, lines[pos].split())
        values = list(map(int, lines[pos + 1].split()))
        pos += 2
        peaks = []
        for i, value in enumerate(values):
            left = max(0, i - distance)
            right = min(n, i + distance + 1)
            if all(value > values[j] for j in range(left, right) if j != i):
                peaks.append(i + 1)
        answers.append(str(len(peaks)))
        answers.append(" ".join(map(str, peaks)))
    return "\n".join(answers)


def cases_093() -> list[dict[str, str]]:
    verify = "对每个位置直接扫描距离 d 内全部邻项，严格要求大于。"
    return [
        generated_case("1\n1 0\n-5", solve_093, "d 为零单点必为峰", "boundary", verify),
        generated_case("1\n5 10\n1 2 3 4 5", solve_093, "窗口覆盖全数组", "boundary", verify),
        generated_case("1\n6 1\n1 3 2 2 4 0", solve_093, "相邻并列", "adversarial", verify),
        generated_case("1\n7 2\n9 1 2 8 3 7 0", solve_093, "多个局部峰", "typical", verify),
        generated_case("2\n4 0\n1 1 1 1\n5 1\n5 4 3 2 1", solve_093, "全并列与单调下降", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 094 Fog and spotlight intervals


def solve_094(text: str) -> str:
    data = iter(map(int, text.split()))
    groups = next(data)
    answers: list[str] = []
    for _ in range(groups):
        n, fog_count, spot_count = next(data), next(data), next(data)
        initial = [next(data) for _ in range(n)]
        fog = []
        for _ in range(fog_count):
            fog.append((next(data) - 1, next(data) - 1, next(data)))
        spots = []
        for _ in range(spot_count):
            spots.append((next(data) - 1, next(data) - 1, next(data)))
        result = []
        for i in range(n):
            lows = [q for left, right, q in spots if left <= i <= right]
            highs = [p for left, right, p in fog if left <= i <= right]
            low = max(lows, default=0)
            high = min(highs, default=math.inf)
            result.append(min(max(initial[i], low), high))
        answers.append(" ".join(map(str, result)))
    return "\n".join(answers)


def cases_094() -> list[dict[str, str]]:
    verify = "逐位置扫描全部雾幕/聚光区间，直接取下界最大和上界最小后代入公式。"
    return [
        generated_case("1\n1 0 0\n7", solve_094, "无装置保持原值", "boundary", verify),
        generated_case("1\n3 1 0\n1 2 3\n1 3 0", solve_094, "雾幕全遮为负过", "boundary", verify),
        generated_case("1\n4 0 2\n2 2 2 2\n1 2 5\n3 4 7", solve_094, "仅聚光抬升", "typical", verify),
        generated_case("1\n5 2 2\n4 2 7 1 3\n2 4 3\n3 5 5\n1 3 6\n4 5 2", solve_094, "上下界同时覆盖", "typical", verify),
        generated_case("1\n4 1 1\n0 5 9 1\n1 4 4\n2 3 20", solve_094, "下界高于雾幕仍被截断", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 095 Count strings reducible by deleting opposite adjacent pairs


def solve_095(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    strings = lines[1 : 1 + n]
    return str(sum(s.count("0") == s.count("1") for s in strings))


def cases_095() -> list[dict[str, str]]:
    verify = "理论性质：每次删除各一个 0/1，因此等量是必要条件；等量时总能删到一个连续异色边界直至清空。"
    return [
        generated_case("1\n0", solve_095, "单字符", "boundary", verify),
        generated_case("3\n01\n10\n0011", solve_095, "所有等量小串", "boundary", verify),
        generated_case("4\n000111\n010101\n0110\n1110", solve_095, "多种排列等量", "typical", verify),
        generated_case("5\n000\n111\n001\n1100\n101010", solve_095, "不等量与长交替", "adversarial", verify),
        generated_case("2\n00001111\n000111", solve_095, "长重复游程", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 096 Monster defeat days


def _can_finish_096(day: int, n: int, monsters: int, attack: int, health: list[int]) -> bool:
    successful = 0
    for d in range(1, day + 1):
        phase = (d - 1) % n
        power = attack + (d - 1) // n
        successful += power >= health[phase]
        if successful >= monsters:
            return True
    return False


def solve_096(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n, monsters, attack = map(int, lines[pos].split())
        health = list(map(int, lines[pos + 1].split()))
        pos += 2
        high = 1
        while not _can_finish_096(high, n, monsters, attack, health):
            high *= 2
        low = 1
        while low < high:
            mid = (low + high) // 2
            if _can_finish_096(mid, n, monsters, attack, health):
                high = mid
            else:
                low = mid + 1
        answers.append(str(low))
    return "\n".join(answers)


def cases_096() -> list[dict[str, str]]:
    verify = "对天数候选直接逐日模拟血量相位和攻击力，计数成功日并二分最早可行天。"
    return [
        generated_case("1\n1 1 5\n1", solve_096, "首日即可击败", "boundary", verify),
        generated_case("1\n1 2 0\n3", solve_096, "每轮仅一天成功", "boundary", verify),
        generated_case("1\n3 5 2\n1 3 2", solve_096, "相位轮转计数", "typical", verify),
        generated_case("1\n4 6 0\n5 1 5 1", solve_096, "混合血量", "adversarial", verify),
        generated_case("2\n2 3 1\n2 4\n3 4 0\n2 3 5", solve_096, "多组缓慢成长", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 097 Adjacent XOR path sum


def solve_097(text: str) -> str:
    data = list(map(int, text.split()))
    return "\n".join(str(sum(i ^ (i + 1) for i in range(1, n)) % MOD) for n in data[1 : 1 + data[0]])


def cases_097() -> list[dict[str, str]]:
    verify = "按路径定义直接累加每条相邻边 i xor (i+1)，再用前缀公式交叉检查小 n 结果。"
    return [
        generated_case("1\n1", solve_097, "无边的单点路径", "boundary", verify),
        generated_case("3\n2 3 4", solve_097, "连续小值", "boundary", verify),
        generated_case("3\n7 8 15", solve_097, "二进制进位边界", "typical", verify),
        generated_case("2\n16 31", solve_097, "跨二的四次幂", "adversarial", verify),
        generated_case("2\n63 64", solve_097, "连续跨幂边界", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 098 Balanced-interval 01 string (semantic checker: any legal string)


def cases_098() -> list[dict[str, str]]:
    return [
        ncase(
            "2\n2\n1 2\n1 2",
            "01",
            "两个重复最短区间的最简合法构造",
            "boundary",
            "手工构造并核验：两个相同的 [1,2] 区间都恰含一个 0 和一个 1，且 m=2 满足偶数区间数约束。",
        ),
        ncase(
            "4\n2\n1 4\n2 3",
            "0011",
            "全串与非交替内区间同时平衡",
            "boundary",
            "手工核验 [1,4]=0011、[2,3]=01，两个区间均各含一个 0 和一个 1；结果是非交替串。",
        ),
        ncase(
            "6\n2\n1 4\n3 6",
            "001100",
            "两个重叠区间接受非交替构造",
            "typical",
            "手工核验 [1,4]=0011、[3,6]=1100，两个重叠区间各含两个 0 和两个 1。",
        ),
        ncase(
            "7\n2\n1 2\n2 7",
            "1010101",
            "奇数总长度与非全串区间",
            "boundary",
            "手工核验 [1,2]=10、[2,7]=010101，均各含相等数量的 0/1。",
        ),
        ncase(
            "8\n4\n1 8\n1 4\n5 8\n2 3",
            "00111001",
            "多个嵌套区间接受非交替构造",
            "typical",
            "手工核验 [1,8]=00111001、[1,4]=0011、[5,8]=1001、[2,3]=01，均满足 0/1 各半且 m=4。",
        ),
        ncase(
            "10\n4\n1 10\n1 4\n7 10\n2 3",
            "0011011100",
            "总长度大且首尾区间并列",
            "adversarial",
            "手工核验 [1,10]=0011011100、[1,4]=0011、[7,10]=1100、[2,3]=01，所有区间均平衡且 m=4。",
        ),
    ]


CASE_BUILDERS: tuple[tuple[str, int, Callable[[], list[dict[str, str]]], str, str], ...] = (
    ("050-轻量化推理引擎中的-Masked-Fused-RMSNorm.html", 50, cases_050, "float", "输出统一保留两位小数，用 0.0051 吸收标准四舍五入差异。"),
    ("051-X-Means-聚类算法的实现.html", 51, cases_051, "float", "中心明确要求保留两位小数，用 0.0051 作为打印精度容差。"),
    ("052-网游皮肤智能推荐系统.html", 52, cases_052, "tokens", "输出为按顺序的整数标签，空白不敏感但顺序必须一致。"),
    ("053-OCR-智能纠错系统迭代训练和推理.html", 53, cases_053, "tokens", "输出单个按字符顺序拼接的字符串。"),
    ("054-大模型推理-KV-Cache-内存池管理.html", 54, cases_054, "tokens", "输出单个整数。"),
    ("055-基于信息增益的决策树分类器.html", 55, cases_055, "tokens", "输出逐测试样本的整数标签，顺序具有意义。"),
    ("056-最优流水线并行切分.html", 56, cases_056, "tokens", "输出单个整数瓶颈耗时。"),
    ("057-外卖下楼等待时长.html", 57, cases_057, "tokens", "每组输出固定顺序的整数数组。"),
    ("058-密码强度字符串计数.html", 58, cases_058, "tokens", "每组输出一个模数计数整数。"),
    ("059-CLIP-对比学习损失.html", 59, cases_059, "float", "题面规定保留六位小数，用 6e-7 容差。"),
    ("060-多多捕蝇.html", 60, cases_060, "tokens", "输出最小总代价整数。"),
    ("061-多多的营救行动.html", 61, cases_061, "tokens", "输出 SUCCESS 或剩余人数的整数。"),
    ("062-对角线遍历矩阵.html", 62, cases_062, "tokens", "每题输出固定顺序的矩阵元素序列。"),
    ("063-机房维护.html", 63, cases_063, "tokens", "输出最大收益整数。"),
    ("064-神秘三件套.html", 64, cases_064, "tokens", "输出合法三元组数量。"),
    ("065-递增边路径.html", 65, cases_065, "tokens", "输出最大路径边数。"),
    ("066-魔法通道.html", 66, cases_066, "tokens", "输出固定四种模式词之一。"),
    ("067-和差方程最少标定.html", 67, cases_067, "tokens", "输出 YES/NO 及确定数量或 -1。"),
    ("068-展廊灯带后缀点亮.html", 68, cases_068, "tokens", "输出最少操作次数。"),
    ("069-护栏补强.html", 69, cases_069, "tokens", "输出最大最小高度整数。"),
    ("070-驿站补给最短耗时.html", 70, cases_070, "tokens", "每组输出最短时间或 -1。"),
    ("071-冰柜指令看反后仍安全的位置数.html", 71, cases_071, "tokens", "输出合法交换位置数量。"),
    ("072-冷链物流网络最小总代价.html", 72, cases_072, "tokens", "输出最小总代价整数。"),
    ("073-团子体重可能不变的最长连续日子.html", 73, cases_073, "tokens", "输出最长连续段长度。"),
    ("074-环线巡游巡检全部道路的最小花费.html", 74, cases_074, "tokens", "每组输出最小花费整数。"),
    ("075-找朋友.html", 75, cases_075, "tokens", "每组输出最小总矛盾值。"),
    ("076-滑动窗口.html", 76, cases_076, "tokens", "输出最小总增量整数。"),
    ("077-开关控制灯.html", 77, cases_077, "tokens", "每组输出最少按键次数。"),
    ("078-格子行走翻转.html", 78, cases_078, "tokens", "每组固定为翻转数量行和升序位置行，顺序必须一致。"),
    ("079-魔法藤蔓.html", 79, cases_079, "tokens", "每组输出最少操作次数。"),
    ("080-余数游走.html", 80, cases_080, "tokens", "每组输出所有起点游走长度之和。"),
    ("081-最大乘积操作.html", 81, cases_081, "tokens", "每组输出模意义最大乘积。"),
    ("082-消失的括号层.html", 82, cases_082, "tokens", "每组按原字符顺序输出整数轮次。"),
    ("083-平衡度划分.html", 83, cases_083, "tokens", "每组输出最大总价值整数。"),
    ("084-旋转跳跃.html", 84, cases_084, "tokens", "每组输出最小正操作次数的模。"),
    ("085-最小爆发值.html", 85, cases_085, "tokens", "每组输出最小异或值整数。"),
    ("086-排列子数组和最大化.html", 86, cases_086, "permutation-sum", "题面允许输出任意最大排列；语义 checker 应校验第二行是 1..n 排列、其加权和可独立算出最大值，并核对第一行最大值取模。"),
    ("087-数组公约数改造.html", 87, cases_087, "tokens", "输出最少修改元素数。"),
    ("088-阈值分界总和逼近.html", 88, cases_088, "tokens", "输出与目标总和的最小绝对差。"),
    ("089-相邻逆序交换洗牌.html", 89, cases_089, "tokens", "每组输出固定顺序的最终排列。"),
    ("090-蜂蜜回文数组最少搬运.html", 90, cases_090, "tokens", "每组输出最少单位搬运数或 -1。"),
    ("091-连通图边权和最大化.html", 91, cases_091, "tokens", "每组输出最大边权和。"),
    ("092-刀盾分配最小总伤害.html", 92, cases_092, "tokens", "每组输出最小总伤害。"),
    ("093-窗口内严格极峰位置.html", 93, cases_093, "tokens", "每组输出数量行与升序位置行。"),
    ("094-雾幕聚光最终亮度.html", 94, cases_094, "tokens", "每组按位置顺序输出亮度数组。"),
    ("095-可删去的-01-串计数.html", 95, cases_095, "tokens", "输出可删去字符串数量。"),
    ("096-循环血量怪物最少讨伐天数.html", 96, cases_096, "tokens", "每组输出最少天数。"),
    ("097-相邻异或路径权值和.html", 97, cases_097, "tokens", "每组输出路径权值和的模。"),
    ("098-区间平衡01串构造.html", 98, cases_098, "balanced-intervals", "题面明确允许输出任意满足条件的 01 串；语义 checker 应校验长度、字符集以及每个给定区间内 0 与 1 数量相等。"),
)


def build_payload() -> dict[str, object]:
    metadata = json.loads((ROOT / "books/ai-exam/practice-meta.json").read_text(encoding="utf-8"))
    selected_metadata = metadata[49:98]
    if len(selected_metadata) != 49:
        raise ValueError(
            f"practice-meta slice [49:98] must contain 49 problems, got {len(selected_metadata)}"
        )
    expected_urls = [row["url"] for row in selected_metadata]
    if len(CASE_BUILDERS) != 49:
        raise ValueError("case builder registry must contain 49 entries")
    items: dict[str, object] = {}
    for meta_row, (basename, number, builder, mode, reason) in zip(selected_metadata, CASE_BUILDERS):
        url = meta_row["url"]
        if not url.endswith("/" + basename):
            raise ValueError(f"metadata order mismatch at {number}: {url}")
        samples = builder()
        # Problem 091 retains its six reviewed cases and adds three signed/large regressions.
        maximum_cases = 9 if number == 91 else 8
        if mode != "manual" and not 4 <= len(samples) <= maximum_cases:
            raise ValueError(
                f"problem {number} must have 4..{maximum_cases} supplemental cases"
            )
        checker: dict[str, object] = {"mode": mode, "reason": reason}
        if mode == "float":
            checker["abs_tol"] = 0.0051 if number in (50, 51) else 6e-7
            checker["rel_tol"] = 1e-9
        items[url] = {"checker": checker, "samples": samples}
    if list(items) != expected_urls:
        raise AssertionError("item order differs from the practice-meta slice")
    return {"version": 1, "items": items}


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    payload = build_payload()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(item["samples"]) for item in payload["items"].values())
    print(f"wrote {len(payload['items'])} problems and {total} supplemental cases to {output}")


if __name__ == "__main__":
    main()



