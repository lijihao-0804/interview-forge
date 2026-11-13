#!/usr/bin/env python3
"""Generate independently verified supplemental cases for ACM practice slice A.

The expected outputs are derived from small brute-force programs, direct
formula evaluations, or manual semantic simulations of the statements.  The
existing reference programs are not imported or executed by this generator.
"""

from __future__ import annotations

import itertools
import json
import math
import re
import sys
from collections import Counter, deque
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
PRACTICE_META = ROOT / "books" / "ai-exam" / "practice-meta.json"
SLICE_SIZE = 49
DEFAULT_OUTPUT = ROOT / "data" / "ai_exam" / "practice-cases-a.json"


def ncase(
    input_text: str,
    expected: str,
    name: str,
    kind: str,
    verification: str,
) -> dict[str, str]:
    if kind not in {"boundary", "typical", "adversarial"}:
        raise ValueError(f"invalid case kind: {kind}")
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


def fmt(value: float, digits: int) -> str:
    text = f"{value:.{digits}f}"
    if text.startswith("-0") and float(text) == 0.0:
        return "0" + text[2:]
    return text


def fmt_half_up(value: float, digits: int) -> str:
    quantum = Decimal(1).scaleb(-digits)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return format(Decimal(0), f".{digits}f")
    return format(rounded, f".{digits}f")


def fmt_fraction(value: Fraction, digits: int) -> str:
    decimal = Decimal(value.numerator) / Decimal(value.denominator)
    rounded = decimal.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    if rounded == 0:
        return format(Decimal(0), f".{digits}f")
    return format(rounded, f".{digits}f")


# ---------------------------------------------------------------------------
# 001 longest hypnotic substring


def solve_001(text: str) -> str:
    tokens = text.split()
    groups = int(tokens[0])
    pos = 1
    answers: list[str] = []
    for _ in range(groups):
        n = int(tokens[pos])
        s = tokens[pos + 1]
        pos += 2
        if len(s) != n:
            raise ValueError("string length mismatch")
        magic = {i for i, ch in enumerate(s) if ch in "oO0"}
        best = 0
        for left in range(n):
            for right in range(left, n):
                if left in magic and right in magic:
                    best = max(best, right - left + 1)
        answers.append(str(best))
    return "\n".join(answers)


def cases_001() -> list[dict[str, str]]:
    verify = "枚举全部连续子串并按首尾是否为 o/O/0 取最长，未执行参考实现。"
    return [
        generated_case("1\n1\nx", solve_001, "无幻觉字符的最小串", "boundary", verify),
        generated_case("1\n1\nO", solve_001, "单个大写幻觉字符", "boundary", verify),
        generated_case("1\n5\noabcO", solve_001, "仅首尾为幻觉字符", "typical", verify),
        generated_case("1\n7\nab0cdOf", solve_001, "数字零参与端点", "typical", verify),
        generated_case("1\n9\nxxxx0xxxx", solve_001, "重复幻觉字符取长度一", "adversarial", verify),
        generated_case("2\n4\nAbCd\n6\naOxyzb", solve_001, "多组含完全无解", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 002 permutation patrol direction counts


def solve_002(text: str) -> str:
    values = list(map(int, text.split()))
    n = values[0]
    perm = values[1 : n + 1]
    positions = [0] * (n + 1)
    for index, value in enumerate(perm, 1):
        positions[value] = index
    left = sum(positions[v + 1] < positions[v] for v in range(1, n))
    return f"{left} {n - 1 - left}"


def cases_002() -> list[dict[str, str]]:
    verify = "按巡检序号构造位置逆映射，逐一比较相邻序号的位置。"
    return [
        generated_case("1\n1", solve_002, "单元素无移动", "boundary", verify),
        generated_case("4\n1 2 3 4", solve_002, "已按序号递增排列", "boundary", verify),
        generated_case("4\n4 3 2 1", solve_002, "完全逆序", "adversarial", verify),
        generated_case("4\n2 1 4 3", solve_002, "左右交替移动", "typical", verify),
        generated_case("3\n3 1 2", solve_002, "循环排列", "typical", verify),
        generated_case("6\n4 1 6 3 5 2", solve_002, "一般复杂排列", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 003 PCA reconstruction anomaly detection


def cases_003() -> list[dict[str, str]]:
    verify = "样例手算 PCA 秩与阈值；只使用可手工证明的共线或退化数据集。"
    return [
        ncase(
            '{"train":[[1,2],[2,4],[3,6],[4,8]],"test":[[2.5,5],[2.5,6],[3,null]]}',
            "[0, 1, 1]",
            "完美共线训练与单侧缺失补全",
            "typical",
            verify,
        ),
        ncase(
            '{"train":[[0,0],[0,1],[1,0],[1,1]],"test":[[0,0],[1,1],[0.5,0.5]]}',
            "[0, 0, 0]",
            "满秩训练保留全部主成分",
            "boundary",
            verify,
        ),
        ncase(
            '{"train":[[1,1],[1,1],[1,1],[1,1]],"test":[[1,1],[1,2]]}',
            "[0, 1]",
            "零方差训练与非零测试",
            "adversarial",
            verify,
        ),
        ncase(
            '{"train":[[0,0],[0,2],[0,4],[0,6]],"test":[[0,3],[1,3]]}',
            "[0, 1]",
            "首列全零且存在重建误差",
            "adversarial",
            verify,
        ),
    ]


# ---------------------------------------------------------------------------
# 004 random-subspace centroid voting


def fixed_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def cases_004() -> list[dict[str, str]]:
    verify = "按 RandomState 调用顺序手工固定抽袋/特征序列，最近质心与投票另按定义手算。"
    return [
        ncase(
            '{"train":[[0,0,0],[1,0,0],[5,5,1],[6,5,1]],"test":[[0.5,0],[5.5,5],[3,3]],"n_estimators":2,"max_features":2,"seed":2}',
            fixed_json({"features": [[0, 1], [0, 1]], "bootstraps": [[0, 3, 1, 0], [3, 2, 3, 0]], "pred": [0, 1, 1]}),
            "两基分类器含重复抽袋索引",
            "typical",
            verify,
        ),
        ncase(
            '{"train":[[0,0,0,0],[1,0,0,0],[0,5,0,1],[0,6,0,1],[0,0,5,2]],"test":[[0.5,0,0],[0,5.5,0],[0,0,5]],"n_estimators":3,"max_features":2,"seed":0}',
            fixed_json({"features": [[0, 2], [0, 1], [1, 2]], "bootstraps": [[4, 0, 3, 3, 3], [2, 4, 0, 0, 4], [0, 1, 1, 0, 1]], "pred": [0, 1, 2]}),
            "三类且各分类器选不同特征",
            "typical",
            verify,
        ),
        ncase(
            '{"train":[[0,0,0],[2,0,0],[10,0,1],[12,0,1],[0,10,2],[0,12,2]],"test":[[1,0],[11,0],[0,11]],"n_estimators":2,"max_features":1,"seed":42}',
            fixed_json({"features": [[1], [1]], "bootstraps": [[3, 4, 2, 4, 4, 1], [2, 2, 4, 3, 2, 5]], "pred": [0, 0, 2]}),
            "单特征分类器导致类别不可分",
            "adversarial",
            verify,
        ),
        ncase(
            '{"train":[[-2,0,0],[2,0,0],[10,0,1],[14,0,1]],"test":[[0,0],[12,0],[3,0]],"n_estimators":1,"max_features":2,"seed":7}',
            fixed_json({"features": [[0, 1]], "bootstraps": [[3, 0, 1, 2]], "pred": [0, 1, 0]}),
            "单分类器负坐标",
            "boundary",
            verify,
        ),
    ]


# ---------------------------------------------------------------------------
# 005 longest arithmetic-modular pulse


def solve_005(text: str) -> str:
    lines = text.splitlines()
    p, modulus = map(int, lines[0].split())
    values = list(map(int, lines[1].split()))
    if len(values) != p:
        raise ValueError("length mismatch")
    best_len = best_left = best_delta = 0
    for left in range(p):
        if left == p - 1:
            candidates = [(1, 0)]
        else:
            delta = (values[left + 1] - values[left]) % modulus
            candidates = []
            right = left + 1
            while right < p and (values[right] - values[right - 1]) % modulus == delta:
                right += 1
            candidates.append((right - left, delta))
        for length, delta in candidates:
            if length > best_len:
                best_len, best_left, best_delta = length, left + 1, delta
    return f"{best_len} {best_left} {best_delta}"


def cases_005() -> list[dict[str, str]]:
    verify = "逐个起点延伸并比较模 K 前向变化量，所有等长段保留最早起点。"
    return [
        generated_case("1 2\n0", solve_005, "单元素公共差为零", "boundary", verify),
        generated_case("5 10\n7 7 7 7 7", solve_005, "全相等读数", "boundary", verify),
        generated_case("4 10\n9 0 1 2", solve_005, "跨模数回绕", "adversarial", verify),
        generated_case("6 2\n0 1 0 1 1 1", solve_005, "模二交替与末端并列", "typical", verify),
        generated_case("7 13\n1 4 7 2 2 2 8", solve_005, "一般复杂差值序列", "typical", verify),
        generated_case("6 9\n2 2 2 5 8 2", solve_005, "等长重复段选最早", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 006 equal-cardinality two-way partition minimum difference


def solve_006(text: str) -> str:
    tokens = text.split()
    q = int(tokens[0])
    pos = 1
    answers: list[str] = []
    for _ in range(q):
        n = int(tokens[pos])
        values = list(map(int, tokens[pos + 1 : pos + 1 + n]))
        pos += 1 + n
        total = sum(values)
        best = min(abs(2 * sum(values[i] for i in chosen) - total)
                   for chosen in itertools.combinations(range(n), n // 2))
        answers.append(str(best))
    return "\n".join(answers)


def cases_006() -> list[dict[str, str]]:
    verify = "枚举所有恰好 n/2 个工单的组合并直接计算差值。"
    return [
        generated_case("1\n2\n1 100", solve_006, "最小双工单", "boundary", verify),
        generated_case("1\n4\n1 1 1 1", solve_006, "重复收益完全平衡", "boundary", verify),
        generated_case("1\n4\n1 2 3 4", solve_006, "可精确平分", "typical", verify),
        generated_case("1\n4\n1 2 4 8", solve_006, "快速增长的收益", "adversarial", verify),
        generated_case("1\n4\n1 1 1 2", solve_006, "奇数总和最小差一", "adversarial", verify),
        generated_case("3\n2\n5 9\n6\n3 7 7 3 1 1\n8\n9 2 8 3 7 4 6 1", solve_006, "多询问混合规模", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 007 Apriori frequent itemsets


def solve_007(text: str) -> str:
    data = json.loads(text)
    records = [set(row) for row in data["records"]]
    minimum = int(data["min_cnt"])
    universe = sorted(set().union(*records)) if records else []
    found: list[list[object]] = []
    for size in range(1, len(universe) + 1):
        for items in itertools.combinations(universe, size):
            target = set(items)
            support = sum(target <= record for record in records)
            if support >= minimum:
                found.append([list(items), support])
    return json.dumps(found, separators=(",", ":"))


def cases_007() -> list[dict[str, str]]:
    verify = "枚举项全集的所有非空子集并计数包含记录；频繁性的反单调性保证与 Apriori 汇总一致。"
    return [
        generated_case('{"records":[[1]],"min_cnt":2}', solve_007, "不存在频繁项集", "boundary", verify),
        generated_case('{"records":[[3,1]],"min_cnt":1}', solve_007, "单项记录含全部子集", "boundary", verify),
        generated_case('{"records":[[1,2],[1,2],[1,3],[2,3]],"min_cnt":3}', solve_007, "二项集恰好达到阈值", "typical", verify),
        generated_case('{"records":[[4],[4,5],[4,5,6],[5,6],[6]],"min_cnt":2}', solve_007, "重复记录与链式共现", "typical", verify),
        generated_case('{"records":[[5,1,3],[1,3,5],[1,3],[3,5]],"min_cnt":1}', solve_007, "unordered 记录仍输出升序项集", "adversarial", verify),
        generated_case('{"records":[[1,2,3,4]],"min_cnt":1}', solve_007, "四项单记录产生全部子集", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 008 split conformal prediction sets


def solve_008(text: str) -> str:
    data = json.loads(text)
    labels = list(map(int, data["cal_y"]))
    probs = list(map(Fraction, data["cal_p1"]))
    tests = list(map(Fraction, data["test_p1"]))
    scores = sorted(prob if y == 0 else 1 - prob for y, prob in zip(labels, probs))
    n = len(scores)
    k = min(n, (4 * (n + 1) + 4) // 5)  # ceil(4(n+1)/5)
    if (4 * (n + 1)) % 5 == 0:
        k = min(n, 4 * (n + 1) // 5)
    threshold = scores[max(0, k - 1)]
    result: list[int] = []
    for prob in tests:
        has_zero = prob <= threshold
        has_one = prob >= 1 - threshold
        if has_zero and has_one:
            result.append(-1)
        elif has_zero:
            result.append(0)
        elif has_one:
            result.append(1)
        else:
            result.append(-2)
    return json.dumps(result, separators=(",", ":"))


def cases_008() -> list[dict[str, str]]:
    verify = "用 Fraction 精确计算非一致性分数、顺序统计量与两端包含关系。"
    return [
        generated_case('{"cal_y":[0],"cal_p1":[0.2],"test_p1":[0,0.5,0.8,1]}', solve_008, "单校准点阈值封顶", "boundary", verify),
        generated_case('{"cal_y":[0,1],"cal_p1":[0.0,1.0],"test_p1":[0,0.2,0.8,1]}', solve_008, "阈值零与概率端点", "boundary", verify),
        generated_case('{"cal_y":[0,1,0,1,1],"cal_p1":[0.5,0.5,0.5,0.5,0.5],"test_p1":[0.2,0.5,0.8]}', solve_008, "阈值半点形成双类集合", "typical", verify),
        generated_case('{"cal_y":[0,0,0,0,0,0,0,0,0],"cal_p1":[0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8],"test_p1":[0.1,0.79,0.8,0.81]}', solve_008, "n+1 超界时钳制为 n", "adversarial", verify),
        generated_case('{"cal_y":[0,1,0,1],"cal_p1":[0.1,0.7,0.4,0.9],"test_p1":[0,0.39,0.4,0.61,1]}', solve_008, "重复与错位概率", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 009 dynamic farthest gap


def solve_009(text: str) -> str:
    lines = text.splitlines()
    n, updates = map(int, lines[0].split())
    positions = list(map(int, lines[1].split()))
    out: list[str] = []
    for line in lines[2 : 2 + updates]:
        index, value = map(int, line.split())
        positions[index - 1] = value
        left, right = min(positions), max(positions)
        anchors = sorted(set(positions))
        best = 0
        for x in range(left, right + 1):
            best = max(best, min(abs(x - anchor) for anchor in anchors))
        out.append(str(best))
    return "\n".join(out)


def cases_009() -> list[dict[str, str]]:
    verify = "每次修改后在完整整数区间枚举 x 并取最近锚点距离最大值。"
    return [
        generated_case("1 2\n5\n1 5\n1 10", solve_009, "单锚点修改后距离仍为零", "boundary", verify),
        generated_case("2 2\n0 10\n2 6\n1 2", solve_009, "两端锚点移动", "boundary", verify),
        generated_case("2 2\n0 0\n2 4\n1 8", solve_009, "重复锚点分离", "adversarial", verify),
        generated_case("3 3\n1 2 100\n3 1\n2 50\n1 25", solve_009, "一般三锚点动态更新", "typical", verify),
        generated_case("4 2\n-5 -1 6 10\n1 2\n4 -2", solve_009, "含负坐标", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 010 k-th alternating subsequence string


def solve_010(text: str) -> str:
    tokens = text.split()
    groups = int(tokens[0])
    pos = 1
    out: list[str] = []
    for _ in range(groups):
        n, k = int(tokens[pos]), int(tokens[pos + 1])
        s = tokens[pos + 2]
        pos += 3
        if len(s) != n:
            raise ValueError("length mismatch")
        strings: list[str] = []
        for mask in range(1 << n):
            candidate = "".join(s[i] for i in range(n) if mask >> i & 1)
            if all(candidate[i] != candidate[i + 1] for i in range(len(candidate) - 1)):
                strings.append(candidate)
        strings.sort()
        out.append(strings[k - 1] if k <= len(strings) else "-1")
    return "\n".join(out)


def cases_010() -> list[dict[str, str]]:
    verify = "枚举全部下标集合，过滤交替串后按 Python 字典序稳定排序并取第 k 项。"
    return [
        generated_case("1\n1 2\n0", solve_010, "最小串的第二个方案", "boundary", verify),
        generated_case("1\n1 3\n0", solve_010, "方案数不足", "boundary", verify),
        generated_case("1\n2 4\n01", solve_010, "重复字符下标产生长串", "adversarial", verify),
        generated_case("1\n3 4\n000", solve_010, "相同字符只有单字符子序列", "typical", verify),
        generated_case("1\n4 8\n0011", solve_010, "多重复字符的第八个方案", "adversarial", verify),
        generated_case("2\n5 9\n10101\n3 2\n110", solve_010, "多组普通与重复情况", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 011 perceptron


def solve_011(text: str) -> str:
    data = json.loads(text)
    train = data["train"]
    test = data["test"]
    dimension = len(train[0][0])
    weights = [0.0] * (dimension + 1)
    for _ in range(10):
        for features, label in train:
            x = [1.0] + list(map(float, features))
            score = sum(w * v for w, v in zip(weights, x))
            predicted = 1 if score >= 0 else -1
            truth = 2 * int(label) - 1
            if predicted != truth:
                for i in range(dimension + 1):
                    weights[i] += truth * x[i]
    labels: list[int] = []
    for features in test:
        score = weights[0] + sum(w * float(v) for w, v in zip(weights[1:], features))
        labels.append(1 if score >= 0 else 0)
    return json.dumps(labels, separators=(",", ":"))


def cases_011() -> list[dict[str, str]]:
    verify = "按固定十轮、原始顺序和零分归正类规则逐样本更新权重。"
    return [
        generated_case('{"train":[[[0],0],[[1],1]],"test":[[-1],[0],[1],[2]]}', solve_011, "一维极小线性可分", "boundary", verify),
        generated_case('{"train":[[[0,0],0],[[0,0],1]],"test":[[0,0],[1,0]]}', solve_011, "重复特征冲突标签", "adversarial", verify),
        generated_case('{"train":[[[-2,-1],0],[[2,1],1]],"test":[[-2,-1],[0,0],[2,1],[3,2]]}', solve_011, "二维负坐标与零分测试", "typical", verify),
        generated_case('{"train":[[[1,1],0],[[1,-1],1],[[-1,1],1],[[-1,-1],0]],"test":[[1,1],[-1,-1],[1,-1],[-1,1]]}', solve_011, "异或不可线性分且测试训练点", "adversarial", verify),
        generated_case('{"train":[[[0.5],0]],"test":[[0],[0.5],[1]]}', solve_011, "单训练样本与零初始化", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 012 DBSCAN point types (classic Euclidean DBSCAN)


def solve_012(text: str) -> str:
    data = json.loads(text)
    points = data["X"]
    eps = float(data["eps"])
    minimum = int(data["min_samples"])
    neighbors: list[list[int]] = []
    for i, a in enumerate(points):
        neighbors.append([
            j for j, b in enumerate(points)
            if sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)) <= eps ** 2 + 1e-15
        ])
    core = [len(row) >= minimum for row in neighbors]
    result = []
    for i, row in enumerate(neighbors):
        if core[i]:
            result.append(2)
        elif any(core[j] for j in row):
            result.append(1)
        else:
            result.append(0)
    return json.dumps(result, separators=(",", ":"))


def cases_012() -> list[dict[str, str]]:
    verify = "逐点成对计算欧氏距离，先判定全部核心点，再识别边界与噪声。"
    return [
        generated_case('{"X":[[0,0],[10,0]],"eps":1,"min_samples":1}', solve_012, "最小样本数使所有点为核心", "boundary", verify),
        generated_case('{"X":[[0,0],[1,0],[3,0]],"eps":0.4,"min_samples":2}', solve_012, "彼此远离全部为噪声", "boundary", verify),
        generated_case('{"X":[[0,0],[0,1],[0,-1],[0.1,0]],"eps":1,"min_samples":3}', solve_012, "一个核心点带三个边界点", "typical", verify),
        generated_case('{"X":[[0,0],[0.1,0],[0.2,0],[1,0]],"eps":0.2,"min_samples":3}', solve_012, "链式邻域核心与孤立噪声", "typical", verify),
        generated_case('{"X":[[0,0],[0.2,0],[0.4,0]],"eps":0.2,"min_samples":2}', solve_012, "半径等号计入邻域", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 013 mirror laboratory


def solve_013(text: str) -> str:
    lines = text.splitlines()
    groups = int(lines[0])
    pos = 1
    answers: list[str] = []
    directions = [(-1, 0), (0, 1), (1, 0), (0, -1)]  # up, right, down, left
    for _ in range(groups):
        n, m = map(int, lines[pos].split())
        grid = lines[pos + 1 : pos + 1 + n]
        pos += 1 + n
        escaped = 0
        for row in range(n):
            for col in range(m):
                for direction in range(4):
                    r, c, d = row, col, direction
                    seen: set[tuple[int, int, int]] = set()
                    while 0 <= r < n and 0 <= c < m and (r, c, d) not in seen:
                        seen.add((r, c, d))
                        mirror = grid[r][c]
                        if mirror == "/":
                            d = {0: 1, 1: 0, 2: 3, 3: 2}[d]
                        elif mirror == "\\":
                            d = {0: 3, 3: 0, 2: 1, 1: 2}[d]
                        dr, dc = directions[d]
                        r += dr
                        c += dc
                    if not (0 <= r < n and 0 <= c < m):
                        escaped += 1
        answers.append(str(escaped))
    return "\n".join(answers)


def cases_013() -> list[dict[str, str]]:
    verify = "枚举每组网格的全部 4nm 个 (位置,方向) 状态并直接模拟反射直到出界或重复。"
    return [
        generated_case("1\n1 1\n.", solve_013, "单格空实验室", "boundary", verify),
        generated_case("1\n1 2\n..", solve_013, "单行空实验室", "boundary", verify),
        generated_case("1\n2 2\n//\n//", solve_013, "纯斜镜网格", "adversarial", verify),
        generated_case("1\n2 2\n/\\\n\\/", solve_013, "四格对称镜面", "typical", verify),
        generated_case("2\n1 3\n...\n2 2\n/.\n./", solve_013, "多组混合空地与镜面", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 014 one-step MLP backpropagation


def matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


def outer(left: list[float], right: list[float]) -> list[list[float]]:
    return [[a * b for b in right] for a in left]


def solve_014(text: str) -> str:
    lines = text.splitlines()
    din, dhid, dout = map(int, lines[0].split())
    pos = 1
    w1 = [list(map(float, lines[pos + i].split())) for i in range(dhid)]
    pos += dhid
    b1 = list(map(float, lines[pos].split()))
    pos += 1
    w2 = [list(map(float, lines[pos + i].split())) for i in range(dout)]
    pos += dout
    b2 = list(map(float, lines[pos].split()))
    pos += 1
    x = list(map(float, lines[pos].split()))
    truth = list(map(float, lines[pos + 1].split()))
    eta = float(lines[pos + 2])
    if not (len(x) == din and len(truth) == dout):
        raise ValueError("dimension mismatch")
    z1 = [z + bias for z, bias in zip(matvec(w1, x), b1)]
    a1 = [max(0.0, z) for z in z1]
    predicted = [v + bias for v, bias in zip(matvec(w2, a1), b2)]
    delta2 = [pred - actual for pred, actual in zip(predicted, truth)]
    grad_w2 = outer(delta2, a1)
    delta1 = [
        sum(w2[out][hidden] * delta2[out] for out in range(dout)) * (z1[hidden] > 0.0)
        for hidden in range(dhid)
    ]
    grad_w1 = outer(delta1, x)
    new_w1 = [[v - eta * grad_w1[i][j] for j, v in enumerate(row)] for i, row in enumerate(w1)]
    new_b1 = [v - eta * d for v, d in zip(b1, delta1)]
    new_w2 = [[v - eta * grad_w2[i][j] for j, v in enumerate(row)] for i, row in enumerate(w2)]
    new_b2 = [v - eta * d for v, d in zip(b2, delta2)]
    output = [" ".join(fmt(v, 6) for v in row) for row in new_w1]
    output.append(" ".join(fmt(v, 6) for v in new_b1))
    output.extend(" ".join(fmt(v, 6) for v in row) for row in new_w2)
    output.append(" ".join(fmt(v, 6) for v in new_b2))
    output.append(" ".join(fmt(v, 6) for v in predicted))
    return "\n".join(output)


def cases_014() -> list[dict[str, str]]:
    verify = "按链式法则独立计算前向、输出层梯度、ReLU 门控梯度与同步一步更新。"
    return [
        generated_case("1 1 1\n1\n0\n1\n0\n2\n3\n0.1", solve_014, "最小单神经元回归", "boundary", verify),
        generated_case("1 1 1\n-1\n1\n2\n0.5\n1\n2\n0.2", solve_014, "ReLU 零点梯度截断", "adversarial", verify),
        generated_case("2 1 1\n0.5 -0.5\n0.2\n1.2\n0.1\n1 -1\n3\n0.05", solve_014, "二维输入与负特征", "typical", verify),
        generated_case("1 2 2\n2\n-3\n0 0\n1 2\n0.2 -0.1\n0.5 -0.3\n1\n1 -1\n0.1", solve_014, "双隐藏单元和二维输出", "typical", verify),
        generated_case("2 2 1\n1 0\n0 1\n1 -1\n2 -1\n0.5\n0 0\n1\n0.25", solve_014, "零输入只更新偏置", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 015 online least-squares pricing


def solve_015(text: str) -> str:
    tokens = text.split()
    q = int(tokens[0])
    pos = 1
    samples: list[tuple[int, int]] = []
    out: list[str] = []
    for _ in range(q):
        operation = tokens[pos]
        pos += 1
        if operation == "ADD":
            samples.append((int(tokens[pos]), int(tokens[pos + 1])))
            pos += 2
            continue
        x0 = int(tokens[pos])
        pos += 1
        n = len(samples)
        if n == 0:
            out.append("0.000000")
        elif len({x for x, _ in samples}) == 1:
            out.append(fmt(sum(y for _, y in samples) / n, 6))
        else:
            sx = sum(x for x, _ in samples)
            sy = sum(y for _, y in samples)
            sxx = sum(x * x for x, _ in samples)
            sxy = sum(x * y for x, y in samples)
            slope = Fraction(n * sxy - sx * sy, n * sxx - sx * sx)
            intercept = Fraction(sy, n) - slope * Fraction(sx, n)
            prediction = slope * x0 + intercept
            out.append(fmt_fraction(prediction, 6))
    return "\n".join(out)


def cases_015() -> list[dict[str, str]]:
    verify = "用 Fraction 求正规方程并消去浮点误差，覆盖无样本与所有 x 相同的退化分支。"
    return [
        generated_case("1\nQUERY 0", solve_015, "空样本查询", "boundary", verify),
        generated_case("3\nADD 2 10\nADD 2 20\nQUERY 99", solve_015, "所有 x 相同取均值", "boundary", verify),
        generated_case("3\nADD 0 0\nADD 2 2\nQUERY 5", solve_015, "两个点确定精确直线", "typical", verify),
        generated_case("4\nADD 0 1\nADD 1 3\nADD 2 4\nQUERY 4", solve_015, "三点最小二乘外推", "typical", verify),
        generated_case("5\nQUERY -3\nADD -2 -1\nADD 2 3\nQUERY 0\nQUERY 5", solve_015, "负坐标和查询先后", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 016 expert-choice routing


def solve_016(text: str) -> str:
    values = text.split()
    if len(values) < 4:
        raise ValueError("missing header")
    n, d, experts, selected = map(int, values[:4])
    if min(n, d, experts, selected) <= 0 or selected > n:
        return "0"
    pos = 4
    x = [[float(values[pos + i * d + j]) for j in range(d)] for i in range(n)]
    pos += n * d
    gate = [[float(values[pos + i * experts + j]) for j in range(experts)] for i in range(d)]
    pos += d * experts
    transforms: list[list[list[float]]] = []
    for _ in range(experts):
        transforms.append([
            [float(values[pos + i * d + j]) for j in range(d)] for i in range(d)
        ])
        pos += d * d
    scores = [[sum(x[i][k] * gate[k][e] for k in range(d)) for e in range(experts)] for i in range(n)]
    weights: list[list[float]] = []
    for row in scores:
        high = max(row)
        exp_values = [math.exp(value - high) for value in row]
        total = sum(exp_values)
        weights.append([value / total for value in exp_values])
    output = [[0.0] * d for _ in range(n)]
    for expert in range(experts):
        chosen = sorted(range(n), key=lambda i: (-weights[i][expert], i))[:selected]
        for i in chosen:
            transformed = matvec(transforms[expert], x[i])
            for j in range(d):
                output[i][j] += weights[i][expert] * transformed[j]
    return "\n".join(" ".join(fmt(value, 2) for value in row) for row in output)


def cases_016() -> list[dict[str, str]]:
    verify = "独立矩阵乘、逐行稳定 softmax、专家 Top-S 稳定排序与加权累加。"
    return [
        generated_case("2 1 2 1\n1\n2\n0 0\n2\n3", solve_016, "两专家同权重选择同一 token", "typical", verify),
        generated_case("2 1 1 1\n1\n2\n0\n2", solve_016, "单专家按门控权重选大值", "typical", verify),
        generated_case("3 1 1 2\n-1\n0\n2\n0\n2", solve_016, "Top-S 相等权重按下标", "adversarial", verify),
        generated_case("2 2 2 2\n1 2\n3 4\n0 0\n0 0\n1 0\n0 1\n0 1\n1 0", solve_016, "两 token 被两专家全部选中", "adversarial", verify),
        generated_case("2 1 1 2\n1\n2\n0\n2", solve_016, "S 等于 N 的合法边界", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 017 deterministic 3D K-means labels


def solve_017(text: str) -> str:
    values = text.split()
    n, k = int(values[0]), int(values[1])
    points = [
        [float(values[2 + i * 3 + j]) for j in range(3)] for i in range(n)
    ]
    centers = [row[:] for row in points[:k]]
    labels = [0] * n
    for _ in range(100):
        labels = []
        for point in points:
            distances = [sum((point[j] - center[j]) ** 2 for j in range(3)) for center in centers]
            labels.append(min(range(k), key=distances.__getitem__))
        new_centers = [center[:] for center in centers]
        for cluster in range(k):
            members = [points[i] for i, label in enumerate(labels) if label == cluster]
            if members:
                new_centers[cluster] = [sum(row[j] for row in members) / len(members) for j in range(3)]
        shift = max(abs(new_centers[i][j] - centers[i][j]) for i in range(k) for j in range(3))
        centers = new_centers
        if shift < 1e-6:
            break
    return "\n".join(map(str, labels))


def cases_017() -> list[dict[str, str]]:
    verify = "按固定初值、平方欧氏距离、最小编号平局和均值更新直接迭代。"
    return [
        generated_case("1 1\n0 0 0", solve_017, "单点单簇", "boundary", verify),
        generated_case("4 2\n0 0 0\n10 0 0\n1 0 0\n11 0 0", solve_017, "两个明显三维修饰簇", "typical", verify),
        generated_case("3 2\n0 0 0\n2 0 0\n1 0 0", solve_017, "第三点与两初值等距", "adversarial", verify),
        generated_case("5 2\n-2 0 0\n2 0 0\n-3 0 0\n3 0 0\n0 4 0", solve_017, "负坐标与第四维状点", "typical", verify),
        generated_case("3 3\n1 2 3\n4 5 6\n7 8 9", solve_017, "初值等于全部点", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 018 pipeline configuration


def solve_018(text: str) -> str:
    tokens = text.split()
    if len(tokens) != 4 or any(not re.fullmatch(r"[1-9]\d*", token) for token in tokens):
        return "-1 -1"
    layers, max_layers, micro_batches, cards = map(int, tokens)
    feasible = [
        pp for pp in range(1, min(cards, layers) + 1)
        if layers % pp == 0 and layers // pp <= max_layers
    ]
    if not feasible:
        return "-1 -1"
    pp = min(feasible, key=lambda value: (Fraction(value - 1, micro_batches + value - 1), value))
    bubble = Fraction(pp - 1, micro_batches + pp - 1)
    return f"{pp} {fmt_fraction(bubble, 4)}"


def cases_018() -> list[dict[str, str]]:
    verify = "枚举全部正整数 PP，直接检查整除与阶段层数上限，并用 Fraction 比较气泡率。"
    return [
        generated_case("1 1 1 1", solve_018, "单层单卡", "boundary", verify),
        generated_case("5 5 2 3", solve_018, "仅 PP=1 可行时气泡为零", "boundary", verify),
        generated_case("12 4 4 6", solve_018, "多个因数中取气泡率最小", "typical", verify),
        generated_case("16 2 5 10", solve_018, "卡数限制 PP 上界", "adversarial", verify),
        generated_case("7 2 1 10", solve_018, "质数层数无法满足承载上限", "adversarial", verify),
        generated_case("7 7 3 10", solve_018, "单 Stage 合法且气泡为零", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 019 DFT feature extraction and integer K-means


def banker_round_nonnegative(total: int, count: int) -> int:
    quotient, remainder = divmod(total, count)
    twice = 2 * remainder
    if twice < count:
        return quotient
    if twice > count:
        return quotient + 1
    return quotient if quotient % 2 == 0 else quotient + 1


def solve_019(text: str) -> str:
    values = text.split()
    n, length, k = map(int, values[:3])
    pos = 3
    signals = []
    for _ in range(n):
        signals.append([float(v) for v in values[pos : pos + length]])
        pos += length
    initial = list(map(int, values[pos : pos + k]))
    frequencies = list(range(1, length // 2))
    features: list[list[int]] = []
    for signal in signals:
        magnitudes = []
        for frequency in frequencies:
            real = sum(signal[t] * math.cos(2 * math.pi * frequency * t / length) for t in range(length))
            imag = -sum(signal[t] * math.sin(2 * math.pi * frequency * t / length) for t in range(length))
            magnitudes.append((math.hypot(real, imag), frequency))
        order = sorted(magnitudes, key=lambda pair: (-pair[0], pair[1]))
        features.append([frequency for _, frequency in order[:3]])
    centers = [features[index][:] for index in initial]
    for _ in range(100):
        clusters = [[] for _ in range(k)]
        for feature in features:
            distances = [sum((feature[t] - center[t]) ** 2 for t in range(3)) for center in centers]
            clusters[min(range(k), key=distances.__getitem__)].append(feature)
        updated = []
        for cluster in range(k):
            if not clusters[cluster]:
                updated.append(centers[cluster][:])
            else:
                updated.append([
                    banker_round_nonnegative(sum(row[axis] for row in clusters[cluster]), len(clusters[cluster]))
                    for axis in range(3)
                ])
        if updated == centers:
            break
        centers = updated
    return "\n".join(" ".join(map(str, center)) for center in sorted(centers))


def make_019(rankings: list[tuple[int, int, int]], k: int, initial: list[int]) -> str:
    length = 8
    signals = []
    for weights in rankings:
        row = []
        for t in range(length):
            row.append(sum(
                weights[frequency - 1] * math.cos(2 * math.pi * frequency * t / length)
                for frequency in (1, 2, 3)
            ))
        signals.append(row)
    lines = [f"{len(signals)} {length} {k}"]
    lines.extend(" ".join(f"{value:.6f}" for value in row) for row in signals)
    lines.append(" ".join(map(str, initial)))
    return "\n".join(lines)


def cases_019() -> list[dict[str, str]]:
    verify = "直接按 DFT 幅值降序提取频点，并以整数银行家舍入逐步更新 K-means 中心。"
    return [
        generated_case(make_019([(4, 3, 2), (3, 4, 2), (2, 4, 3)], 2, [0, 1]), solve_019, "三类频点重排后二分聚类", "typical", verify),
        generated_case(make_019([(4, 3, 2), (3, 4, 2), (2, 5, 3)], 1, [0]), solve_019, "单簇取逐维中位数", "boundary", verify),
        generated_case(make_019([(4, 3, 2), (2, 3, 4)], 1, [0]), solve_019, "偶数成员触发银行家舍入", "adversarial", verify),
        generated_case(make_019([(5, 1, 2), (1, 5, 2), (1, 2, 5)], 3, [0, 1, 2]), solve_019, "每个特征向量单簇并按字典序排序", "boundary", verify),
        generated_case(make_019([(4, 3, 2), (4, 3, 2), (2, 4, 3), (3, 2, 4)], 2, [0, 2]), solve_019, "重复频域特征与逆序初值", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 020 dynamic NTK-aware RoPE


def solve_020(text: str) -> str:
    lines = text.splitlines()
    sequence_length, pretrain_length, dimension, base, position = lines[0].split()
    sequence_length, pretrain_length, dimension, position = map(
        int, (sequence_length, pretrain_length, dimension, position)
    )
    base = float(base)
    vector = list(map(float, lines[1].split()))
    if len(vector) != dimension or dimension < 4 or dimension % 2:
        raise ValueError("invalid RoPE dimensions")
    scale = max(1.0, sequence_length / pretrain_length)
    adjusted_base = base * scale ** (dimension / (dimension - 2))
    output = vector[:]
    for pair in range(dimension // 2):
        theta = position * adjusted_base ** (-2.0 * pair / dimension)
        cosine, sine = math.cos(theta), math.sin(theta)
        left, right = 2 * pair, 2 * pair + 1
        output[left] = vector[left] * cosine - vector[right] * sine
        output[right] = vector[left] * sine + vector[right] * cosine
    return " ".join(fmt(value, 4) for value in output)


def cases_020() -> list[dict[str, str]]:
    verify = "按缩放因子、动态基频和逐对旋转公式直接计算，未调用参考代码。"
    return [
        generated_case("20 100 4 10000 0\n1 2 3 4", solve_020, "位置零不旋转", "boundary", verify),
        generated_case("5 10 4 10000 3\n0 0 0 0", solve_020, "零向量全零输出", "boundary", verify),
        generated_case("10 10 4 100 1\n1 0 -1 0", solve_020, "序列不超长缩放为一", "typical", verify),
        generated_case("32 8 6 10000 5\n1 2 -1 0.5 3 -2", solve_020, "超长序列六维旋转", "adversarial", verify),
        generated_case("256 64 4 500 127\n-1.5 2.25 3 -4", solve_020, "高位置动态基频", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 021 optimal segmented constant quantization


def interval_cost(values: list[int]) -> int:
    ordered = sorted(values)
    representative = ordered[(len(ordered) - 1) // 2]
    return sum(abs(value - representative) for value in values)


def solve_021(text: str) -> str:
    lines = text.splitlines()
    n, k = map(int, lines[0].split())
    values = list(map(int, lines[1].split()))
    if len(values) != n:
        raise ValueError("length mismatch")
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    costs = {}
    for left in range(n):
        for right in range(left + 1, n + 1):
            costs[left, right] = interval_cost(values[left:right])
    dp = [[math.inf] * (n + 1) for _ in range(k + 1)]
    dp[0][0] = 0
    for groups in range(1, k + 1):
        for right in range(1, n + 1):
            candidates = [
                dp[groups - 1][left] + costs[left, right]
                for left in range(groups - 1, right)
            ]
            if candidates:
                dp[groups][right] = min(candidates)
    return str(dp[k][n])


def cases_021() -> list[dict[str, str]]:
    verify = "枚举所有连续区间并独立计算下中位数绝对误差，再做精确区间 DP。"
    return [
        generated_case("1 1\n42", solve_021, "单元素单区间", "boundary", verify),
        generated_case("3 3\n1 2 3", solve_021, "每个元素独立成段", "boundary", verify),
        generated_case("3 1\n1 2 3", solve_021, "唯一段取下中位数", "typical", verify),
        generated_case("3 2\n0 10 11", solve_021, "偶数长度取下中位数", "adversarial", verify),
        generated_case("4 2\n-5 -5 -1 100", solve_021, "负值与重复值", "adversarial", verify),
        generated_case("5 2\n1 2 10 11 12", solve_021, "两个紧簇的复杂切分", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 022 certainty-forcing loss


def solve_022(text: str) -> str:
    lines = text.splitlines()
    n, vocabulary, budget, multiplier = lines[0].split()
    n, vocabulary, budget = int(n), int(vocabulary), int(budget)
    multiplier = float(multiplier)
    items = []
    base = 0.0
    for line in lines[1 : n + 1]:
        row = line.split()
        logits = list(map(float, row[:vocabulary]))
        label, weight = int(row[vocabulary]), int(row[vocabulary + 1])
        maximum = max(logits)
        exponentials = [math.exp(value - maximum) for value in logits]
        denominator = sum(exponentials)
        probabilities = [value / denominator for value in exponentials]
        ce = -math.log(probabilities[label])
        entropy = -sum(probability * math.log(probability) for probability in probabilities if probability > 0)
        base += ce
        items.append((ce, entropy, weight))
    best = None
    for mask in range(1 << n):
        used = sum(items[i][2] for i in range(n) if mask >> i & 1)
        if used > budget:
            continue
        selected_ce = sum(items[i][0] for i in range(n) if mask >> i & 1)
        selected_entropy = sum(items[i][1] for i in range(n) if mask >> i & 1)
        candidate = (selected_ce, -mask, selected_entropy)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        best = (0.0, 0, 0.0)
    return f"{base + multiplier * best[2]:.2f}"


def cases_022() -> list[dict[str, str]]:
    verify = "独立计算稳定 softmax、交叉熵和熵，并穷举全部 0/1 子集满足容量约束。"
    return [
        generated_case("1 2 1 1.0\n0 0 0 1", solve_022, "容量一选取唯一 token", "boundary", verify),
        generated_case("1 2 1 1.0\n0 0 0 2", solve_022, "容量不足拒绝重 token", "boundary", verify),
        generated_case("2 2 1 1.0\n3 0 0 1\n3 0 1 1", solve_022, "容量一选择高交叉熵 token", "typical", verify),
        generated_case("2 3 2 0.0\n2 1 0 0 1\n0 1 2 2 1", solve_022, "倍率为零时仅基础损失", "adversarial", verify),
        generated_case("3 4 3 0.5\n2 1 0 -1 0 2\n0 3 1 0 2 1\n1 0 2 1 1 2", solve_022, "多 token 背包组合", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 023 weighted nearest products


def solve_023(text: str) -> str:
    lines = text.splitlines()
    n, d, k = map(int, lines[0].split())
    weights = list(map(float, lines[1].split()))
    target = list(map(float, lines[2].split()))
    products = []
    for line in lines[3 : 3 + n]:
        raw = line.split()
        product_id = int(raw[0])
        features = list(map(float, raw[1:]))
        distance = sum(weights[j] * (target[j] - features[j]) ** 2 for j in range(d))
        products.append((distance, product_id))
    products.sort()
    return " ".join(str(product_id) for _, product_id in products[:k])


def cases_023() -> list[dict[str, str]]:
    verify = "逐商品求加权平方距离并按 (距离, 商品 ID) 排序取前 K。"
    return [
        generated_case("1 1 1\n2\n0\n9 1", solve_023, "单商品单维", "boundary", verify),
        generated_case("3 1 3\n1\n0\n30 1\n10 1\n20 -1", solve_023, "正负坐标距离并列按 ID", "adversarial", verify),
        generated_case("3 2 2\n2 0\n1 2\n8 1 2\n7 0 2\n9 1 3", solve_023, "零权重特征不参与距离", "typical", verify),
        generated_case("4 3 1\n1 2 3\n0 0 0\n4 0 0 0\n3 1 0 0\n2 0 2 0\n1 0 0 1", solve_023, "只返回最近一个商品", "boundary", verify),
        generated_case("3 2 2\n1 3\n-2 3\n11 -2 3\n12 -2 2\n13 1 3", solve_023, "不同权重放大距离差", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 024 shortest semantically equivalent agent trace


DIRECTIONS_024 = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}


def solve_024(text: str) -> str:
    lines = text.splitlines()
    n, m = map(int, lines[0].split())
    steps = int(lines[1])
    row, col = n // 2, m // 2
    start = (row, col)
    values: Counter[tuple[int, int]] = Counter()
    for line in lines[2 : 2 + steps]:
        move, operation, raw_parameter = line.split()
        dr, dc = DIRECTIONS_024[move]
        nr, nc = row + dr, col + dc
        if 0 <= nr < n and 0 <= nc < m:
            row, col = nr, nc
        parameter = int(raw_parameter)
        if operation == "I":
            values[row, col] += parameter
        elif operation == "D":
            values[row, col] -= parameter
    targets = [cell for cell, value in values.items() if value != 0]
    target_index = {cell: i for i, cell in enumerate(targets)}
    full = (1 << len(targets)) - 1
    queue = deque([(start[0], start[1], 0)])
    distance = {(start[0], start[1], 0): 0}
    while queue:
        r, c, mask = queue.popleft()
        if (r, c) == (row, col) and mask == full:
            return str(distance[r, c, mask])
        for dr, dc in DIRECTIONS_024.values():
            nr, nc = r + dr, c + dc
            if not (0 <= nr < n and 0 <= nc < m):
                continue
            next_mask = mask
            bit = target_index.get((nr, nc))
            if bit is not None:
                next_mask |= 1 << bit
            state = (nr, nc, next_mask)
            if state not in distance:
                distance[state] = distance[r, c, mask] + 1
                queue.append(state)
    return "-1"


def cases_024() -> list[dict[str, str]]:
    verify = "先模拟原轨迹得到净状态与终点，再在 (格子,目标掩码) 上独立 BFS。"
    return [
        generated_case("3 3\n1\nU N 0", solve_024, "仅需到达原终点", "boundary", verify),
        generated_case("3 3\n1\nU I 1", solve_024, "单目标且终点同格", "boundary", verify),
        generated_case("3 3\n2\nU N 0\nD I 5", solve_024, "中心目标必须绕行后写入", "adversarial", verify),
        generated_case("3 3\n3\nU I 1\nR I 2\nD N 0", solve_024, "两个相邻目标的最短访问", "typical", verify),
        generated_case("3 3\n2\nU N 0\nU I 3", solve_024, "越界停留后写入边界格", "adversarial", verify),
        generated_case("5 5\n4\nL I 2\nL D 2\nR N 0\nD I 4", solve_024, "净值为零格被消去", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 025 bounded KV cache


def solve_025(text: str) -> str:
    lines = text.splitlines()
    capacity, operations = map(int, lines[0].split())
    pos = 1
    cache: dict[int, tuple[Decimal, str, str, str]] = {}
    output: list[str] = []
    for _ in range(operations):
        operation = lines[pos].split()
        pos += 1
        if operation[0] == "ADD":
            token_pos, score_text = int(operation[1]), operation[2]
            key_text, value_text = lines[pos], lines[pos + 1]
            pos += 2
            cache[token_pos] = (Decimal(score_text), score_text, key_text, value_text)
            if len(cache) > capacity:
                pruned = min(cache, key=lambda item: (cache[item][0], item))
                del cache[pruned]
                output.append(f"PRUNED {pruned}")
        else:
            output.append(str(len(cache)))
            for token_pos in sorted(cache):
                _, score_text, key_text, value_text = cache[token_pos]
                output.append(f"{token_pos} {score_text}")
                output.append(key_text)
                output.append(value_text)
    return "\n".join(output)


def cases_025() -> list[dict[str, str]]:
    verify = "用 Decimal 比较分数并同步维护按分数淘汰与按位置查询的两套顺序。"
    return [
        generated_case("1 1\nQUERY", solve_025, "空缓存查询", "boundary", verify),
        generated_case("1 2\nADD 0 1.0\n0 0 0 0\n1 1 1 1\nADD 1 1.0\n2 2 2 2\n3 3 3 3", solve_025, "同分淘汰更小位置", "adversarial", verify),
        generated_case("2 4\nADD 0 5.0\n1 1 1 1\n2 2 2 2\nADD 1 2.0\n3 3 3 3\n4 4 4 4\nQUERY\nADD 2 9.0\n5 5 5 5\n6 6 6 6", solve_025, "装满后替换最低分", "typical", verify),
        generated_case("2 4\nADD 10 0.5\n-1 -1 -1 -1\n-2 -2 -2 -2\nADD 20 0.5\n-3 -3 -3 -3\n-4 -4 -4 -4\nADD 30 0.6\n-5 -5 -5 -5\n-6 -6 -6 -6\nQUERY", solve_025, "非连续位置仍按 pos 输出", "typical", verify),
        generated_case("3 5\nADD 0 1000.0\n0.1 0.2 0.3 0.4\n0.5 0.6 0.7 0.8\nQUERY\nQUERY\nQUERY\nQUERY", solve_025, "多次重复查询保持原文本", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 026 MoE dynamic routing


def solve_026(text: str) -> str:
    values = list(map(int, text.split()))
    n, experts, top_k, capacity = values[:4]
    pos = 4
    loads = [0] * experts
    for _ in range(n):
        scores = values[pos : pos + experts]
        pos += experts
        ranking = sorted(range(experts), key=lambda expert: (-scores[expert], expert))[:top_k]
        for expert in ranking:
            if loads[expert] < capacity:
                loads[expert] += 1
    penalty = sum(load * load for load in loads)
    return f"{penalty}\n" + " ".join(map(str, loads))


def cases_026() -> list[dict[str, str]]:
    verify = "逐 token 稳定排序 Top-K、按专家独立容量接收并直接计算平方负载惩罚。"
    return [
        generated_case("1 1 1 1\n7", solve_026, "单专家单 token", "boundary", verify),
        generated_case("3 3 3 3\n1 2 3\n3 2 1\n2 2 2", solve_026, "Top-K 等于全部专家", "typical", verify),
        generated_case("4 3 2 1\n1 9 8\n9 8 1\n1 9 8\n1 9 8", solve_026, "容量满载后跳过候选", "typical", verify),
        generated_case("4 4 2 2\n5 5 0 0\n5 5 0 0\n0 0 5 5\n0 0 5 5", solve_026, "专家分数并列按小编号", "adversarial", verify),
        generated_case("5 2 1 5\n-1 -2\n-2 -1\n0 0\n10 11\n11 10", solve_026, "负分与零分仍参与路由", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 027 contiguous pipeline partition with communication cost


def solve_027(text: str) -> str:
    lines = text.splitlines()
    n, stages, limit = map(int, lines[0].split())
    times = list(map(int, lines[1].split()))
    communication = list(map(int, lines[2].split())) if n > 1 else []
    best = math.inf
    for cuts in itertools.combinations(range(1, n), stages - 1):
        ends = list(cuts) + [n]
        begin = 0
        total_cost = sum(communication[cut - 1] for cut in cuts)
        valid = True
        for end in ends:
            if sum(times[begin:end]) > limit:
                valid = False
                break
            begin = end
        if valid:
            best = min(best, total_cost)
    return "-1" if best == math.inf else str(best)


def cases_027() -> list[dict[str, str]]:
    verify = "枚举全部恰好 p-1 个切口的集合，逐一检查每段时间和并求通信代价最小。"
    return [
        generated_case("1 1 5\n3", solve_027, "单任务单阶段无通信行", "boundary", verify),
        generated_case("3 3 3\n1 1 1\n5 7", solve_027, "每任务独立成段", "boundary", verify),
        generated_case("4 2 5\n2 2 2 2\n1 100 1", solve_027, "只允许中间高代价切口", "adversarial", verify),
        generated_case("5 3 5\n2 2 3 1 2\n5 1 1 4", solve_027, "多个合法切口组合", "typical", verify),
        generated_case("4 2 3\n2 2 2 2\n1 1 1", solve_027, "不存在满足容量划分", "adversarial", verify),
        generated_case("6 3 10\n4 1 4 1 4 1\n9 2 8 1 7", solve_027, "一般复杂通信代价", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 028 Manhattan DBSCAN point classes


def solve_028(text: str) -> str:
    lines = text.splitlines()
    n, radius, minimum = map(int, lines[0].split())
    points = [tuple(map(int, line.split())) for line in lines[1 : 1 + n]]
    neighbors = []
    for i, (x, y) in enumerate(points):
        neighbors.append([
            j for j, (u, v) in enumerate(points) if abs(x - u) + abs(y - v) <= radius
        ])
    core = [len(row) >= minimum for row in neighbors]
    result = []
    for i, row in enumerate(neighbors):
        if core[i]:
            result.append(0)
        elif any(core[j] for j in row):
            result.append(1)
        else:
            result.append(2)
    return "\n".join(map(str, result))


def cases_028() -> list[dict[str, str]]:
    verify = "逐点计算曼哈顿距离邻域，先固定核心点集合再判定边界与噪声。"
    return [
        generated_case("1 0 1\n3 -2", solve_028, "单点邻域包含自身", "boundary", verify),
        generated_case("3 1 2\n0 0\n1 0\n2 0", solve_028, "边界点不能扩张邻域", "adversarial", verify),
        generated_case("4 2 3\n0 0\n1 1\n2 2\n100 100", solve_028, "曼哈顿半径等于门限", "typical", verify),
        generated_case("4 1 2\n0 0\n0 0\n1 0\n5 5", solve_028, "重复坐标参与邻域计数", "typical", verify),
        generated_case("5 0 1\n1 1\n2 2\n-1 -1\n0 0\n1 2", solve_028, "零半径仅自身计数", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 029 alternating multi-agent scheduling


def solve_029(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    agents = [tuple(map(int, line.split())) for line in lines[1 : 1 + n]]
    infinity = 10**30
    best = [[infinity] * n for _ in range(100)]
    answer = infinity
    for progress in range(100):
        for last in range(n):
            current = best[progress][last]
            if progress == 0 and last == -1:
                current = 0
            if current == infinity:
                continue
            for agent, (gain, cost) in enumerate(agents):
                if agent == last:
                    continue
                next_progress = progress + gain
                next_cost = current + cost
                if next_progress >= 100:
                    answer = min(answer, next_cost)
                elif next_cost < best[next_progress][agent]:
                    best[next_progress][agent] = next_cost
    # Handle the virtual start separately so the first agent is unrestricted.
    for agent, (gain, cost) in enumerate(agents):
        if gain >= 100:
            answer = min(answer, cost)
        elif cost < best[gain][agent]:
            best[gain][agent] = cost
    for progress in range(100):
        for last in range(n):
            current = best[progress][last]
            if current == infinity:
                continue
            for agent, (gain, cost) in enumerate(agents):
                if agent == last:
                    continue
                next_progress = progress + gain
                if next_progress >= 100:
                    answer = min(answer, current + cost)
                elif current + cost < best[next_progress][agent]:
                    best[next_progress][agent] = current + cost
    return str(-1 if answer == infinity else answer)


def cases_029() -> list[dict[str, str]]:
    verify = "在 (进度 0..99, 上一 Agent) 状态图上独立求最短代价，首次调用不受限制。"
    return [
        generated_case("1\n100 7", solve_029, "单 Agent 一次完成", "boundary", verify),
        generated_case("1\n60 5", solve_029, "单 Agent 无法连续调用", "boundary", verify),
        generated_case("2\n50 3\n50 4", solve_029, "两 Agent 交替完成", "typical", verify),
        generated_case("3\n30 1\n40 2\n100 50", solve_029, "昂贵直完成与廉价组合", "typical", verify),
        generated_case("3\n10 5\n20 4\n35 3", solve_029, "多步路径与末态越界", "adversarial", verify),
        generated_case("2\n1 100\n2 1", solve_029, "低成本小步优先", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 030 FlashAttention block merging


def merge_state(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    lm, ld, lv = left
    rm, rd, rv = right
    maximum = max(lm, rm)
    ls = math.exp(lm - maximum)
    rs = math.exp(rm - maximum)
    return maximum, ld * ls + rd * rs, lv * ls + rv * rs


def solve_030(text: str) -> str:
    lines = text.splitlines()
    blocks, queries = map(int, lines[0].split())
    states = [tuple(map(float, line.split())) for line in lines[1 : 1 + blocks]]
    out: list[str] = []
    pos = 1 + blocks
    for _ in range(queries):
        operation = lines[pos].split()
        pos += 1
        if operation[0] == "1":
            states[int(operation[1]) - 1] = tuple(map(float, operation[2:5]))
        else:
            left, right = int(operation[1]) - 1, int(operation[2])
            state = states[left]
            for index in range(left + 1, right):
                state = merge_state(state, states[index])
            out.append(fmt(state[2] / state[1], 6))
    return "\n".join(out)


def cases_030() -> list[dict[str, str]]:
    verify = "按合并公式依次合并半开区间，并直接计算 v/d。"
    return [
        generated_case("1 1\n0 2 6\n2 1 1", solve_030, "单块查询", "boundary", verify),
        generated_case("2 2\n0 1 2\n0 1 4\n2 1 2\n2 2 2", solve_030, "相同最大值权重相加", "typical", verify),
        generated_case("3 3\n1 1 3\n3 2 8\n0 4 0\n2 1 3\n1 2 0 5 10\n2 1 3", solve_030, "更新后重新合并", "typical", verify),
        generated_case("3 2\n-2 1 -4\n5 1 5\n-2 3 -9\n2 1 3\n2 3 3", solve_030, "负最大值和单块右端", "adversarial", verify),
        generated_case("2 1\n-10 1 1\n20 1 -1\n2 1 2", solve_030, "指数量级差极大", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 031 minimum bottleneck contiguous partition


def solve_031(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    weights = list(map(int, lines[1].split()))
    k = int(lines[2])
    best = math.inf
    for cuts in itertools.combinations(range(1, n), k - 1):
        begin = 0
        worst = 0
        for end in list(cuts) + [n]:
            worst = max(worst, sum(weights[begin:end]))
            begin = end
        best = min(best, worst)
    return str(best)


def cases_031() -> list[dict[str, str]]:
    verify = "枚举所有恰好 k 段的连续切分，直接最小化最大负载。"
    return [
        generated_case("1\n7\n1", solve_031, "单层单节点", "boundary", verify),
        generated_case("4\n1 2 3 4\n4", solve_031, "每层一个节点", "boundary", verify),
        generated_case("5\n3 1 4 1 5\n2", solve_031, "一般二分瓶颈", "typical", verify),
        generated_case("6\n8 1 8 1 8 1\n3", solve_031, "重元素被迫分组", "adversarial", verify),
        generated_case("7\n1 1 1 10 1 1 1\n4", solve_031, "中心尖峰", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 032 integer-quantized matrix multiplication


def round_fraction_half_away(value: Fraction) -> int:
    if value >= 0:
        return (2 * value.numerator + value.denominator) // (2 * value.denominator)
    return -round_fraction_half_away(-value)


def solve_032(text: str) -> str:
    lines = text.splitlines()
    m, k, n = map(int, lines[0].split())
    a_rows = []
    for line in lines[1 : 1 + m]:
        values = list(map(int, line.split()))
        a_rows.append((values[:k], values[k], values[k + 1]))
    columns = []
    for line in lines[1 + m : 1 + m + n]:
        raw = line.split()
        if len(raw) != k:
            raise ValueError(f"B column must contain {k} floats, got {len(raw)}")
        columns.append([Fraction(token) for token in raw])
    b_quantized = []
    for column in columns:
        maximum = max(abs(value) for value in column)
        if maximum == 0:
            b_quantized.append(([0] * k, 0, 30))
            continue
        best_b = None
        best_a = None
        for b in range(30, -1, -1):
            candidate = round_fraction_half_away(maximum * (1 << b) / 127)
            if candidate <= 127:
                best_b, best_a = b, candidate
                break
        if best_b is None:
            raise ValueError("unrepresentable quantization scale")
        q = [round_fraction_half_away(value * 127 / maximum) for value in column]
        b_quantized.append((q, best_a, best_b))
    rows = []
    for aq, aa, ab in a_rows:
        cells = []
        for bq, ba, bb in b_quantized:
            dot = sum(x * y for x, y in zip(aq, bq))
            cells.extend((str(dot), str(aa * ba), str(ab + bb)))
        rows.append(" ".join(cells))
    return "\n".join(rows)


def cases_032() -> list[dict[str, str]]:
    verify = "用 Fraction 独立实现 half-away 舍入、最大可行二进制缩放与整数点积。"
    return [
        generated_case("1 1 1\n2 3 1\n1", solve_032, "最小非零量化", "boundary", verify),
        generated_case("1 2 1\n1 -2 5 2\n3 -1", solve_032, "负 B 与正负点积", "adversarial", verify),
        generated_case(
            "1 2 2\n3 4 2 3\n0.001 0.0\n-0.002 0.0",
            solve_032,
            "极小正负非零列量化",
            "boundary",
            "用 Fraction 独立实现 half-away 舍入、最大可行二进制缩放与整数点积；两列均含 k=2 个浮点。",
        ),
        generated_case("2 1 2\n127 5 4\n-127 3 2\n1\n2", solve_032, "A 行正负量化值", "typical", verify),
        generated_case("1 3 2\n1 0 -1 1 0\n1 2 3\n-1 0 1", solve_032, "三维多列混合", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 033 sliding-window attention


def solve_033(text: str) -> str:
    lines = text.splitlines()
    header = list(map(int, lines[0].split()))
    if len(header) != 4:
        raise ValueError("invalid header")
    batch_size, sequence_length, dimension, window = header
    if min(batch_size, sequence_length, dimension, window) <= 0 or window > sequence_length:
        return "0"
    tokens = [line.split() for line in lines[1:] if line.strip()]
    pos = 0
    groups: list[str] = []
    for _ in range(batch_size):
        q = [[float(v) for v in tokens[pos + i][:dimension]] for i in range(sequence_length)]
        pos += sequence_length
        k_mat = [[float(v) for v in tokens[pos + i][:dimension]] for i in range(sequence_length)]
        pos += sequence_length
        v = [[float(v) for v in tokens[pos + i][:dimension]] for i in range(sequence_length)]
        pos += sequence_length
        out_rows = []
        for i in range(sequence_length):
            indices = range(max(0, i - window), min(sequence_length, i + window + 1))
            scores = [sum(q[i][x] * k_mat[j][x] for x in range(dimension)) / math.sqrt(dimension) for j in indices]
            high = max(scores)
            exps = [math.exp(score - high) for score in scores]
            total = sum(exps)
            row = []
            for axis in range(dimension):
                row.append(sum(exps[t] * v[j][axis] for t, j in enumerate(indices)) / total)
            out_rows.append(" ".join(fmt_half_up(value, 2) for value in row))
        groups.append("\n".join(out_rows))
    return "\n\n".join(groups)


def cases_033() -> list[dict[str, str]]:
    verify = "在每行有限窗口内独立计算缩放点积、稳定 softmax 和加权 V。"
    return [
        generated_case("1 1 1 1\n0.5\n-2\n7", solve_033, "单 token 只关注自身", "boundary", verify),
        generated_case("1 2 1 2\n0\n0\n0\n0\n2\n4", solve_033, "全零分数均匀平均", "boundary", verify),
        generated_case("1 3 1 1\n1\n1\n1\n1\n1\n1\n10\n20\n30", solve_033, "窗口半径一的滑动平均", "typical", verify),
        generated_case("2 2 2 1\n1 0\n0 1\n1 0\n0 1\n2 0\n0 2\n0 1\n1 0\n1 0\n0 1\n1 0\n0 1\n3 4\n5 6", solve_033, "双 batch 输出空行分隔", "typical", verify),
        generated_case("1 2 2 2\n0 0\n0 0\n0 0\n0 0\n0 0\n0 0", solve_033, "窗口半径等于序列长", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 034 time-series cleaning and score


def solve_034(text: str) -> str:
    values = list(map(int, text.split()))
    n, window, threshold = values[:3]
    rows = [tuple(values[3 + 3 * i : 6 + 3 * i]) for i in range(n)]
    times = [row[0] for row in rows]
    raw = [row[1] for row in rows]
    quality = [row[2] for row in rows]
    previous_valid = [-1] * n
    next_valid = [-1] * n
    last = -1
    for i in range(n):
        previous_valid[i] = last
        if quality[i] == 0:
            last = i
    last = -1
    for i in range(n - 1, -1, -1):
        next_valid[i] = last
        if quality[i] == 0:
            last = i
    cleaned = [float(v) for v in raw]
    for i in range(n):
        if quality[i] != 2:
            continue
        left, right = previous_valid[i], next_valid[i]
        if left >= 0 and right >= 0:
            ratio = (times[i] - times[left]) / (times[right] - times[left])
            cleaned[i] = raw[left] + (raw[right] - raw[left]) * ratio
        elif left >= 0:
            cleaned[i] = float(raw[left])
        elif right >= 0:
            cleaned[i] = float(raw[right])
    half = (window - 1) // 2
    smoothed = cleaned[:]
    for i, value in enumerate(cleaned):
        sample = cleaned[max(0, i - half) : min(n, i + half + 1)]
        mean = sum(sample) / len(sample)
        variance = sum((x - mean) ** 2 for x in sample) / len(sample)
        if abs(value - mean) > threshold * math.sqrt(variance):
            smoothed[i] = mean
    mean = sum(smoothed) / n
    variance = sum((x - mean) ** 2 for x in smoothed) / n
    std = math.sqrt(variance)
    weight_values = (1.0, 0.5, 0.25)
    denominator = sum(weight_values[q] * abs(x) for x, q in zip(smoothed, quality))
    if denominator == 0 or std == 0:
        return "0"
    score = sum(
        weight_values[q] * abs(x) / denominator * abs((x - mean) / std)
        for x, q in zip(smoothed, quality)
    )
    return str(math.floor(score * 100 + 0.5))


def cases_034() -> list[dict[str, str]]:
    verify = "独立执行有效锚点插值、逐窗总体方差平滑、标准化和加权评分。"
    return [
        generated_case("3 1 1\n1 5 0\n2 5 0\n3 5 0", solve_034, "常数序列标准差为零", "boundary", verify),
        generated_case("3 1 1\n1 0 0\n2 0 1\n3 0 2", solve_034, "全零加权分母为零", "boundary", verify),
        generated_case("4 3 10\n1 -1 0\n2 0 2\n3 1 0\n4 2 0", solve_034, "高质量阈值的插值", "typical", verify),
        generated_case("6 3 2\n1 10 0\n2 15 2\n3 20 0\n4 18 0\n5 100 0\n6 12 0", solve_034, "尖峰平滑与窗口边界", "adversarial", verify),
        generated_case("5 5 1\n1 8 2\n2 9 2\n3 10 0\n4 11 0\n5 12 0", solve_034, "无双侧锚点时复制后继", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 035 two-choice training resource allocation


def solve_035(text: str) -> str:
    lines = text.splitlines()
    n, capacity = map(int, lines[0].split())
    choices = [tuple(map(int, line.split())) for line in lines[1 : 1 + n]]
    feasible: list[tuple[int, int]] = []
    for mask in range(1 << n):
        cost = time = 0
        for i, (c1, t1, c2, t2) in enumerate(choices):
            if mask >> i & 1:
                cost += c2
                time += t2
            else:
                cost += c1
                time += t1
        if cost <= capacity:
            feasible.append((time, cost))
    best_time, best_cost = min(feasible)
    return f"{best_time} {best_cost} {capacity - best_cost}"


def cases_035() -> list[dict[str, str]]:
    verify = "穷举每个任务的两种方案，在资源约束内按 (总耗时, 总资源) 字典序取最优。"
    return [
        generated_case("1 5\n5 7 3 9", solve_035, "单任务强制选方案一", "boundary", verify),
        generated_case("2 15\n5 6 8 3\n7 5 9 2", solve_035, "一般双任务组合", "typical", verify),
        generated_case("2 20\n1 10 2 5\n1 10 2 5", solve_035, "同耗时取更少资源", "adversarial", verify),
        generated_case("3 10\n3 5 4 3\n3 5 4 3\n3 5 4 3", solve_035, "资源紧约束全部选方案一", "boundary", verify),
        generated_case("3 5\n1 100 2 1\n1 100 2 1\n1 100 2 1", solve_035, "昂贵慢方案不可行", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 036 city-constrained weighted k-medoids


def solve_036(text: str) -> str:
    lines = text.splitlines()
    city_count = int(lines[0])
    cities = []
    for i in range(1, city_count + 1):
        x_raw, y_raw, weight_raw = lines[i].split(",")
        cities.append((float(x_raw), float(y_raw), float(weight_raw)))
    k = int(lines[1 + city_count])

    def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    centers = list(range(k))
    seen = set()
    while tuple(centers) not in seen:
        seen.add(tuple(centers))
        clusters = [[] for _ in range(k)]
        for i, city in enumerate(cities):
            distances = [distance(city, cities[center]) for center in centers]
            clusters[min(range(k), key=distances.__getitem__)].append(i)
        new_centers = centers[:]
        for cluster_index, members in enumerate(clusters):
            if not members:
                continue
            def weighted_cost(candidate: int) -> float:
                return sum(cities[i][2] * distance(cities[i], cities[candidate]) for i in members)
            new_centers[cluster_index] = min(members, key=lambda candidate: (weighted_cost(candidate), candidate))
        if new_centers == centers:
            break
        centers = new_centers
    clusters = [[] for _ in range(k)]
    for i, city in enumerate(cities):
        distances = [distance(city, cities[center]) for center in centers]
        clusters[min(range(k), key=distances.__getitem__)].append(i)
    rows = []
    for cluster_index, center in enumerate(centers):
        coverage = sum(cities[i][2] for i in clusters[cluster_index])
        rows.append((cities[center][0], cities[center][1], coverage))
    rows.sort(key=lambda row: (row[0], row[1]))
    return "\n".join(f"{fmt(row[0], 2)},{fmt(row[1], 2)},{fmt(row[2], 2)}" for row in rows)


def cases_036() -> list[dict[str, str]]:
    verify = "独立实现加权 k-medoids 的分簇与簇内城市候选重定位，仅选无反转且唯一中心的输入。"
    return [
        generated_case("1\n1.00,2.00,3.00\n1", solve_036, "单城市单 CDN", "boundary", verify),
        generated_case("2\n0.00,0.00,1.00\n4.00,4.00,2.00\n2", solve_036, "两个城市各成一个 CDN", "boundary", verify),
        generated_case("3\n0.00,0.00,1.00\n1.00,0.00,1.00\n2.00,0.00,1.00\n1", solve_036, "一簇重定位到中位城市", "typical", verify),
        generated_case("4\n0.00,0.00,1.00\n0.00,1.00,2.00\n10.00,0.00,3.00\n10.00,1.00,4.00\n2", solve_036, "两个远离簇稳定不动", "typical", verify),
        generated_case("3\n1.00,1.00,1.00\n3.00,1.00,1.00\n5.00,1.00,1.00\n3", solve_036, "CDN 数等于城市数", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 037 global KV sparsification


def solve_037(text: str) -> str:
    lines = text.splitlines()
    layers, heads, tokens, budget = map(int, lines[0].split())
    scores = []
    for line in lines[1 : 1 + layers]:
        raw = list(map(float, line.split()))
        scores.append([raw[h * tokens : (h + 1) * tokens] for h in range(heads)])
    current = int(lines[1 + layers])
    kept = [[[current] for _ in range(heads)] for _ in range(layers)]
    remaining = budget - layers * heads
    candidates = []
    for layer in range(layers):
        for head in range(heads):
            for token in range(tokens):
                if token != current:
                    candidates.append((-scores[layer][head][token], layer, head, token))
    for _, layer, head, token in sorted(candidates)[: max(remaining, 0)]:
        kept[layer][head].append(token)
    for layer in range(layers):
        for head in range(heads):
            kept[layer][head].sort()
    return "\n".join(
        " ".join(",".join(map(str, kept[layer][head])) for head in range(heads))
        for layer in range(layers)
    )


def cases_037() -> list[dict[str, str]]:
    verify = "先强制保留当前位置，再按 (-score, layer, head, token) 全局排序取剩余预算。"
    return [
        generated_case("1 1 1 1\n9\n0", solve_037, "仅强制保留当前位置", "boundary", verify),
        generated_case("1 1 3 3\n0.1 0.9 0.1\n1", solve_037, "单头按分数补一个候选", "typical", verify),
        generated_case("1 1 3 3\n0.5 0.8 0.5\n1", solve_037, "剩余候选分数并列按 token", "adversarial", verify),
        generated_case("2 2 2 6\n0.1 0.2 0.3 0.4\n0.4 0.3 0.2 0.1\n0", solve_037, "跨两层的全局预算分配", "typical", verify),
        generated_case("1 2 3 4\n0.1 0.9 0.1 0.1 0.2 0.8\n2", solve_037, "两头共享总预算", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 038 density-connected document fragments


def solve_038(text: str) -> str:
    lines = text.splitlines()
    n, queries, radius_raw, minimum = lines[0].split()
    n, queries, minimum = int(n), int(queries), int(minimum)
    radius = Decimal(radius_raw)
    points = [tuple(Decimal(v) for v in line.split()) for line in lines[1 : 1 + n]]
    neighbors: list[list[int]] = []
    for x, y in points:
        neighbors.append([
            j for j, (u, v) in enumerate(points)
            if (x - u) ** 2 + (y - v) ** 2 <= radius ** 2
        ])
    core = [len(row) >= minimum for row in neighbors]
    parent = list(range(n))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for i in range(n):
        if core[i]:
            for j in neighbors[i]:
                if core[j]:
                    union(i, j)
    memberships = [
        {find(j) for j in neighbors[i] if core[j]} for i in range(n)
    ]
    out = []
    for line in lines[1 + n : 1 + n + queries]:
        first, second = map(int, line.split())
        out.append(str(int(bool(memberships[first] & memberships[second]))))
    return "\n".join(out)


def cases_038() -> list[dict[str, str]]:
    verify = "精确 Decimal 建邻域，仅连接核心点，并用核心簇集合判断查询密度相连。"
    return [
        generated_case("1 1 0.5 1\n0 0\n0 0", solve_038, "单核心点与自身相连", "boundary", verify),
        generated_case("2 3 1 2\n0 0\n1 0\n0 1\n0 0\n1 1\n0 1", solve_038, "核心自连与重复查询", "boundary", verify),
        generated_case("3 3 1 2\n0 0\n1 0\n10 0\n0 1\n0 2\n2 2", solve_038, "不同核心簇及噪声自身", "adversarial", verify),
        generated_case("4 4 1 2\n0 0\n0.5 0\n1 0\n1.5 0\n0 3\n1 3\n0 1\n1 2", solve_038, "相对邻域连接两个核心", "typical", verify),
        generated_case("4 3 1 3\n0 0\n0.1 0\n0 1\n0.2 0\n3 0\n3 1\n3 2", solve_038, "边界点与噪声查询", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 039 dynamic contiguous weight pruning


def solve_039(text: str) -> str:
    lines = text.splitlines()
    n, budget = map(int, lines[0].split())
    importance = list(map(int, lines[1].split()))
    memory = list(map(int, lines[2].split()))
    ordinary = compressed = 0
    for left in range(n):
        for right in range(left, n):
            used = sum(memory[left : right + 1])
            score = sum(importance[left : right + 1])
            if used <= budget:
                ordinary = max(ordinary, score)
            candidates = range(left, right + 1)
            block = min(candidates, key=lambda i: (importance[i], -memory[i], i))
            if used - memory[block] // 2 <= budget:
                compressed = max(compressed, score - importance[block])
    compressed = max(compressed, ordinary)
    return f"{ordinary} {compressed}"


def cases_039() -> list[dict[str, str]]:
    verify = "枚举全部连续区间，分别检查原内存和量化最重要最小块后的内存与收益。"
    return [
        generated_case("1 10\n7\n9", solve_039, "单块普通与量化模式", "boundary", verify),
        generated_case("1 3\n7\n9", solve_039, "预算不足时答案为两个零", "boundary", verify),
        generated_case("3 4\n5 1 4\n3 4 3", solve_039, "量化最小重要度以纳入区间", "adversarial", verify),
        generated_case("4 10\n3 9 2 8\n2 3 2 3", solve_039, "正收益子数组选择", "typical", verify),
        generated_case("4 7\n5 5 5 5\n6 6 6 6", solve_039, "并列最小重要度选最大内存节省", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 040 fixed Transformer encoder layer


def layer_norm_040(values: list[float]) -> list[float]:
    mean = sum(values) / 4
    variance = sum((value - mean) ** 2 for value in values) / 4
    scale = math.sqrt(variance + 1e-5)
    return [(value - mean) / scale for value in values]


def solve_040(text: str) -> str:
    values = list(map(float, text.split()))
    if len(values) != 8:
        raise ValueError("expected eight values")
    x = [values[:4], values[4:]]
    head_rows = []
    for start in (0, 2):
        head = [row[start : start + 2] for row in x]
        head_out = []
        for query in head:
            scores = [sum(a * b for a, b in zip(query, key)) / math.sqrt(2) for key in head]
            high = max(scores)
            exponentials = [math.exp(score - high) for score in scores]
            total = sum(exponentials)
            head_out.append([
                sum(exponentials[j] * head[j][axis] for j in range(2)) / total
                for axis in range(2)
            ])
        head_rows.append(head_out)
    attention = [
        head_rows[0][token] + head_rows[1][token] for token in range(2)
    ]
    hidden = [
        layer_norm_040([x[token][axis] + attention[token][axis] for axis in range(4)])
        for token in range(2)
    ]
    output = [layer_norm_040([value + max(0.0, value) for value in hidden[token]]) for token in range(2)]
    return " ".join(fmt(value, 2) for row in output for value in row)


def cases_040() -> list[dict[str, str]]:
    verify = "按固定维度独立执行双头注意力、残差层归一化、恒等 FFN 与第二次层归一化。"
    return [
        generated_case("0 0 0 0 0 0 0 0", solve_040, "零输入保持零输出", "boundary", verify),
        generated_case("1 1 1 1 1 1 1 1", solve_040, "全相同输入形成零残差", "boundary", verify),
        generated_case("1 2 3 4 5 6 7 8", solve_040, "递增输入", "typical", verify),
        generated_case("-1 2 -3 4 4 -3 2 -1", solve_040, "正负对称输入", "adversarial", verify),
        generated_case("10 1 -5 2 -2 7 0 -8", solve_040, "一般双 token 非对称输入", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 041 iterative Bi-K-Means domains


def sse_041(points: list[tuple[int, int]]) -> float:
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    return sum((x - mean_x) ** 2 + (y - mean_y) ** 2 for x, y in points)


def split_two_041(points: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    first_point = min(points, key=lambda point: point[0])
    second_point = max(points, key=lambda point: point[0])
    centers = [[float(first_point[0]), float(first_point[1])], [float(second_point[0]), float(second_point[1])]]
    previous_labels = None
    labels: list[int] = []
    for _ in range(1000):
        labels = []
        for x, y in points:
            d0 = (x - centers[0][0]) ** 2 + (y - centers[0][1]) ** 2
            d1 = (x - centers[1][0]) ** 2 + (y - centers[1][1]) ** 2
            labels.append(0 if d0 < d1 else 1)
        if labels == previous_labels:
            break
        previous_labels = labels[:]
        new_centers = []
        largest_move = 0.0
        for label in (0, 1):
            group = [points[i] for i, value in enumerate(labels) if value == label]
            center_x = sum(x for x, _ in group) / len(group)
            center_y = sum(y for _, y in group) / len(group)
            largest_move = max(largest_move, math.hypot(center_x - centers[label][0], center_y - centers[label][1]))
            new_centers.append([center_x, center_y])
        centers = new_centers
        if largest_move < 1e-6:
            break
    else:
        raise ValueError("split did not settle")
    first = [points[i] for i, label in enumerate(labels) if label == 0]
    second = [points[i] for i, label in enumerate(labels) if label == 1]
    return first, second


def solve_041(text: str) -> str:
    numbers = list(map(int, text.split()))
    target, count = numbers[:2]
    points = [tuple(numbers[i : i + 2]) for i in range(2, 2 + 2 * count, 2)]
    clusters = [points]
    output = [str(count)]
    for _ in range(target - 1):
        best_index = -1
        best_gradient = 0.0
        best_children = None
        for index, cluster in enumerate(clusters):
            if len(cluster) < 2:
                continue
            left, right = split_two_041(cluster)
            gradient = sse_041(cluster) - sse_041(left) - sse_041(right)
            better = gradient > best_gradient + 1e-6
            tied = abs(gradient - best_gradient) <= 1e-6
            larger = best_index == -1 or len(cluster) > len(clusters[best_index])
            if best_index == -1 or better or (tied and larger):
                best_index, best_gradient, best_children = index, gradient, (left, right)
        if best_index < 0 or best_children is None:
            raise ValueError("no splittable cluster")
        clusters.pop(best_index)
        clusters.extend(best_children)
        output.append(" ".join(map(str, sorted((len(cluster) for cluster in clusters), reverse=True))))
    return "\n".join(output)


def cases_041() -> list[dict[str, str]]:
    verify = "独立执行指定初值、等距归第二簇、均值更新、SSE 增益与生成顺序选择；使用无平局小例。"
    return [
        generated_case("1\n3\n1 1\n2 2\n6 6", solve_041, "目标为初始单簇", "boundary", verify),
        generated_case("2\n3\n1 1\n2 2\n6 6", solve_041, "两明显端点分裂", "typical", verify),
        generated_case("3\n4\n0 0\n1 0\n10 0\n11 0", solve_041, "递归二分两个紧簇", "typical", verify),
        generated_case("3\n5\n0 5\n1 4\n2 3\n100 0\n101 0", solve_041, "SSE 增益选择先分裂大簇", "adversarial", verify),
        generated_case("4\n4\n0 0\n2 0\n10 0\n12 0", solve_041, "每条目最终单点", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 042 minimum maximum stage load


def solve_042(text: str) -> str:
    lines = text.splitlines()
    n, stages = map(int, lines[0].split())
    load = list(map(int, lines[1].split()))
    best = math.inf
    for cuts in itertools.combinations(range(1, n), stages - 1):
        begin = 0
        worst = 0
        for end in list(cuts) + [n]:
            worst = max(worst, sum(load[begin:end]))
            begin = end
        best = min(best, worst)
    return str(best)


def cases_042() -> list[dict[str, str]]:
    verify = "枚举全部恰好 K 个非空连续 Stage 的切分并最小化最大负载。"
    return [
        generated_case("1 1\n7", solve_042, "单层单 Stage", "boundary", verify),
        generated_case("5 1\n1 2 3 4 5", solve_042, "只有一个 Stage", "boundary", verify),
        generated_case("5 2\n3 5 2 7 4", solve_042, "两层 Stage 平衡", "typical", verify),
        generated_case("6 3\n8 1 8 1 8 1", solve_042, "重层与轻层交错", "adversarial", verify),
        generated_case("4 4\n10 1 100 3", solve_042, "Stage 数等于层数", "boundary", verify),
    ]


# ---------------------------------------------------------------------------
# 043 sparse local attention


def solve_043(text: str) -> str:
    values = list(map(int, text.split()))
    length, dimension, global_count, window, top = values[:5]
    pos = 5
    global_positions = values[pos : pos + global_count]
    pos += global_count
    size = length * dimension
    q = [values[pos + i * dimension : pos + (i + 1) * dimension] for i in range(length)]
    pos += size
    k = [values[pos + i * dimension : pos + (i + 1) * dimension] for i in range(length)]
    pos += size
    v = [values[pos + i * dimension : pos + (i + 1) * dimension] for i in range(length)]
    global_set = set(global_positions)
    rows = []
    for i in range(length):
        if i in global_set:
            candidates = set(range(length))
        else:
            candidates = set(range(max(0, i - window), min(length, i + window + 1))) | global_set
        scored = [
            (sum(q[i][axis] * k[j][axis] for axis in range(dimension)), j)
            for j in candidates
        ]
        selected = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: (-pair[0], pair[1]))[:top]
        output = [
            sum(score * v[j][axis] for score, j in selected) for axis in range(dimension)
        ]
        rows.append(" ".join(map(str, output)))
    return "\n".join(rows)


def cases_043() -> list[dict[str, str]]:
    verify = "独立构造窗口与全局位置并集，过滤非正点积，按 (-score,index) 取 Top-T 后加权。"
    return [
        generated_case("1 1 0 0 1\n2\n3\n4", solve_043, "单位置无全局行", "boundary", verify),
        generated_case("3 1 0 0 1\n1\n1\n1\n2\n2\n2\n10\n20\n30", solve_043, "零窗口只看自身", "boundary", verify),
        generated_case("3 1 1 2 1\n2\n1\n1\n1\n2\n2\n1\n10\n20\n30", solve_043, "全局位置看全序列", "typical", verify),
        generated_case("4 2 1 1 2\n3\n1 0\n0 1\n-1 0\n0 -1\n1 2\n2 1\n3 3\n4 4\n1 10\n2 20\n3 30\n4 40", solve_043, "正负点积并列与 Top-T", "adversarial", verify),
        generated_case("3 1 2 0 2\n0 2\n-1\n2\n-3\n-1\n2\n-3\n5\n6\n7", solve_043, "所有点积非正输出零", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 044 activation recomputation checkpoints


def solve_044(text: str) -> str:
    lines = text.splitlines()
    n, budget = map(int, lines[0].split())
    forward = list(map(int, lines[1].split()))
    memory = list(map(int, lines[2].split()))
    interiors = list(range(1, n))
    best = math.inf
    for mask in range(1 << len(interiors)):
        chosen = [interiors[i] for i in range(len(interiors)) if mask >> i & 1]
        used = sum(memory[layer - 1] for layer in chosen)
        if used > budget:
            continue
        checkpoints = [0] + chosen + [n]
        cost = 0
        for left, right in zip(checkpoints, checkpoints[1:]):
            for layer in range(left + 1, right):
                cost += forward[layer - 1] * (right - layer)
        best = min(best, cost)
    return str(best)


def cases_044() -> list[dict[str, str]]:
    verify = "枚举全部内存可行的中间检查点集合，并按闭区间定义累加每个重算层代价。"
    return [
        generated_case("1 0\n7\n3", solve_044, "无中间层代价为零", "boundary", verify),
        generated_case("2 0\n5 9\n1 1", solve_044, "相邻端点无中间层", "boundary", verify),
        generated_case("3 0\n2 3 4\n1 1 1", solve_044, "预算零强制完整重算", "typical", verify),
        generated_case("4 5\n10 20 30 40\n3 4 2 6", solve_044, "选择第二层检查点", "typical", verify),
        generated_case("5 3\n1 9 1 9 1\n1 3 1 3 1", solve_044, "尖峰前设置检查点", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 045 training cost with two-level objective


def solve_045(text: str) -> str:
    times_raw, k_raw, base_raw, decay_raw = text.strip().split(";")
    times = list(map(int, times_raw.split(",")))
    k = int(k_raw)
    base = float(base_raw)
    decay = float(decay_raw)
    best: tuple[int, float] | None = None
    for assignment in itertools.product(range(k), repeat=len(times)):
        loads = [0] * k
        for task, card in enumerate(assignment):
            loads[card] += times[task]
        peak = max(loads)
        cost = base * sum(load * decay ** (peak - load) for load in loads)
        candidate = (peak, cost)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return f"{best[0]};{fmt(best[1], 4)}"


def cases_045() -> list[dict[str, str]]:
    verify = "穷举每项任务到有标签 NPU 的分配，按 (最大负载, 总成本) 字典序寻优。"
    return [
        generated_case("0;1;1;0.5", solve_045, "单卡零耗时", "boundary", verify),
        generated_case("5;1;0.1;0.9", solve_045, "单卡一般负载", "boundary", verify),
        generated_case("1,1;2;1;0.5", solve_045, "两任务两卡恰好平衡", "typical", verify),
        generated_case("8,1,7;2;0.2;0.8", solve_045, "总负载不等且成本次目标", "adversarial", verify),
        generated_case("3,0,2,0;2;0.5;0.25", solve_045, "多个零耗时任务", "adversarial", verify),
        generated_case("4,3,2,3,5,2,1;3;0.1;0.9", solve_045, "一般六任务三卡", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 046 iterative K-median with Manhattan distance


def solve_046(text: str) -> str:
    lines = text.splitlines()
    n, dimension, k = map(int, lines[0].split())
    points = [list(map(float, line.split())) for line in lines[1 : 1 + n]]
    centers = [row[:] for row in points[:k]]
    labels = [0] * n
    for _ in range(100):
        labels = []
        for point in points:
            distances = [sum(abs(point[axis] - center[axis]) for axis in range(dimension)) for center in centers]
            labels.append(min(range(k), key=distances.__getitem__))
        updated = [center[:] for center in centers]
        for cluster in range(k):
            members = [points[i] for i, label in enumerate(labels) if label == cluster]
            if members:
                for axis in range(dimension):
                    ordered = sorted(row[axis] for row in members)
                    length = len(ordered)
                    updated[cluster][axis] = ordered[length // 2] if length % 2 else (ordered[length // 2 - 1] + ordered[length // 2]) / 2
        shift = sum(abs(updated[i][axis] - centers[i][axis]) for i in range(k) for axis in range(dimension))
        centers = updated
        if shift < 1e-4:
            break
    inertia = sum(
        sum(abs(points[i][axis] - centers[labels[i]][axis]) for axis in range(dimension))
        for i in range(n)
    )
    output = [" ".join(map(str, labels))]
    output.extend(" ".join(fmt(value, 6) for value in center) for center in centers)
    output.append(fmt(inertia, 6))
    return "\n".join(output)


def cases_046() -> list[dict[str, str]]:
    verify = "独立执行曼哈顿分配、偶数中位数、空簇保持与停止后不重分配的计算。"
    return [
        generated_case("1 1 1\n7", solve_046, "单点单簇", "boundary", verify),
        generated_case("3 1 1\n-4\n0\n8", solve_046, "一维中位数中心", "typical", verify),
        generated_case("4 2 2\n0 0\n2 0\n10 0\n12 0", solve_046, "两维两明显簇", "typical", verify),
        generated_case("5 2 1\n1 2\n0 10\n10 0\n10 10\n5 5", solve_046, "单簇二维中位数", "typical", verify),
        generated_case("4 1 2\n0\n0\n10\n10", solve_046, "重复点和初值重合", "adversarial", verify),
        generated_case("5 2 2\n-2 -1\n-1 -2\n0 0\n8 8\n9 9", solve_046, "负坐标与后置大簇", "adversarial", verify),
    ]


# ---------------------------------------------------------------------------
# 047 grouped-query attention


def solve_047(text: str) -> str:
    lines = text.splitlines()
    n, hq, hkv, dk, dv = map(int, lines[0].split())
    pos = 1
    query = [list(map(float, lines[pos + i].split())) for i in range(n)]
    pos += n
    key = [list(map(float, lines[pos + i].split())) for i in range(n)]
    pos += n
    value = [list(map(float, lines[pos + i].split())) for i in range(n)]
    pos += n
    mask = [list(map(int, lines[pos + i].split())) for i in range(n)]
    group = hq // hkv
    output = [[0.0] * (hq * dv) for _ in range(n)]
    for head in range(hq):
        shared = head // group
        q_start, k_start, v_start = head * dk, shared * dk, shared * dv
        for i in range(n):
            scores = []
            for j in range(n):
                score = sum(query[i][q_start + axis] * key[j][k_start + axis] for axis in range(dk)) / math.sqrt(dk)
                scores.append(-1e30 if mask[i][j] else score)
            high = max(scores)
            weights = [math.exp(score - high) for score in scores]
            total = sum(weights)
            for axis in range(dv):
                output[i][head * dv + axis] = sum(
                    weights[j] * value[j][v_start + axis] for j in range(n)
                ) / total
    return "\n".join(" ".join(fmt(value, 2) for value in row) for row in output)


def cases_047() -> list[dict[str, str]]:
    verify = "按连续头列块、共享 KV 头、有限 -1e30 掩码和稳定 softmax 独立计算。"
    return [
        generated_case("1 1 1 1 1\n2\n3\n4\n0", solve_047, "单头单 token", "boundary", verify),
        generated_case("2 2 1 1 1\n1 1\n1 1\n1\n2\n4\n8\n0 0\n0 0", solve_047, "一个 KV 头服务两个 Q 头", "typical", verify),
        generated_case("2 1 1 2 1\n1 0\n-1 0\n1 0\n0 1\n2\n8\n0 1\n1 0", solve_047, "掩码不同导致非线性输出", "adversarial", verify),
        generated_case("2 1 1 1 1\n1\n2\n1\n2\n5\n9\n1 1\n1 1", solve_047, "整行全屏蔽均匀 softmax", "adversarial", verify),
        generated_case("2 4 2 2 2\n1 2 3 4 5 6 7 8\n9 10 11 12 13 14 15 16\n1 2 3 4\n5 6 7 8\n1 2 3 4\n5 6 7 8\n0 0\n0 0", solve_047, "四 Q 头二 KV 头恒等值", "typical", verify),
    ]


# ---------------------------------------------------------------------------
# 048 deterministic CART classification tree


def gini_048(rows: list[tuple[int, int, int, int, int]]) -> Fraction:
    ones = sum(row[4] for row in rows)
    zeros = len(rows) - ones
    return Fraction(2 * zeros * ones, len(rows) * len(rows)) if rows else Fraction(0)


def build_tree_048(rows: list[tuple[int, int, int, int, int]]) -> object:
    ones = sum(row[4] for row in rows)
    majority = int(ones * 2 > len(rows))
    if len(rows) < 2 or ones == 0 or ones == len(rows):
        return majority
    best_score = gini_048(rows)
    best_feature = None
    best_value = None
    for feature in range(4):
        for value in sorted({row[feature] for row in rows}):
            left = [row for row in rows if row[feature] == value]
            right = [row for row in rows if row[feature] != value]
            score = Fraction(len(left), len(rows)) * gini_048(left) + Fraction(len(right), len(rows)) * gini_048(right)
            if score < best_score:
                best_score, best_feature, best_value = score, feature, value
    if best_feature is None:
        return majority
    left = [row for row in rows if row[best_feature] == best_value]
    right = [row for row in rows if row[best_feature] != best_value]
    return best_feature, best_value, build_tree_048(left), build_tree_048(right)


def solve_048(text: str) -> str:
    lines = text.splitlines()
    n = int(lines[0])
    rows = [tuple(map(int, line.split())) for line in lines[1 : 1 + n]]
    m = int(lines[1 + n])
    tests = [tuple(map(int, line.split())) for line in lines[2 + n : 2 + n + m]]
    tree = build_tree_048(rows)
    out = []
    for sample in tests:
        node = tree
        while isinstance(node, tuple):
            feature, value, left, right = node
            node = left if sample[feature] == value else right
        out.append(str(node))
    return " ".join(out)


def cases_048() -> list[dict[str, str]]:
    verify = "用 Fraction 精确比较加权 Gini，独立递归建树并严格按首次最小值处理平票。"
    return [
        generated_case("4\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n1\n3 2 1 0", solve_048, "纯类叶节点", "boundary", verify),
        generated_case("4\n0 0 0 0 0\n0 0 0 0 1\n1 1 1 1 0\n1 1 1 1 1\n4\n0 0 0 0\n0 0 0 0\n1 1 1 1\n1 1 1 1", solve_048, "无切分可降低基尼", "boundary", verify),
        generated_case("4\n0 0 0 0 0\n0 0 0 0 1\n1 0 0 0 0\n1 0 0 0 1\n3\n0 0 0 0\n1 0 0 0\n2 0 0 0", solve_048, "特征零完全分开后右叶多数", "typical", verify),
        generated_case("4\n0 0 0 0 0\n0 1 0 0 1\n1 0 0 0 1\n1 1 0 0 0\n4\n0 0 0 0\n0 1 0 0\n1 0 0 0\n1 1 0 0", solve_048, "并列切分选小编号特征", "adversarial", verify),
        generated_case("8\n0 0 0 0 0\n0 1 0 1 1\n1 0 0 1 1\n1 1 1 0 1\n2 2 1 1 1\n2 0 0 0 0\n3 2 1 0 0\n3 2 0 1 1\n3\n2 0 0 0\n1 1 1 0\n3 2 1 0", solve_048, "多特征递归与未见组合", "typical", verify),
    ]


STATEMENT_EXCLUSIONS: dict[str, dict[str, str]] = {
    "ai-2026/京东/011-字典序第-k-个交替串.html": {
        "空串, 0, 1, 1, 10, 10": (
            "该条把讲解文字误录成输入；题面应为 1 个测试组，根 Python 与 Java 参考实现均在此处解析首行失败。"
        ),
    },
    "ai-2026/华为/025-Agent-执行轨迹压缩.html": {
        "0 3 -1\n0 0 4\n0 0 0": (
            "该条以 3×3 状态矩阵开头，与题面 n m / K / K 条 move op param 格式不符；Python 与 Java 参考实现均读取失败。"
        ),
        "4": (
            "该条只有单个整数，缺少 n m 首行和 K 条移动指令；Python 与 Java 参考实现均读取失败。"
        ),
    },
}


CASE_NOTES: dict[str, str] = {
    "ai-2026/华为/017-Expert-Choice-Routing.html": (
        "当前固定用例按本站已公开的稳定 softmax、Top-S 与同权小编号规则自动校验；"
        "原平台未完整保留的数值实现细节不能保证适用于任意隐藏输入。"
    ),
    "ai-2026/华为/023-Certainty-Forcing-训练损失计算.html": (
        "当前固定用例的最大交叉熵子集均唯一，并按本站公开的两位小数规则自动校验；"
        "原平台未定义最大交叉熵并列时熵项如何取舍，不能保证任意隐藏输入语义完整。"
    ),
    "ai-2026/华为/025-Agent-执行轨迹压缩.html": (
        "当前固定用例按本站已公开的“新轨迹 I/D 参数可任意取值”语义自动校验；"
        "原平台可能另有构造轨迹参数限制，不能保证完整官方语义。"
    ),
    "ai-2026/华为/033-全整型量化的矩阵乘法.html": (
        "当前固定用例均使用合法非零且缩放可表示的列，并按本站公开的 half-away 舍入规则自动校验；"
        "原平台未定义全零列、不可表示缩放和其他半整数情形，不能保证任意隐藏输入语义完整。"
    ),
    "ai-2026/华为/037-CDN分发服务器选址.html": (
        "当前固定用例按本站已公开的 k-medoids、同代价小编号和数值容差规则自动校验；"
        "原平台未完整定义中心重定位同代价、空簇及数值容差，不能保证完整官方语义。"
    ),
    "ai-2026/华为/042-核心路由器管理域规划.html": (
        "当前固定用例按本站已公开的等距归第二簇、SSE 同差取舍和生成顺序规则自动校验；"
        "原平台未完整保留这些选择细节，不能保证任意隐藏输入语义完整。"
    ),
}


# ---------------------------------------------------------------------------
# Registry and generator


def checker(
    mode: str,
    reason: str,
    *,
    abs_tol: float | None = None,
    rel_tol: float | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {"mode": mode, "reason": reason}
    if mode == "float":
        if abs_tol is None or rel_tol is None:
            raise ValueError("float checker requires abs_tol and rel_tol")
        result.update({"abs_tol": abs_tol, "rel_tol": rel_tol})
    elif abs_tol is not None or rel_tol is not None:
        raise ValueError("tolerances are valid only for float checkers")
    return result


def build_registry() -> dict[str, tuple[dict[str, object], list[dict[str, str]]]]:
    return {
        "ai-2026/OPPO/001-幻觉字符串.html": (checker("tokens", "逐行整数结果，仅允许空白分隔差异。"), cases_001()),
        "ai-2026/OPPO/002-序号巡检轨迹.html": (checker("tokens", "每行两个整数，顺序固定且空白不影响语义。"), cases_002()),
        "ai-2026/OPPO/003-监测样本偏离判定.html": (checker("json", "输出为顺序敏感的 JSON 整数数组。"), cases_003()),
        "ai-2026/OPPO/004-防风核心.html": (checker("tokens", "逐组输出一个非负整数。"), cases_004_windbreak()),
        "ai-2026/OPPO/005-抽检子空间质心投票.html": (checker("json", "键序无关但 features/bootstraps/pred 数组顺序均有语义。"), cases_004()),
        "ai-2026/OPPO/006-最长匀差脉冲.html": (checker("tokens", "输出长度、左端点和变化量三个整数。"), cases_005()),
        "ai-2026/京东/007-双班次收益差.html": (checker("tokens", "逐行一个整数结果。"), cases_006()),
        "ai-2026/京东/008-抽检共现项集.html": (checker("json", "输出是分层有序的 JSON 项集数组，结构比较即可。"), cases_007()),
        "ai-2026/京东/009-检索召回置信集映射.html": (checker("json", "输出是顺序敏感的 JSON 标签数组。"), cases_008()),
        "ai-2026/京东/010-锚点最远盲区.html": (checker("tokens", "每行一个整数答案。"), cases_009()),
        "ai-2026/京东/011-字典序第-k-个交替串.html": (checker("tokens", "每个答案是单个 01 串或 -1，token 边界已足以区分。"), cases_010()),
        "ai-2026/京东/012-感知机二分类.html": (checker("json", "输出为顺序敏感的 JSON 二元标签数组。"), cases_011()),
        "ai-2026/京东/013-DBSCAN-点类型判定.html": (checker("json", "输出为顺序敏感的 JSON 点类型数组。"), cases_012()),
        "ai-2026/京东/014-镜子实验室.html": (checker("tokens", "逐组输出一个整数。"), cases_013()),
        "ai-2026/华为/015-回归任务反向传播机理.html": (checker("float", "所有矩阵元素规定六位小数，允许舍入到末位的机器误差。", abs_tol=5.1e-7, rel_tol=1e-6), cases_014()),
        "ai-2026/华为/016-智能物流定价引擎.html": (checker("float", "预测按六位小数输出，允许机器舍入误差。", abs_tol=5.1e-7, rel_tol=1e-6), cases_015()),
        "ai-2026/华为/017-Expert-Choice-Routing.html": (checker("float", "当前公开样例与固定补充用例均为两位小数，按半单位末位容差校验。", abs_tol=5.1e-3, rel_tol=1e-6), cases_016()),
        "ai-2026/华为/018-自动驾驶障碍物检测.html": (checker("tokens", "每行一个整数簇编号。"), cases_017()),
        "ai-2026/华为/019-流水线并行最优配置.html": (checker("float", "PP 为整数，气泡率规定四位小数。", abs_tol=5.1e-5, rel_tol=1e-6), cases_018()),
        "ai-2026/华为/020-频域特征信号聚类.html": (checker("tokens", "每行三个整数中心坐标。"), cases_019()),
        "ai-2026/华为/021-动态旋转位置编码.html": (checker("float", "输出向量规定四位小数。", abs_tol=5.1e-5, rel_tol=1e-6), cases_020()),
        "ai-2026/华为/022-最优分段常数量化.html": (checker("tokens", "输出一个整数最小总误差。"), cases_021()),
        "ai-2026/华为/023-Certainty-Forcing-训练损失计算.html": (checker("float", "当前全部固定用例的最大交叉熵子集唯一，最终输出保留两位小数。", abs_tol=5.1e-3, rel_tol=1e-6), cases_022()),
        "ai-2026/华为/024-智能选品.html": (checker("tokens", "输出商品 ID，顺序即排序结果。"), cases_023()),
        "ai-2026/华为/025-Agent-执行轨迹压缩.html": (checker("tokens", "当前页面已明确构造轨迹的 I/D 参数可任意取值，输出为唯一的最短整数步数。"), cases_024()),
        "ai-2026/华为/026-KV-Cache-稀疏化管理器.html": (checker("tokens", "分数与 KV 必须原样输出，token 比较保留顺序与文本单位。"), cases_025()),
        "ai-2026/华为/027-MoE-动态路由.html": (checker("tokens", "先输出惩罚再输出固定顺序负载整数。"), cases_026()),
        "ai-2026/华为/028-流水线连续划分.html": (checker("tokens", "输出一个通信代价整数或 -1。"), cases_027()),
        "ai-2026/华为/029-基站空间重叠区域识别.html": (checker("tokens", "按输入顺序逐行输出类别整数。"), cases_028()),
        "ai-2026/华为/030-多-Agent-协作任务调度.html": (checker("tokens", "输出一个最小总代价整数。"), cases_029()),
        "ai-2026/华为/031-FlashAttention-分块合并.html": (checker("float", "每次查询输出 v/d 并保留六位小数。", abs_tol=5.1e-7, rel_tol=1e-6), cases_030()),
        "ai-2026/华为/032-流水线并行最小瓶颈.html": (checker("tokens", "输出一个峰值负载整数。"), cases_031()),
        "ai-2026/华为/033-全整型量化的矩阵乘法.html": (checker("tokens", "当前固定用例均为合法非零且缩放可表示的列，按页面公开的 half-away 规则输出唯一整数三元组。"), cases_032()),
        "ai-2026/华为/034-滑动窗口注意力机制.html": (checker("float", "结果规定两位小数，并需保留 batch 间空行语义。", abs_tol=5.1e-3, rel_tol=1e-6), cases_033()),
        "ai-2026/华为/035-时间序列数据清洗与特征评分.html": (checker("tokens", "输出一个已取整的整数评分。"), cases_034()),
        "ai-2026/华为/036-模型训练任务资源分配.html": (checker("tokens", "输出耗时、资源、余量三个整数。"), cases_035()),
        "ai-2026/华为/037-CDN分发服务器选址.html": (checker("float", "当前固定用例按页面公开的 k-medoids 规则得到唯一中心，输出坐标和人数均保留两位小数。", abs_tol=5.1e-3, rel_tol=1e-6), cases_036()),
        "ai-2026/华为/038-动态KV缓存稀疏优化.html": (checker("tokens", "每层每头输出升序 token 索引字符串，顺序固定。"), cases_037()),
        "ai-2026/华为/039-文档片段相关性判定.html": (checker("tokens", "每个查询逐行输出 0/1。"), cases_038()),
        "ai-2026/华为/040-端侧大模型动态权重剪枝管理器.html": (checker("tokens", "输出普通和量化模式两个整数。"), cases_039()),
        "ai-2026/华为/041-实现-Transformer-编码器层.html": (checker("float", "固定结构与固定维度，输出八个两位小数。", abs_tol=5.1e-3, rel_tol=1e-6), cases_040()),
        "ai-2026/华为/042-核心路由器管理域规划.html": (checker("tokens", "当前固定用例按页面公开的等距归组、SSE 同差和生成顺序规则得到唯一簇大小序列。"), cases_041()),
        "ai-2026/华为/043-流水线并行最小化最大-Stage-负载.html": (checker("tokens", "输出一个整数最小最大 Stage 负载。"), cases_042()),
        "ai-2026/华为/044-稀疏局部注意力机制.html": (checker("tokens", "输出整数矩阵，行列顺序固定。"), cases_043()),
        "ai-2026/华为/045-激活重计算.html": (checker("tokens", "输出一个整数最小重计算代价。"), cases_044()),
        "ai-2026/华为/046-训练成本优化.html": (checker("float", "峰值为整数语义、成本保留四位小数；float checker 按 token 数值比较，接受 7 与合法等价的 7.0。", abs_tol=5.1e-5, rel_tol=1e-6), cases_045()),
        "ai-2026/华为/047-K-Median-聚类.html": (checker("float", "标签为整数，中心与 inertia 规定六位小数。", abs_tol=5.1e-7, rel_tol=1e-6), cases_046()),
        "ai-2026/华为/048-分组查询注意力.html": (checker("float", "输出矩阵每项规定两位小数。", abs_tol=5.1e-3, rel_tol=1e-6), cases_047()),
        "ai-2026/华为/049-基于-CART-分类树预测客户购房选择.html": (checker("tokens", "输出一行固定顺序的 0/1 预测。"), cases_048()),
    }


def cases_004_windbreak() -> list[dict[str, str]]:
    """Windbreak cases are kept separate from the random-voting identifier."""
    verify = "枚举所有整数落点并按 max(a_i+|i-p|) 直接求最小能量。"
    return [
        generated_case("1\n1\n0", solve_004_windbreak(), "单树苗零需求", "boundary", verify),
        generated_case("1\n1\n7", solve_004_windbreak(), "单树苗正需求", "boundary", verify),
        generated_case("1\n4\n0 0 0 0", solve_004_windbreak(), "全零需求取内部位置", "typical", verify),
        generated_case("1\n3\n5 0 5", solve_004_windbreak(), "双峰需求", "typical", verify),
        generated_case("1\n5\n0 100 0 100 0", solve_004_windbreak(), "两个高峰", "adversarial", verify),
        generated_case("2\n4\n1 2 3 4\n1\n1000000000", solve_004_windbreak(), "多组线性递增与大需求", "adversarial", verify),
    ]


def solve_004_windbreak() -> Callable[[str], str]:
    def solve(text: str) -> str:
        tokens = text.split()
        groups = int(tokens[0])
        pos = 1
        answers = []
        for _ in range(groups):
            n = int(tokens[pos])
            values = list(map(int, tokens[pos + 1 : pos + 1 + n]))
            pos += 1 + n
            answers.append(str(min(
                max(value + abs(index - place) for index, value in enumerate(values, 1))
                for place in range(1, n + 1)
            )))
        return "\n".join(answers)
    return solve


def validate_record(url: str, record: tuple[dict[str, object], list[dict[str, str]]]) -> None:
    check, samples = record
    if check["mode"] not in {"exact", "tokens", "float", "json", "manual"}:
        raise ValueError(f"invalid checker mode for {url}")
    if check["mode"] in {"float", "manual"} and not check.get("reason"):
        raise ValueError(f"missing checker rationale for {url}")
    if not 4 <= len(samples) <= 8:
        raise ValueError(f"expected 4..8 supplemental cases for {url}, got {len(samples)}")
    seen: set[tuple[str, str]] = set()
    for sample in samples:
        if set(sample) != {"input", "expected", "name", "kind", "source", "verification"}:
            raise ValueError(f"malformed sample for {url}")
        if sample["source"] != "supplemental":
            raise ValueError(f"wrong source for {url}")
        if sample["kind"] not in {"boundary", "typical", "adversarial"}:
            raise ValueError(f"wrong case kind for {url}")
        key = sample["input"], sample["expected"]
        if key in seen:
            raise ValueError(f"duplicate supplemental case for {url}")
        seen.add(key)


def build_document() -> dict[str, object]:
    catalog = json.loads(PRACTICE_META.read_text(encoding="utf-8"))
    if len(catalog) < SLICE_SIZE:
        raise ValueError(f"practice metadata must contain at least {SLICE_SIZE} problems, got {len(catalog)}")
    entries = catalog[:SLICE_SIZE]
    registry = build_registry()
    slice_urls = [entry["url"] for entry in entries]
    if set(slice_urls) != set(registry):
        missing = sorted(set(slice_urls) - set(registry))
        extra = sorted(set(registry) - set(slice_urls))
        raise ValueError(f"practice slice A registry mismatch; missing={missing}, extra={extra}")
    items: dict[str, object] = {}
    for url in slice_urls:
        record = registry[url]
        validate_record(url, record)
        check, samples = record
        item: dict[str, object] = {"checker": check, "samples": samples}
        case_note = CASE_NOTES.get(url)
        if case_note:
            item["case_note"] = case_note
        exclusions = STATEMENT_EXCLUSIONS.get(url)
        if exclusions:
            item["exclude_statement_inputs"] = list(exclusions)
            item["exclusion_reason"] = exclusions
        items[url] = item
    return {"version": 1, "items": items}


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        raise SystemExit("usage: acm_cases_a.py [output.json]")
    output = Path(arguments[0]) if arguments else DEFAULT_OUTPUT
    document = build_document()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sample_count = sum(len(record["samples"]) for record in document["items"].values())
    print(f"wrote {len(document['items'])} problems and {sample_count} supplemental cases to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
