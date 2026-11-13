#!/usr/bin/env python3
"""Regenerate supplemental ACM cases for practice-meta indices 98..146.

The expectations in this file are produced by small, independent solvers:
brute force, direct simulation, elementary number theory, or explicit
formulas.  The metadata's reference programs are intentionally not executed or
used as the oracle.  ``--validate-only`` checks the generated contract and the
visible source samples without writing the JSON file.
"""

from __future__ import annotations

import ast
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict, deque
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
META_PATH = ROOT / "books" / "ai-exam" / "practice-meta.json"
OUTPUT_PATH = ROOT / "data" / "ai_exam" / "practice-cases-c.json"

KINDS = {"boundary", "typical", "adversarial"}


def sample(
    input_text: str,
    expected: str,
    name: str,
    kind: str,
    verification: str,
) -> dict[str, str]:
    if kind not in KINDS:
        raise ValueError(f"invalid sample kind: {kind}")
    return {
        "input": input_text,
        "expected": expected,
        "name": name,
        "kind": kind,
        "source": "supplemental",
        "verification": verification,
    }


def checker(
    mode: str,
    reason: str,
    *,
    abs_tol: float | None = None,
    rel_tol: float | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {"mode": mode, "reason": reason}
    if mode == "float":
        if abs_tol is None or rel_tol is None:
            raise ValueError("float checker requires both tolerances")
        value.update({"abs_tol": abs_tol, "rel_tol": rel_tol})
    elif abs_tol is not None or rel_tol is not None:
        raise ValueError("tolerances are only valid for float checkers")
    return value


def item(meta: dict[str, object], check: dict[str, object], samples: list[dict[str, str]]) -> dict[str, object]:
    return {"checker": check, "samples": samples}


def text_samples(
    inputs: Iterable[tuple[str, str, str]],
    runner: Callable[[str], str],
    verification: str,
) -> list[dict[str, str]]:
    rows = []
    for input_text, name, kind in inputs:
        rows.append(sample(input_text, runner(input_text), name, kind, verification))
    return rows


def ints(text: str) -> list[int]:
    return list(map(int, text.split()))


def split_nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Independent problem oracles
# ---------------------------------------------------------------------------


def solve_000(text: str) -> str:
    data = ints(text)
    pos = 0
    tests = data[pos]
    pos += 1
    answers = []
    for _ in range(tests):
        n = data[pos]
        pos += 1
        periods = data[pos : pos + n]
        pos += n
        best = 0
        for modulus in range(1, max(periods) + 1):
            eligible = sum(period % modulus == 0 for period in periods)
            best = max(best, min(modulus, eligible))
        answers.append(str(best))
    return " ".join(answers)


def solve_001(text: str) -> str:
    data = ints(text)
    n, width, limit = data[:3]
    values = tuple(data[3 : 3 + n])
    states = {values}
    best = min(values)
    for _ in range(limit):
        next_states = set(states)
        for state in states:
            for start in range(n - width + 1):
                changed = list(state)
                for index in range(start, start + width):
                    changed[index] += 1
                next_states.add(tuple(changed))
        states = next_states
        best = max(best, max(min(state) for state in states))
    return str(best)


def solve_002(text: str) -> str:
    x, wanted = ints(text)
    value = 0
    for y in range(x, max(x, wanted) + 32):
        value ^= y
        if value == wanted:
            return str(y)
    return "-1"


def minimum_number_with_length_and_sum(length: int, digit_sum: int) -> int | None:
    if digit_sum < 1 or digit_sum > 9 * length:
        return None

    @lru_cache(None)
    def possible(used: int, remaining: int) -> bool:
        if used == length:
            return remaining == 0
        return any(
            possible(used + 1, remaining - digit)
            for digit in range(0 if used else 1, 10)
            if digit <= remaining
        )

    if not possible(0, digit_sum):
        return None
    result = 0
    remaining = digit_sum
    for used in range(length):
        for digit in range(0 if used else 1, 10):
            left = length - used - 1
            if digit <= remaining and possible(used + 1, remaining - digit):
                result = result * 10 + digit
                remaining -= digit
                break
    return result


def solve_003(text: str) -> str:
    data = ints(text)
    answers = []
    for target in data[1 : 1 + data[0]]:
        found = None
        for length in range(1, 18):
            if target % length:
                continue
            candidate = minimum_number_with_length_and_sum(length, target // length)
            if candidate is not None and candidate <= 10**16:
                found = candidate
                break
        answers.append(str(-1 if found is None else found))
    return "\n".join(answers)


def all_pairs_distances(n: int, edges: list[tuple[int, int, int]]) -> list[list[int]]:
    inf = 10**30
    distance = [[inf] * n for _ in range(n)]
    for index in range(n):
        distance[index][index] = 0
    for u, v, weight in edges:
        distance[u - 1][v - 1] = min(distance[u - 1][v - 1], weight)
    for middle in range(n):
        for start in range(n):
            through = distance[start][middle]
            if through >= inf:
                continue
            for end in range(n):
                candidate = through + distance[middle][end]
                if candidate < distance[start][end]:
                    distance[start][end] = candidate
    return distance


def solve_004(text: str) -> str:
    data = ints(text)
    pos = 0
    n, directed_count, undirected_count, station = data[pos : pos + 4]
    pos += 4
    edges = []
    for _ in range(directed_count):
        edges.append(tuple(data[pos : pos + 3]))
        pos += 3
    for _ in range(undirected_count):
        u, v, weight = data[pos : pos + 3]
        pos += 3
        edges.extend(((u, v, weight), (v, u, weight)))
    hand_fee, locker_fee, delivery_count = data[pos : pos + 3]
    pos += 3
    destinations = data[pos : pos + delivery_count]
    distance = all_pairs_distances(n, edges)
    total = 0
    current = station - 1
    for destination in destinations:
        total += distance[current][destination - 1]
        total += hand_fee if total % 2 else locker_fee
        current = destination - 1
    total += distance[current][station - 1]
    return str(total)


def solve_005(text: str) -> str:
    data = ints(text)
    n, target = data[:2]
    frequencies = Counter(data[2 : 2 + n])
    keep = 0
    for value, count in frequencies.items():
        other = target - value
        if other not in frequencies:
            keep += count
        elif value * 2 == target:
            keep += min(1, count)
        elif value < other:
            keep += max(count, frequencies[other])
    return str(n - keep)


def solve_006(text: str) -> str:
    data = ints(text)
    n, first, second = data[:3]
    faces = data[3 : 3 + n]
    probability = Fraction(Counter(faces)[first] * Counter(faces)[second], n * n)
    return f"{float(1 / probability):.1f}"


def password_count(max_length: int) -> list[int]:
    # a[n], b[n], c[n]: valid strings ending in a run of length 1, 2, 3.
    a = [0] * (max_length + 1)
    b = [0] * (max_length + 1)
    c = [0] * (max_length + 1)
    total = [0] * (max_length + 1)
    if max_length:
        a[1] = 26
        total[1] = 26
    for length in range(2, max_length + 1):
        a[length] = 25 * (a[length - 1] + b[length - 1] + c[length - 1]) % (10**9 + 7)
        b[length] = a[length - 1]
        c[length] = b[length - 1]
        total[length] = (a[length] + b[length] + c[length]) % (10**9 + 7)
    return total


def solve_007(text: str) -> str:
    data = ints(text)
    queries = data[1 : 1 + data[0]]
    table = password_count(max(queries))
    return "\n".join(str(table[length]) for length in queries)


def solve_008(text: str) -> str:
    lines = split_nonempty_lines(text)
    n, food = map(int, lines[0].split())
    daily = list(map(int, lines[1].split()))
    costs = sorted(value * (n - index) for index, value in enumerate(daily))
    used = 0
    accepted = 0
    for cost in costs:
        if used + cost > food:
            break
        used += cost
        accepted += 1
    return str(accepted)


def smallest_odd_prime_brute(value: int) -> int:
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return divisor
        divisor += 2
    return value if value > 2 and value % 2 else -1


def solve_009(text: str) -> str:
    data = ints(text)
    return "\n".join(str(smallest_odd_prime_brute(value)) for value in data[1 : 1 + data[0]])


def solve_010(text: str) -> str:
    data = ints(text)
    pos = 1
    answers = []
    for _ in range(data[0]):
        x, y, left, right = data[pos : pos + 4]
        pos += 4
        step = math.gcd(x, y)
        answers.append(str(right // step - (left - 1) // step))
    return "\n".join(answers)


def solve_011(text: str) -> str:
    lines = split_nonempty_lines(text)
    pos = 1
    answers = []
    for _ in range(int(lines[0])):
        n = int(lines[pos])
        apples = list(map(int, lines[pos + 1].split()))
        candies = list(map(int, lines[pos + 2].split()))
        pos += 3
        target_a = max(apples)
        target_b = max(candies)
        answers.append(str(sum(max(target_a - a, target_b - b) for a, b in zip(apples, candies))))
    return "\n".join(answers)


def solve_013(text: str) -> str:
    lines = split_nonempty_lines(text)
    sentences = ast.literal_eval(lines[0])
    index, word = ast.literal_eval(lines[1])
    documents = [sentence.split() for sentence in sentences]
    term_frequency = documents[index].count(word) / len(documents[index])
    document_frequency = sum(word in set(document) for document in documents)
    inverse_frequency = math.log(len(documents) / (document_frequency + 1) + 1)
    return str(round(term_frequency * inverse_frequency, 3))


def matrix_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def solve_014(text: str) -> str:
    first, second, bias, features, labels = ast.literal_eval(text.strip())
    hidden_values = matrix_vector(first, [row[0] for row in features])
    hidden = [sigmoid(value + bias) for value in hidden_values]
    outputs = matrix_vector(second, hidden)
    probabilities = [sigmoid(value + bias) for value in outputs]
    loss = sum(
        -(target[0] * math.log(probability) + (1 - target[0]) * math.log(1 - probability))
        for target, probability in zip(labels, probabilities)
    )
    return str(round(loss, 3))


def solve_015(text: str) -> str:
    lines = split_nonempty_lines(text)
    if len(lines) != 3:
        raise ValueError("convolution input must contain image, kernel and six parameters")
    image = ast.literal_eval(lines[0])
    kernel = ast.literal_eval(lines[1])
    params = ast.literal_eval(lines[2])
    if not isinstance(params, list) or len(params) != 6 or not all(isinstance(value, int) for value in params):
        raise ValueError("convolution parameters must contain six integers")
    left, top, width, height, padding, stride = params
    if width != height:
        raise ValueError("convolution width must equal height")
    if not 1 <= len(image) <= 3:
        raise ValueError("convolution channel count must be in [1, 3]")
    if not 1 <= len(image[0]) <= 20 or any(len(channel) != len(image[0]) for channel in image):
        raise ValueError("convolution image must be a nonempty square matrix per channel")
    magnitude = len(image[0])
    if any(len(row) != magnitude for channel in image for row in channel):
        raise ValueError("convolution image channels must be square")
    if any(not isinstance(value, int) or not 0 <= value <= 9 for channel in image for row in channel for value in row):
        raise ValueError("convolution image values must be integers in [0, 9]")
    if len(kernel) != len(image):
        raise ValueError("convolution kernel channel count must match image")
    size = width
    if size < 1 or any(len(channel) != size for channel in kernel):
        raise ValueError("convolution kernel must be square with side matching width/height")
    if any(len(row) != size for channel in kernel for row in channel):
        raise ValueError("convolution kernel channels must be square")
    if any(not isinstance(value, int) or not -3 <= value <= 3 for channel in kernel for row in channel for value in row):
        raise ValueError("convolution kernel values must be integers in [-3, 3]")
    if not 0 <= padding <= 3 or not 1 <= stride <= 3:
        raise ValueError("convolution padding must be in [0, 3] and stride in [1, 3]")
    padded_size = magnitude + 2 * padding
    if size > padded_size:
        raise ValueError("convolution kernel cannot exceed padded image")
    if not 0 <= left <= padded_size - size or not 0 <= top <= padded_size - size:
        raise ValueError("convolution window must fit inside padded image")
    channels = len(image)
    padded = [[[0] * padded_size for _ in range(padded_size)] for _ in range(channels)]
    for channel in range(channels):
        for row in range(magnitude):
            for column in range(magnitude):
                padded[channel][row + padding][column + padding] = image[channel][row][column]
    total = 0
    for channel in range(channels):
        for row in range(size):
            for column in range(size):
                total += padded[channel][left + row][top + column] * kernel[channel][row][column]
    feature_size = (padded_size - size) // stride + 1
    return f"{total} {feature_size}"


def round_vector(values: list[float], digits: int | None) -> str:
    rendered = []
    for value in values:
        if digits is None:
            if abs(value) < 5e-13:
                rendered.append("0.")
            else:
                rendered.append(f"{value:.8g}")
        else:
            rounded = round(value, digits)
            if abs(rounded - round(rounded)) < 5e-13:
                rendered.append(f"{float(rounded):.1f}")
            else:
                rendered.append(f"{rounded:.{digits}f}".rstrip("0").rstrip("."))
    width = max(map(len, rendered), default=1)
    return "[" + " ".join(value.rjust(width) for value in rendered) + "]"


def solve_016(text: str) -> str:
    lines = split_nonempty_lines(text)
    features = ast.literal_eval(lines[0])
    targets = ast.literal_eval(lines[1])
    learning_rate = float(lines[2])
    iterations = int(lines[3])
    sample_count = len(features)
    dimension = len(features[0])
    weights = [0.0] * dimension
    for _ in range(iterations):
        residuals = [
            sum(features[row][column] * weights[column] for column in range(dimension)) - targets[row]
            for row in range(sample_count)
        ]
        gradients = [
            sum(features[row][column] * residuals[row] for row in range(sample_count)) / sample_count
            for column in range(dimension)
        ]
        weights = [weights[column] - learning_rate * gradients[column] for column in range(dimension)]
    return round_vector(weights, 4)


def transposed_product(rows: list[list[float]], residual: list[float], dimension: int) -> list[float]:
    return [sum(row[column] * error for row, error in zip(rows, residual)) for column in range(dimension)]


def solve_017(text: str) -> str:
    lines = split_nonempty_lines(text)
    features = ast.literal_eval(lines[0])
    targets = ast.literal_eval(lines[1])
    weights = [float(value) for value in ast.literal_eval(lines[2])]
    learning_rate = float(lines[3])
    iterations = int(lines[4])
    batch_size = int(lines[5])
    method = ast.literal_eval(lines[6])
    sample_count = len(features)
    dimension = len(weights)
    step = sample_count if method == "batch" else 1 if method == "stochastic" else batch_size
    for _ in range(iterations):
        for start in range(0, sample_count, step):
            rows = features[start : start + step]
            expected = targets[start : start + step]
            residual = [
                sum(row[column] * weights[column] for column in range(dimension)) - wanted
                for row, wanted in zip(rows, expected)
            ]
            gradient = transposed_product(rows, residual, dimension)
            weights = [weights[index] - learning_rate * 2.0 * gradient[index] / step for index in range(dimension)]
    return round_vector(weights, None)


def solve_018(text: str) -> str:
    lines = split_nonempty_lines(text)
    actual = ast.literal_eval(lines[0])
    predicted = ast.literal_eval(lines[1])
    beta = float(lines[2])
    true_positive = sum(a == 1 and p == 1 for a, p in zip(actual, predicted))
    false_positive = sum(a == 0 and p == 1 for a, p in zip(actual, predicted))
    false_negative = sum(a == 1 and p == 0 for a, p in zip(actual, predicted))
    if true_positive == 0:
        return "0.000"
    beta2 = beta * beta
    value = (1 + beta2) * true_positive / ((1 + beta2) * true_positive + beta2 * false_negative + false_positive)
    return f"{value:.3f}"


def solve_019(text: str) -> str:
    lines = split_nonempty_lines(text)
    n, wanted = map(int, lines[0].split())
    string = lines[1].strip()
    answer = 0
    for left in range(n):
        transitions = 0
        for right in range(left, n):
            if right > left and string[right] != string[right - 1]:
                transitions += 1
            if transitions + 1 == wanted:
                answer += 1
    return str(answer)


def parse_cards(text: str) -> list[str]:
    cards = []
    index = 0
    while index < len(text):
        if text[index] == "1":
            if index + 1 >= len(text) or text[index + 1] != "0":
                raise ValueError("10 must be encoded as '10'")
            cards.append("10")
            index += 2
        else:
            cards.append(text[index])
            index += 1
    return cards


def solve_020(text: str) -> str:
    cards = parse_cards(text.strip())
    hands = [deque(cards[::2]), deque(cards[1::2])]
    table: list[str] = []
    current = 0
    while hands[0] and hands[1]:
        card = hands[current].popleft()
        collected = False
        if card == "J" and table:
            table.append(card)
            while table:
                hands[current].append(table.pop())
            collected = True
        elif card != "J" and card in table:
            matching = table.index(card)
            table.append(card)
            while len(table) > matching:
                hands[current].append(table.pop())
            collected = True
        else:
            table.append(card)
        if not collected:
            current = 1 - current
    winner = 0 if hands[0] else 1
    name = ("sanqiu", "xiran")[winner]
    return name + "\n" + " ".join(hands[winner])


def solve_021(text: str) -> str:
    data = ints(text)
    pos = 0
    test_count = data[pos]
    pos += 1
    output = []
    for _ in range(test_count):
        n, operation_count = data[pos : pos + 2]
        pos += 2
        values = data[pos : pos + n]
        pos += n
        for _ in range(operation_count):
            operation = data[pos]
            pos += 1
            if operation == 1:
                index, value = data[pos : pos + 2]
                pos += 2
                values[index - 1] = value
            else:
                total = 0
                for left in range(n):
                    for right in range(left + 1, n):
                        total += abs(values[left] - values[right])
                output.append(str(total))
    return "\n".join(output)


def totient(value: int) -> int:
    result = value
    factor = 2
    while factor * factor <= value:
        if value % factor == 0:
            result = result // factor * (factor - 1)
            while value % factor == 0:
                value //= factor
        factor += 1
    if value > 1:
        result = result // value * (value - 1)
    return result


def sum_of_gcds(a: int, b: int, left: int, right: int) -> int:
    if a == b:
        count = right - left + 1
        return (a + left + a + right) * count // 2
    difference = abs(a - b)
    answer = 0
    divisor = 1
    while divisor * divisor <= difference:
        if difference % divisor == 0:
            for current in {divisor, difference // divisor}:
                # gcd(a+i,b+i)=g iff g divides a+i and g divides b-a.
                low = a + left
                high = a + right
                count = high // current - (low - 1) // current
                answer += totient(current) * count
        divisor += 1
    return answer % (10**9 + 7)


def solve_022(text: str) -> str:
    data = ints(text)
    if not data or not 1 <= data[0] <= 100:
        raise ValueError("test case count must be in [1, 100]")
    if len(data) != 1 + 4 * data[0]:
        raise ValueError("each gcd-range test case must contain four integers")
    pos = 1
    output = []
    for _ in range(data[0]):
        a, b, left, right = data[pos : pos + 4]
        pos += 4
        if not 1 <= a <= 100_000 or not 1 <= b <= 100_000:
            raise ValueError("gcd-range bases must be positive integers up to 100000")
        if not 0 <= left <= right <= 10**18:
            raise ValueError("gcd-range indices must satisfy 0 <= left <= right <= 10^18")
        output.append(str(sum_of_gcds(a, b, left, right)))
    return "\n".join(output)


def solve_023(text: str) -> str:
    lines = split_nonempty_lines(text)
    n, high, position, direction = lines[0].split()
    high = int(high)
    position = int(position)
    directions = list(map(int, lines[1].split()))
    if position == 0 and direction == "L":
        direction = "R"
    elif position == high and direction == "R":
        direction = "L"
    collisions = 0
    for distance in directions[: int(n)]:
        for _ in range(distance):
            position += 1 if direction == "R" else -1
            if position == 0 or position == high:
                collisions += 1
                direction = "R" if position == 0 else "L"
    return f"{collisions} {position} {direction}"


def solve_024(text: str) -> str:
    lines = split_nonempty_lines(text)
    pos = 1
    output = []
    for _ in range(int(lines[0])):
        n = int(lines[pos])
        values = list(map(int, lines[pos + 1].split()))
        query_count = int(lines[pos + 2])
        pos += 3

        def pattern(items: Iterable[object]) -> list[int]:
            mapping: dict[object, int] = {}
            encoded = []
            for value in items:
                if value not in mapping:
                    mapping[value] = len(mapping)
                encoded.append(mapping[value])
            return encoded

        expected = pattern(values)
        for _ in range(query_count):
            candidate = lines[pos]
            pos += 1
            output.append("YES" if len(candidate) == n and pattern(candidate) == expected else "NO")
    return "\n".join(output)


def solve_025(text: str) -> str:
    data = ints(text)
    n, regions = data[:2]
    values = data[2 : 2 + n]
    best = 10**30
    for cuts in itertools.combinations(range(1, n), regions - 1):
        boundaries = (0, *cuts, n)
        spread = 0
        for left, right in zip(boundaries, boundaries[1:]):
            spread += max(values[left:right]) - min(values[left:right])
        best = min(best, spread)
    return str(best)


def solve_026(text: str) -> str:
    server_services: dict[int, set[str]] = defaultdict(set)
    running: Counter[str] = Counter()
    dependencies: dict[str, set[str]] = defaultdict(set)
    output = []

    def available(name: str, visiting: set[str]) -> bool:
        if running[name] <= 0:
            return False
        if name in visiting:
            return True
        visiting.add(name)
        result = all(available(child, visiting) for child in dependencies[name])
        visiting.remove(name)
        return result

    for line in split_nonempty_lines(text):
        expression = ast.parse(line, mode="eval").body
        if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
            raise ValueError(f"unsupported service operation: {line}")
        function = expression.func.id
        arguments = [ast.literal_eval(argument) for argument in expression.args]
        if function == "ServiceWgSys":
            server_services.clear()
            running.clear()
            dependencies.clear()
            output.append("null")
        elif function == "rebootServers":
            for server in arguments[0]:
                for service in list(server_services[server]):
                    running[service] -= 1
                server_services[server].clear()
            output.append("null")
        elif function == "startService":
            server, service = arguments
            if service in server_services[server]:
                output.append("false")
            else:
                server_services[server].add(service)
                running[service] += 1
                output.append("true")
        elif function == "addDependency":
            source, target = arguments
            if target in dependencies[source]:
                output.append("false")
            else:
                dependencies[source].add(target)
                output.append("true")
        elif function == "isServiceAvailable":
            output.append("true" if available(arguments[0], set()) else "false")
        else:
            raise ValueError(f"unknown service operation: {function}")
    return "\n".join(output)


def solve_027(text: str) -> str:
    data = ints(text)
    records, query_count = data[:2]
    pos = 2
    pairs: Counter[tuple[int, int]] = Counter()
    for _ in range(records):
        count = data[pos]
        pos += 1
        products = sorted(set(data[pos : pos + count]))
        pos += count
        for first, second in itertools.combinations(products, 2):
            pairs[(first, second)] += 1
    thresholds = data[pos : pos + query_count]
    frequencies = sorted(pairs.values())
    output = []
    for threshold in thresholds:
        output.append(str(sum(frequency >= threshold for frequency in frequencies)))
    return "\n".join(output)


def solve_028(text: str) -> str:
    lines = split_nonempty_lines(text)
    values = [int(value) for value in "".join(lines[1:]).split("-") if value]
    totals = [0] * len(values)
    for index in range(len(values) - 1, -1, -1):
        if values[index] == -1:
            totals[index] = -1
            continue
        total = values[index]
        for child in (2 * index + 1, 2 * index + 2):
            if child < len(values) and values[child] != -1:
                total += totals[child]
        totals[index] = total
    return "-".join(map(str, totals))


def solve_029(text: str) -> str:
    data = ints(text)
    n = data[0]
    points = [(data[index], data[index + 1]) for index in range(1, 1 + 2 * n, 2)]
    if n < 2:
        return "0.0000"
    best = min(
        (x1 - x2) ** 2 + (y1 - y2) ** 2
        for (x1, y1), (x2, y2) in itertools.combinations(points, 2)
    )
    return f"{math.sqrt(best):.4f}"


def solve_030(text: str) -> str:
    data = ints(text)
    pos = 1
    output = []
    for _ in range(data[0]):
        n, k = data[pos : pos + 2]
        pos += 2
        values = data[pos : pos + n]
        pos += n
        best: tuple[int, tuple[int, ...], list[tuple[int, int]]] | None = None
        for cuts in itertools.combinations(range(1, n), k - 1):
            boundaries = (0, *cuts, n)
            maxima = [max(values[left:right]) for left, right in zip(boundaries, boundaries[1:])]
            spread = max(maxima) - min(maxima)
            intervals = [(left + 1, right) for left, right in zip(boundaries, boundaries[1:])]
            flattened = tuple(value for interval in intervals for value in interval)
            candidate = (spread, flattened, intervals)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        assert best is not None
        output.extend(f"{left} {right}" for left, right in best[2])
    return "\n".join(output)


def solve_031(text: str) -> str:
    data = ints(text)
    n = data[0]
    sequence = data[1 : 1 + n]
    waiting: set[int] = set()
    introduced = 0
    gate_one = 0
    for train in sequence:
        waiting.update(range(introduced + 1, train + 1))
        introduced = max(introduced, train)
        if not waiting:
            return "-1"
        low, high = min(waiting), max(waiting)
        if train == high:
            waiting.remove(train)
            gate_one += 1
        elif train == low:
            waiting.remove(train)
        else:
            return "-1"
    return str(gate_one)


def solve_032(text: str) -> str:
    lines = split_nonempty_lines(text)
    pos = 1
    output = []
    for _ in range(int(lines[0])):
        n = int(lines[pos])
        tunnel = lines[pos + 1]
        pos += 2
        start = tunnel.find("D")
        if start < 0:
            output.append("NO")
        elif start == 0 or start == n - 1:
            output.append("YES")
        else:
            left = start
            right = start
            while left > 0 and tunnel[left - 1] != "#":
                left -= 1
            while right + 1 < n and tunnel[right + 1] != "#":
                right += 1
            output.append("YES" if right - left + 1 >= 2 else "NO")
    return "\n".join(output)


def solve_033(text: str) -> str:
    lines = split_nonempty_lines(text)
    required = {"D", "M", "T", "A", "O"}
    pos = 1
    output = []
    for _ in range(int(lines[0])):
        auxiliary_limit = int(lines[pos])
        string = lines[pos + 1]
        pos += 2
        answer = 0
        for left in range(len(string)):
            colors: set[str] = set()
            auxiliary = 0
            for right in range(left, len(string)):
                character = string[right]
                if character in required:
                    colors.add(character)
                else:
                    auxiliary += 1
                if auxiliary > auxiliary_limit:
                    break
                if auxiliary == auxiliary_limit and colors == required:
                    answer += 1
        output.append(str(answer))
    return "\n".join(output)


def solve_034(text: str) -> str:
    lines = split_nonempty_lines(text)
    output = []
    for string in lines[1 : 1 + int(lines[0])]:
        total_zero = string.count("0")
        total_one = len(string) - total_zero
        answer = len(string)
        for length in range(len(string), -1, -1):
            zeros_in_prefix = string[:length].count("0")
            ones_in_prefix = length - zeros_in_prefix
            if total_one >= zeros_in_prefix and total_zero >= ones_in_prefix:
                answer = len(string) - length
                break
        output.append(str(answer))
    return "\n".join(output)


def solve_035(text: str) -> str:
    data = ints(text)
    n, players, rounds = data[:3]
    happiness = data[3 : 3 + n]
    totals = [0] * players
    riders = min(n, players)
    for round_index in range(rounds):
        start = (round_index * n) % players
        for pod in range(riders):
            totals[(start + pod) % players] += happiness[pod]
    winner = max(range(players), key=lambda index: (totals[index], -index))
    return str(winner + 1)


def solve_036(text: str) -> str:
    n = int(text.strip())
    value = 1
    for factor in range(2, min(n, 4) + 1):
        value *= factor
    return str(0 if n >= 5 else value % 10)


def solve_037(text: str) -> str:
    data = ints(text)
    output = []
    pos = 1
    for _ in range(data[0]):
        total, odd_primes = data[pos : pos + 2]
        pos += 2
        if total >= 3 * odd_primes and (total - odd_primes) % 2 == 0:
            output.append(str((total - odd_primes) // 2))
        else:
            output.append("-1")
    return "\n".join(output)


def solve_039(text: str) -> str:
    data = ints(text)
    pos = 1
    output = []
    for _ in range(data[0]):
        n = data[pos]
        pos += 1
        values = [0, *data[pos : pos + n]]
        pos += n
        query_count = data[pos]
        pos += 1
        queries = data[pos : pos + query_count]
        pos += query_count
        for mask in queries:
            output.append(str(sum(values[index] for index in range(1, n + 1) if index & mask == index)))
    return "\n".join(output)


def solve_040(text: str) -> str:
    data = ints(text)
    pos = 0
    test_count = data[pos]
    pos += 1
    output = []
    for _ in range(test_count):
        duration, _, release_count, kill_count = data[pos : pos + 4]
        pos += 4
        releases = data[pos : pos + release_count]
        pos += release_count
        kills = data[pos : pos + kill_count]
        pos += kill_count
        best = max(
            sum(release <= moment < release + duration for moment in kills)
            for release in releases
        )
        output.append(str(best))
    return "\n".join(output)


def point_in_triangle(triangle: list[tuple[float, float]], x: float, y: float) -> bool:
    signs = []
    for (ax, ay), (bx, by) in zip(triangle, triangle[1:] + triangle[:1]):
        signs.append((bx - ax) * (y - ay) - (by - ay) * (x - ax))
    epsilon = 1e-12
    return all(value >= -epsilon for value in signs) or all(value <= epsilon for value in signs)


def solve_041(text: str) -> str:
    tokens = text.split()
    pos = 0
    n, m, samples_per_axis = map(int, tokens[:3])
    pos = 3
    triangle = []
    for _ in range(3):
        triangle.append((float(tokens[pos]), float(tokens[pos + 1])))
        pos += 2
    histogram = [0] * (samples_per_axis * samples_per_axis + 1)
    for pixel_x in range(n):
        for pixel_y in range(m):
            covered = 0
            for sx in range(samples_per_axis):
                for sy in range(samples_per_axis):
                    x = pixel_x + (sx + 0.5) / samples_per_axis
                    y = pixel_y + (sy + 0.5) / samples_per_axis
                    covered += point_in_triangle(triangle, x, y)
            histogram[covered] += 1
    return " ".join(map(str, histogram))


def nearest_exit_distances(
    n: int,
    m: int,
    exits: list[tuple[int, int]],
    grid: list[str],
) -> list[list[int]]:
    inf = 10**9
    distance = [[inf] * m for _ in range(n)]
    queue: deque[tuple[int, int]] = deque()
    for x, y in exits:
        row, column = y - 1, x - 1
        if grid[row][column] != "#" and distance[row][column] == inf:
            distance[row][column] = 0
            queue.append((row, column))
    while queue:
        row, column = queue.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, column + dc
            if 0 <= nr < n and 0 <= nc < m and grid[nr][nc] != "#" and distance[nr][nc] == inf:
                distance[nr][nc] = distance[row][column] + 1
                queue.append((nr, nc))
    return distance


def solve_042(text: str) -> str:
    lines = split_nonempty_lines(text)
    pos = 1
    output = []
    for _ in range(int(lines[0])):
        n, m, egg_count, exit_count, initial_energy = map(int, lines[pos].split())
        pos += 1
        eggs = []
        for _ in range(egg_count):
            x, y, requirement, carried = map(int, lines[pos].split())
            pos += 1
            eggs.append((x, y, requirement, carried))
        exits = []
        for _ in range(exit_count):
            x, y = map(int, lines[pos].split())
            pos += 1
            exits.append((x, y))
        grid = lines[pos : pos + n]
        pos += n
        distance = nearest_exit_distances(n, m, exits, grid)
        egg_data = []
        impossible = False
        for x, y, requirement, carried in eggs:
            steps = distance[y - 1][x - 1]
            if steps >= 10**9 or steps > carried:
                impossible = True
                break
            egg_data.append((steps, requirement, carried))
        if impossible:
            output.append("-1")
            continue
        feasible_permutation = None
        for permutation in itertools.permutations(egg_data):
            energy = initial_energy
            feasible = True
            for steps, requirement, carried in permutation:
                if energy < requirement:
                    feasible = False
                    break
                energy += carried - steps
            if feasible:
                feasible_permutation = permutation
                break
        if feasible_permutation is None:
            output.append("-1")
        else:
            output.append(str(sum(steps for steps, _, _ in feasible_permutation)))
    return "\n".join(output)


def solve_046(text: str) -> str:
    lines = split_nonempty_lines(text)
    output = []
    for number in lines[1 : 1 + int(lines[0])]:
        best_sum = -1
        best_value = "0"
        for index, character in enumerate(number):
            digit = int(character)
            if digit == 0:
                continue
            candidate = number[:index] + str(digit - 1) + "9" * (len(number) - index - 1)
            candidate = candidate.lstrip("0") or "0"
            digit_sum = sum(map(int, candidate))
            if digit_sum > best_sum:
                best_sum = digit_sum
                best_value = candidate
        output.append(best_value)
    return "\n".join(output)


def solve_047(text: str) -> str:
    data = ints(text)
    pos = 0
    test_count = data[pos]
    pos += 1
    output = []
    for _ in range(test_count):
        robot_count, station_count = data[pos : pos + 2]
        pos += 2
        robots = data[pos : pos + robot_count]
        pos += robot_count
        stations = data[pos : pos + station_count]
        pos += station_count
        capacities = data[pos : pos + station_count]
        pos += station_count
        if sum(capacities) < robot_count:
            output.append("-1")
            continue

        def feasible(limit: int) -> bool:
            remaining = capacities[:]
            order = sorted(
                range(robot_count),
                key=lambda robot: sum(abs(robots[robot] - station) <= limit for station in stations),
            )

            def assign(depth: int) -> bool:
                if depth == robot_count:
                    return True
                robot = order[depth]
                for station in sorted(range(station_count), key=lambda index: abs(robots[robot] - stations[index])):
                    if remaining[station] and abs(robots[robot] - stations[station]) <= limit:
                        remaining[station] -= 1
                        if assign(depth + 1):
                            return True
                        remaining[station] += 1
                return False

            return assign(0)

        candidates = sorted({abs(robot - station) for robot in robots for station in stations})
        low, high = 0, len(candidates) - 1
        answer = -1
        while low <= high:
            middle = (low + high) // 2
            if feasible(candidates[middle]):
                answer = candidates[middle]
                high = middle - 1
            else:
                low = middle + 1
        output.append(str(answer))
    return "\n".join(output)


def solve_048(text: str) -> str:
    data = ints(text)
    pos = 0
    n = data[pos]
    pos += 1
    starts = data[pos : pos + n]
    pos += n
    distance = [data[pos + row * n : pos + (row + 1) * n] for row in range(n)]
    best = 10**30
    for order in itertools.permutations(range(n)):
        first = order[0]
        if starts[first] == -1:
            continue
        if starts[first] < 0:
            raise ValueError("only -1 may mark a missing start edge")
        total = starts[first]
        valid = True
        for previous, current in zip(order, order[1:]):
            edge = distance[previous][current]
            if edge == -1:
                valid = False
                break
            if edge < 0:
                raise ValueError("only -1 may mark a missing city edge")
            total += edge
        if valid:
            best = min(best, total)
    return str(-1 if best >= 10**30 else best)


def solve_012_window_distinct(text: str) -> str:
    lines = split_nonempty_lines(text)
    n, k = map(int, lines[0].split())
    values = list(map(int, lines[1].split()))
    if len(values) != n:
        raise ValueError(f"expected {n} values, got {len(values)}")
    for candidate in itertools.permutations(sorted(values)):
        valid = True
        for start in range(n):
            window = candidate[start : start + k]
            if len(window) != len(set(window)):
                valid = False
                break
        if valid:
            return " ".join(map(str, candidate))
    return "-1"


RUNNERS: dict[int, Callable[[str], str]] = {
    0: solve_000,
    1: solve_001,
    2: solve_002,
    3: solve_003,
    4: solve_004,
    5: solve_005,
    6: solve_006,
    7: solve_007,
    8: solve_008,
    9: solve_009,
    10: solve_010,
    11: solve_011,
    12: solve_012_window_distinct,
    13: solve_013,
    14: solve_014,
    15: solve_015,
    16: solve_016,
    17: solve_017,
    18: solve_018,
    19: solve_019,
    20: solve_020,
    21: solve_021,
    22: solve_022,
    23: solve_023,
    24: solve_024,
    25: solve_025,
    26: solve_026,
    27: solve_027,
    28: solve_028,
    29: solve_029,
    30: solve_030,
    31: solve_031,
    32: solve_032,
    33: solve_033,
    34: solve_034,
    35: solve_035,
    36: solve_036,
    37: solve_037,
    39: solve_039,
    40: solve_040,
    41: solve_041,
    42: solve_042,
    43: solve_040,
    44: solve_041,
    45: solve_042,
    46: solve_046,
    47: solve_047,
    48: solve_048,
}


def case(input_text: str, name: str, kind: str) -> tuple[str, str, str]:
    return input_text, name, kind


def perceptron_input(
    first: list[list[float]],
    second: list[list[float]],
    bias: float,
    features: list[list[float]],
    labels: list[list[int]],
) -> str:
    return repr((first, second, bias, features, labels))


def convolution_input(
    image: list[list[list[int]]],
    kernel: list[list[list[int]]],
    parameters: list[int],
) -> str:
    return f"{image!r}\n{kernel!r}\n{parameters!r}"


def service_input(*events: str) -> str:
    return "\n".join(events)


def triangle_input(
    n: int,
    m: int,
    subdivisions: int,
    triangle: list[tuple[float, float]],
) -> str:
    points = "\n".join(f"{x} {y}" for x, y in triangle)
    return f"{n} {m} {subdivisions}\n{points}"


def maze_data(
    n: int,
    m: int,
    initial_energy: int,
    eggs: list[tuple[int, int, int, int]],
    exits: list[tuple[int, int]],
    grid: list[str],
) -> str:
    lines = ["1", f"{n} {m} {len(eggs)} {len(exits)} {initial_energy}"]
    lines.extend(f"{x} {y} {requirement} {carried}" for x, y, requirement, carried in eggs)
    lines.extend(f"{x} {y}" for x, y in exits)
    lines.extend(grid)
    return "\n".join(lines)


def build_case_specs() -> dict[int, list[tuple[str, str, str]]]:
    return {
        0: [
            case("1\n1 1", "单个周期一", "boundary"),
            case("1\n3 2 4 8", "整除链", "typical"),
            case("1\n4 6 6 10 15", "重复周期与并列", "adversarial"),
            case("1\n4 5 7 11 13", "互异素数周期", "boundary"),
            case("2\n3 1 2 3\n4 8 8 4 2", "多组一般周期", "typical"),
        ],
        1: [
            case("1 1 1\n5", "单点单次加一", "boundary"),
            case("3 1 2\n0 0 0", "单点窗口重复操作", "typical"),
            case("3 2 1\n5 0 1", "窗口只能部分补足", "boundary"),
            case("4 4 2\n-2 3 0 1", "全数组窗口与负数", "adversarial"),
            case("5 2 4\n0 5 0 0 5", "两端高值中间补足", "typical"),
        ],
        2: [
            case("0 0", "从零开始", "boundary"),
            case("1 0", "最短非平凡零异或", "typical"),
            case("5 7", "一般前缀区间", "typical"),
            case("0 2", "无解异或值", "adversarial"),
            case("100 123", "较大起点", "boundary"),
        ],
        3: [
            case("1\n1", "一位数最小", "boundary"),
            case("1\n9", "一位数上界", "boundary"),
            case("1\n20", "两位构造", "typical"),
            case("1\n23", "不可行目标", "adversarial"),
            case("1\n2500", "合法目标上界", "boundary"),
        ],
        4: [
            case("1 0 0 1\n1 2 1\n1", "单村自投递", "boundary"),
            case("2 0 1 1\n1 2 2\n3 4 2\n2 1", "双向道路往返", "typical"),
            case("3 3 0 1\n1 2 1\n2 3 1\n3 1 1\n1 0 3\n2 3 1", "有向环多次配送", "typical"),
            case("3 2 1 2\n1 2 4\n2 3 1\n1 3 10\n2 5 2\n3 1", "混合道路与奇偶附加耗时", "adversarial"),
            case("4 0 3 1\n1 2 1\n2 3 3\n3 4 2\n4 1 4\n4 2 4 3", "链式图重复目的地", "typical"),
        ],
        5: [
            case("1 2\n1", "单个按钮无冲突", "boundary"),
            case("2 3\n1 2", "唯一冲突对", "typical"),
            case("4 4\n2 2 2 1", "半目标和重复值", "adversarial"),
            case("5 5\n0 5 0 5 2", "含零且两侧数量相等", "boundary"),
            case("6 7\n3 4 3 4 3 4", "多组等价互补对", "typical"),
        ],
        6: [
            case("2 0 1\n0 1", "两面骰子", "boundary"),
            case("3 0 1\n0 0 1", "目标面频次不等", "typical"),
            case("4 0 1\n0 0 0 1", "低成功概率", "boundary"),
            case("5 0 1\n0 1 1 1 2", "多位面一般频次", "typical"),
            case("6 0 1\n0 0 1 1 2 2", "对称频次", "adversarial"),
        ],
        7: [
            case("1\n1", "长度一", "boundary"),
            case("1\n2", "长度二", "boundary"),
            case("1\n3", "恰未出现四连", "typical"),
            case("1\n4", "首个非法四连", "adversarial"),
            case("3\n5\n10\n26", "多长度一般情况", "typical"),
        ],
        8: [
            case("1 4\n3", "一天一位客人", "boundary"),
            case("2 5\n1 4", "只能接待一人", "boundary"),
            case("4 6\n1 1 1 1", "四人中等食物", "typical"),
            case("4 1\n1 1 1 1", "食物仅够最便宜一人", "adversarial"),
            case("5 100\n1 1 1 1 1", "全部可接待", "typical"),
        ],
        9: [
            case("1\n1", "一没有奇质因数", "boundary"),
            case("1\n2", "二的幂无奇质因数", "boundary"),
            case("1\n15", "两个奇质因数取小", "typical"),
            case("1\n49", "奇合数", "typical"),
            case("1\n77", "两个素因子", "adversarial"),
        ],
        10: [
            case("1\n2 3 -5 5", "负区间", "boundary"),
            case("1\n4 6 1 15", "公因数二", "typical"),
            case("1\n6 9 0 0", "仅包含零", "boundary"),
            case("1\n12 18 -20 -1", "负区间倍数", "adversarial"),
            case("2\n1 7 10 30\n5 10 -3 17", "多组一般情况", "typical"),
        ],
        11: [
            case("1\n1\n3\n4", "单盒无需补足", "boundary"),
            case("1\n2\n1 3\n3 1", "两个维度目标不同", "typical"),
            case("1\n3\n1 3 5\n5 1 3", "交错极值", "adversarial"),
            case("1\n3\n2 2 2\n2 2 2", "全部相同", "boundary"),
            case("2\n2\n1 2\n2 1\n3\n1 5 9\n9 5 1", "多组一般情况", "typical"),
        ],
        12: [
            case("1 1\n7", "单元素唯一重排", "boundary"),
            case("2 2\n1 1", "两相同元素无法互异", "boundary"),
            case("3 2\n1 1 1", "三重元素无法间隔", "boundary"),
            case("4 2\n1 1 2 2", "最高频次两值恰好填满", "typical"),
            case("7 3\n1 1 1 2 2 3 3", "单一最高频次紧界", "boundary"),
            case("6 3\n1 1 2 2 3 3", "三个最高频次并列紧界", "adversarial"),
            case("6 6\n6 5 4 3 2 1", "窗口等于长度且值互异", "boundary"),
            case("8 3\n1 1 1 2 2 3 3 4", "重复与独值混合的一般情况", "typical"),
        ],
        13: [
            case("['apple']\n[0, 'apple']", "单文档", "boundary"),
            case("['apple Apple apple', 'Apple']\n[0, 'apple']", "区分大小写", "adversarial"),
            case("['apple apple banana', 'apple', 'Banana apple']\n[0, 'apple']", "同句重复只计一个文档", "typical"),
            case("['a b c', 'b c', 'c']\n[2, 'c']", "末文档短句", "typical"),
            case("['red green', 'blue red', 'green blue', 'red blue']\n[3, 'blue']", "四文档", "typical"),
        ],
        14: [
            case(perceptron_input([[0.0]], [[0.0]], 0.0, [[0.0]], [[0.0]]), "零权重单节点", "boundary"),
            case(perceptron_input([[0.5]], [[-0.25]], 0.1, [[0.2]], [[1.0]]), "单隐层正标签", "typical"),
            case(perceptron_input([[0.2, -0.1], [0.4, 0.3]], [[0.5, -0.6]], -0.1, [[0.3], [-0.2]], [[1.0]]), "二维特征", "typical"),
            case(perceptron_input([[0.1], [0.2]], [[1.0, -1.0], [-1.0, 1.0]], 0.0, [[0.4]], [[1.0], [0.0]]), "多输出损失求和", "adversarial"),
            case(perceptron_input([[-0.3]], [[0.7]], 0.2, [[-0.4]], [[0.0]]), "包含负值", "boundary"),
        ],
        15: [
            case(convolution_input([[[5]]], [[[2]]], [0, 0, 1, 1, 0, 1]), "单通道单格", "boundary"),
            case(convolution_input([[[1, 2], [3, 4]]], [[[1, 0], [0, 1]]], [0, 0, 2, 2, 0, 1]), "迹卷积", "typical"),
            case(convolution_input([[[1, 2], [3, 4]]], [[[1, 1], [1, 1]]], [1, 1, 2, 2, 1, 1]), "填充边缘检查", "boundary"),
            case(convolution_input([[[1, 2], [3, 4]], [[4, 3], [2, 1]]], [[[1, 0], [0, -1]], [[-1, 1], [1, -1]]], [0, 0, 2, 2, 0, 2]), "双通道负核", "adversarial"),
            case(convolution_input([[[1, 2, 3], [4, 5, 6], [7, 8, 9]]], [[[0, 1, 0], [1, -3, 1], [0, 1, 0]]], [1, 1, 3, 3, 1, 1]), "四邻域边缘核", "typical"),
        ],
        16: [
            case("[[1, 0]]\n[0]\n0.1\n1", "零目标零梯度", "boundary"),
            case("[[1, 0], [1, 1]]\n[1, 1]\n0.1\n1", "常数值拟合", "typical"),
            case("[[1, 1], [1, 2], [1, 3]]\n[1, 2, 4]\n0.03\n12", "短序列迭代", "typical"),
            case("[[1, -1], [1, 0], [1, 1]]\n[-1, 0, 1]\n0.05\n25", "负特征线性关系", "adversarial"),
            case("[[1, 0.5], [1, -0.5]]\n[2, 0]\n0.02\n7", "小样本少迭代", "boundary"),
        ],
        17: [
            case("[[1]]\n[1]\n[0]\n0.01\n1\n1\n'batch'", "批量一步", "boundary"),
            case("[[1], [2]]\n[2, 4]\n[0]\n0.01\n1\n1\n'stochastic'", "随机法实际顺序更新", "typical"),
            case("[[1], [2], [3]]\n[1, 2, 4]\n[0]\n0.005\n2\n2\n'mini_batch'", "存在尾批", "boundary"),
            case("[[1, 0], [1, 1], [1, 2]]\n[0, 1, 2]\n[0.5, -0.5]\n0.01\n3\n3\n'batch'", "二维批量", "typical"),
            case("[[1, 1], [2, 1]]\n[3, 6]\n[1, -1]\n0.002\n4\n1\n'mini_batch'", "多样本单批次", "adversarial"),
        ],
        18: [
            case("[1]\n[1]\n1.0", "完全命中", "boundary"),
            case("[0, 0]\n[1, 1]\n1.0", "无真正例", "boundary"),
            case("[1, 1, 0, 0]\n[1, 0, 1, 1]\n1.5", "含假阳性", "typical"),
            case("[1, 1, 0]\n[1, 0, 0]\n2.0", "强调召回率", "typical"),
            case("[0, 1, 1, 0, 1]\n[0, 1, 0, 1, 1]\n0.5", "低于一的 beta", "adversarial"),
        ],
        19: [
            case("1 1\n0", "单字符一次按键", "boundary"),
            case("2 2\n01", "两字符两次按键", "boundary"),
            case("4 1\n0011", "仅单段子串", "typical"),
            case("6 2\n001010", "多次交替与单次", "typical"),
            case("7 4\n0101010", "按键次数超过段数", "adversarial"),
        ],
        20: [
            case("AA", "相同牌收回", "typical"),
            case("AB", "打空手牌直接结束", "boundary"),
            case("JA", "空钩后普通收牌", "typical"),
            case("A2A", "中间牌被一并收走", "typical"),
            case("A10A", "十的解析", "boundary"),
        ],
        21: [
            case("1\n3 1\n1 2 4\n2", "单次查询", "boundary"),
            case("1\n2 2\n-1 1\n2\n1 1 -1", "负数修改", "boundary"),
            case("1\n4 3\n2 2 2 2\n2\n1 3 9\n2", "重复值修改", "adversarial"),
            case("1\n1 2\n5\n2\n1 1 100", "长度为一下修改", "boundary"),
            case("2\n3 2\n1 3 6\n1 2 8\n2\n2 1\n0 0\n2", "多组一般情况", "typical"),
        ],
        22: [
            case("1\n7 7 3 5", "相等基准值", "boundary"),
            case("1\n10 12 0 3", "从索引零开始", "typical"),
            case("1\n1 4 0 6", "多档公约数混合", "adversarial"),
            case("1\n5 17 10 10", "单点区间", "boundary"),
            case("2\n6 20 5 8\n100000 1 0 1000000000000000000", "多组含超大指数上界", "typical"),
        ],
        23: [
            case("1 5 0 L\n5", "左下起点修正后撞右端", "boundary"),
            case("1 5 5 R\n5", "右上起点修正后撞左端", "boundary"),
            case("2 4 1 L\n3 0", "含零工单", "boundary"),
            case("1 5 2 R\n8", "多次折返", "adversarial"),
            case("3 8 2 L\n3 6 10", "多工单一般情况", "typical"),
        ],
        24: [
            case("1\n1\n7\n2\na\nb", "单元素双字符串", "boundary"),
            case("1\n3\n1 1 2\n3\naab\nabb\naba", "重复数字映射", "typical"),
            case("1\n3\n1 2 1\n2\naba\naab", "隔位重复映射", "typical"),
            case("1\n4\n-1 0 -1 5\n2\nabca\nabba", "含负数与错长度", "adversarial"),
            case("2\n2\n1 2\n1\nab\n3\n5 5 6\n2\nbcc\naaa", "多组独立", "typical"),
        ],
        25: [
            case("3 3\n1 9 2", "每个元素单独成区", "boundary"),
            case("3 1\n1 9 2", "整段一个区", "boundary"),
            case("4 2\n3 2 5 1", "两区一般划分", "typical"),
            case("5 2\n5 5 5 5 5", "全部相等", "adversarial"),
            case("6 3\n10 2 7 7 2 10", "重复并列极值", "typical"),
        ],
        26: [
            case(service_input("ServiceWgSys()", "startService(1, \"A\")", "isServiceAvailable(\"A\")", "isServiceAvailable(\"B\")"), "启动与未知服务", "boundary"),
            case(service_input("ServiceWgSys()", "startService(1, \"B\")", "startService(2, \"B\")", "isServiceAvailable(\"A\")", "addDependency(\"A\", \"B\")", "startService(1, \"A\")", "isServiceAvailable(\"A\")", "addDependency(\"A\", \"B\")"), "依赖启动与重复依赖", "typical"),
            case(service_input("ServiceWgSys()", "startService(2, \"A\")", "isServiceAvailable(\"A\")", "rebootServers([2])", "isServiceAvailable(\"A\")", "startService(2, \"A\")"), "重启后服务停止", "boundary"),
            case(service_input("ServiceWgSys()", "startService(1, \"B\")", "startService(2, \"B\")", "rebootServers([1])", "isServiceAvailable(\"B\")", "rebootServers([2])", "isServiceAvailable(\"B\")"), "多实例可用性", "typical"),
            case(service_input("ServiceWgSys()", "addDependency(\"A\", \"B\")", "startService(3, \"A\")", "isServiceAvailable(\"A\")", "startService(4, \"B\")", "isServiceAvailable(\"A\")"), "依赖未运行阻断服务", "adversarial"),
        ],
        27: [
            case("2 2\n2 1 2\n2 1 3\n1\n2", "两个用户的一条共现", "boundary"),
            case("2 2\n3 1 1 2\n2 2 1\n1\n2", "单条记录去重", "adversarial"),
            case("3 2\n1 1\n1 2\n1 3\n1\n2", "单商品不生成对", "boundary"),
            case("5 2\n3 1 2 4\n1 5\n2 2 4\n1 3\n2 1 3\n1\n2", "五记录一般共现", "typical"),
            case("3 3\n3 1 2 3\n3 1 2 3\n3 1 2 3\n1\n2\n4", "所有对同频", "typical"),
        ],
        28: [
            case("1\n10", "根节点单目录", "boundary"),
            case("3\n10-4-4", "二叉树两个孩子", "typical"),
            case("3\n1-2-3", "根汇总", "typical"),
            case("3\n1-2", "缺少右侧孩子", "boundary"),
            case("3\n9-2-4", "不平衡的叶值", "adversarial"),
        ],
        29: [
            case("1\n3 4", "少于两点", "boundary"),
            case("2\n2 2\n5 6", "水平距离", "boundary"),
            case("3\n1 1\n1 1\n5 5", "重合点距离零", "adversarial"),
            case("4\n1 1\n4 5\n7 9\n10 13", "共线等距", "typical"),
            case("5\n1 1\n10 18\n17 50\n22 25\n39 50", "源样例", "typical"),
        ],
        30: [
            case("1\n1 1\n7", "单元素单区", "boundary"),
            case("1\n2 2\n9 1", "两元素两区", "boundary"),
            case("1\n3 1\n4 1 3", "只能一个区", "boundary"),
            case("1\n6 3\n8 3 4 6 5 2", "三区一般划分", "typical"),
            case("1\n5 2\n5 1 5 1 5", "重复值与并列方案", "adversarial"),
        ],
        31: [
            case("1\n1", "仅一辆车", "boundary"),
            case("3\n1 2 3", "顺序直接出站", "boundary"),
            case("3\n3 2 1", "反向全部从出口一", "typical"),
            case("5\n2 5 1 4 3", "双端交错出站", "typical"),
            case("4\n4 2 1 3", "非法夹在中间", "adversarial"),
        ],
        32: [
            case("1\n2\nD#", "起点在端点", "boundary"),
            case("1\n3\n#D#", "孤立空地无法启动", "boundary"),
            case("1\n4\n#DD#", "相邻空地启动技能", "typical"),
            case("1\n5\n..D##", "相邻空地后启动技能", "typical"),
            case("1\n5\n##D##", "障碍中孤立", "adversarial"),
        ],
        33: [
            case("1\n0\nDMTAO", "零辅助色完整串", "boundary"),
            case("1\n1\nDMTXAO", "一个辅助色", "typical"),
            case("1\n0\nDMTA", "缺少主色", "boundary"),
            case("1\n3\nAVMTTLB", "主色不全且辅助过多", "adversarial"),
            case("2\n0\nDMTXAO\n2\nXXDMTAOXX", "多组辅助色", "typical"),
        ],
        34: [
            case("1\n01", "各一个可直接交换", "boundary"),
            case("1\n0", "单字符必须删除", "boundary"),
            case("1\n1110", "需要删除到平衡前缀", "typical"),
            case("2\n01\n101", "不同长度均可不删", "typical"),
            case("2\n0001\n111111", "偏斜与全相同", "adversarial"),
        ],
        35: [
            case("3 3 1\n1 4 2", "一圈人数等于吊舱数", "boundary"),
            case("2 2 3\n5 5", "全程并列取前", "boundary"),
            case("4 4 2\n-1 2 2 0", "含零与负幸福值", "adversarial"),
            case("3 5 2\n1 2 3", "源样例", "typical"),
            case("5 3 2\n1 4 2 8 3", "人数少于吊舱", "typical"),
        ],
        36: [
            case("2", "二阶乘", "boundary"),
            case("4", "四阶乘个位四", "boundary"),
            case("5", "首次为零", "typical"),
            case("10", "一般情况", "typical"),
            case("1000000000", "输入上界附近", "boundary"),
        ],
        37: [
            case("1\n3 1", "一个三素数", "boundary"),
            case("1\n5 1", "三加二", "typical"),
            case("1\n7 1", "三加两个二", "typical"),
            case("1\n11 1", "多个二与一个奇素数", "typical"),
            case("1\n6 1", "奇偶不匹配无解", "adversarial"),
        ],
        39: [
            case("1\n1 5\n2\n0 1", "单位掩码", "boundary"),
            case("1\n3 1 2 3\n2\n0 3", "源样例", "typical"),
            case("1\n5 1 2 4 8 16\n3\n1 4 31", "二的幂掩码", "boundary"),
            case("1\n6 0 3 3 3 5 7\n3\n2 4 6", "零值和重复值", "adversarial"),
            case("2\n4 1 2 3 4\n2\n1 7\n4 10 10 10 10\n2\n4 0", "多组一般情况", "typical"),
        ],
        40: [
            case("1\n1 0 1 2\n0\n0 1", "持续一秒含左不含右", "boundary"),
            case("1\n5 11 2 10\n0 15\n1 2 3 4 6 7 8 9 10 11", "窗口边界另一端", "typical"),
            case("1\n3 2 3 3\n0 1 4\n0 2 3", "多个释放时刻并列", "adversarial"),
            case("1\n10 5 1 1\n100\n99", "窗口前击杀不计", "boundary"),
            case("2\n2 1 2 4\n0 3\n0 1 2 3\n4 1 1 1\n2\n2", "多组一般情况", "typical"),
        ],
        41: [
            case(triangle_input(1, 1, 1, [(0, 0), (1, 0), (0, 1)]), "单像素斜边采样在边界", "boundary"),
            case(triangle_input(2, 2, 2, [(0, 0), (2, 0), (0, 2)]), "完整覆盖左上像素", "boundary"),
            case(triangle_input(2, 2, 1, [(0, 0), (2, 0), (0, 2)]), "二乘二三角", "typical"),
            case(triangle_input(2, 3, 2, [(0.5, 0.5), (1.5, 0.5), (0.5, 2.5)]), "非整数顶点", "typical"),
            case(triangle_input(3, 2, 3, [(0.2, 0.2), (2.8, 0.4), (1.1, 1.8)]), "高倍超采样", "adversarial"),
        ],
        42: [
            case(maze_data(2, 2, 0, [(1, 1, 0, 1)], [(2, 2)], [".#", ".."]), "能量不足无法到达", "boundary"),
            case(maze_data(3, 3, 0, [(1, 1, 0, 4), (2, 2, 0, 6)], [(3, 3)], ["...", "...", "..."]), "两个蛋仔总耗时", "typical"),
            case(maze_data(3, 3, 0, [(1, 1, 5, 10), (3, 3, 0, 5)], [(2, 2)], ["...", "...", "..."]), "能量池顺序不足", "adversarial"),
            case(maze_data(3, 3, 5, [(1, 1, 5, 10), (3, 3, 0, 5)], [(2, 2)], ["...", "...", "..."]), "初始能量使顺序可行", "typical"),
            case(maze_data(3, 4, 2, [(1, 1, 0, 3), (4, 3, 0, 5), (3, 3, 1, 4)], [(3, 1), (2, 3)], ["....", "....", "...."]), "多出口", "typical"),
        ],
        43: [
            case("1\n2 0 1 3\n1\n0 1 2", "间隔击杀", "boundary"),
            case("1\n5 8 2 10\n0 20\n1 2 3 4 6 7 8 9 10 11", "较短无敌窗口", "typical"),
            case("1\n4 1 3 5\n2 3 7\n2 3 4 5 6", "重复击杀时间", "adversarial"),
            case("1\n1 100 2 4\n0 50\n0 1 49 50", "窗口不重叠", "boundary"),
            case("2\n3 2 3 3\n0 1 4\n0 2 3\n2 1 2 2\n5 6\n4 5", "多组一般情况", "typical"),
        ],
        44: [
            case(triangle_input(1, 1, 1, [(0, 0), (0, 1), (1, 0)]), "另一种顶点顺序", "boundary"),
            case(triangle_input(2, 2, 2, [(0, 0), (2, 0), (2, 2)]), "右三角", "typical"),
            case(triangle_input(2, 2, 1, [(0, 1), (1, 0), (2, 2)]), "斜置窄三角", "adversarial"),
            case(triangle_input(3, 3, 3, [(0.5, 0.5), (3.5, 0.5), (2.5, 3.5)]), "部分覆盖三乘三", "typical"),
            case(triangle_input(2, 3, 2, [(0, 2), (2, 2), (1, 0)]), "顶点贴在图像边界", "boundary"),
        ],
        45: [
            case(maze_data(2, 2, 0, [(1, 1, 0, 2)], [(2, 1)], ["..", ".."]), "单路径成功", "boundary"),
            case(maze_data(3, 3, 0, [(1, 1, 0, 0)], [(2, 2)], ["...", ".#.", "..."]), "零能量无法移动", "boundary"),
            case(maze_data(3, 3, 0, [(1, 1, 5, 10), (3, 3, 0, 5)], [(2, 2)], ["...", "...", "..."]), "顺序能量不足", "adversarial"),
            case(maze_data(3, 3, 5, [(1, 1, 5, 10), (3, 3, 0, 5)], [(2, 2)], ["...", "...", "..."]), "调整顺序后成功", "typical"),
            case(maze_data(4, 3, 3, [(2, 1, 0, 5), (3, 2, 0, 3), (2, 3, 2, 6)], [(3, 1), (1, 3)], ["...", "...", "...", "..."]), "多出口多蛋仔", "typical"),
        ],
        47: [
            case("1\n1 1\n3\n3\n1", "零距离", "boundary"),
            case("1\n2 2\n1 5\n2 6\n1 1", "源样例最小阈值一", "boundary"),
            case("1\n3 2\n0 10 20\n5 15\n1 1", "总容量不足", "adversarial"),
            case("1\n3 2\n1 4 7\n2 8\n2 1", "容量非均匀", "typical"),
            case("2\n2 3\n0 100\n40 50 60\n1 1 1\n3 2\n5 9 12\n8 10\n2 1", "多组一般情况", "typical"),
        ],
        48: [
            case("1\n5\n0", "单城市", "boundary"),
            case("2\n2 5\n-1 3\n-1 -1", "只能先去城市一", "boundary"),
            case("3\n3 5 -1\n1 2 4\n-1 1 1\n3 -1 2", "非对称三城市", "typical"),
            case("3\n1 1 1\n-1 9 9\n9 -1 9\n9 9 -1", "无跨城道路", "adversarial"),
            case("4\n5 4 3 2\n-1 1 4 9\n2 -1 1 8\n6 3 -1 1\n2 5 4 -1", "非对称城市道路", "typical"),
        ],
    }


TOKEN_REASON = (
    "题意要求确定的数值、字符串或有序序列；tokens 会忽略空白和换行格式差异，"
    "但仍严格检查 token 的数量、内容和顺序。"
)

FLOAT_SETTINGS: dict[int, tuple[float, float, str]] = {
    6: (0.050000001, 1e-9, "期望轮数按要求保留一位小数，因此容差取半个最小输出单位。"),
    13: (0.0005, 1e-9, "TF-IDF 按题意以 round(x, 3) 输出，容差取 0.0005。"),
    14: (0.0005, 1e-9, "前向损失按题意以 round(x, 3) 输出，容差取 0.0005。"),
    16: (0.00005, 1e-9, "回归系数按题意四舍五入到四位小数，容差取 0.00005。"),
    17: (5e-8, 1e-7, "权重按 NumPy 默认格式输出，未要求固定小数位；按默认约八位有效数字设容差。"),
    18: (0.0005, 1e-9, "F-Score 固定保留三位小数，容差取 0.0005。"),
    29: (0.00005, 1e-9, "参考输出精度为四位小数，容差取 0.00005；原文字漏写精度已记录。"),
}

MANUAL_REASONS: dict[int, str] = {
    38: (
        "结果依赖 sklearn PCA/KMeans 的具体数值实现及 random_state=42、n_init=10 下的原生簇标签；"
        "题目还涉及随机初始化，不能由当前标准库独立判定器稳定给出唯一字符串，暂缓自动判题。"
    ),
    28: (
        "原题用 '-' 同时作节点分隔符并把 -1 作为空节点，但现有可解析样例无法无歧义表达空节点；"
        "补充用例只采用非空正大小树，自动结果应人工确认是否有空节点特例。"
    ),
    32: (
        "原页面未完整保留“穿出隧道端点”的形式化条件，现有语义由样例与说明反推；"
        "补充用例按该已记录解释给出，但仍需人工确认。"
    ),
    35: (
        "原页面缺少队列在整圈结束后的移位规则，现有分配公式由参考叙事反推；"
        "补充用例覆盖人数等于吊舱数或单圈等较确定情形，仍需人工确认更一般映射。"
    ),
}


SEMANTIC_REASONS: dict[int, tuple[str, str]] = {
    12: (
        "window-distinct",
        "题面允许任意合法重排；运行期比较元素多重集，并要求同值最近距离至少为 k，"
        "无解时仅接受 -1，因此不会拒绝其他合法排列。",
    ),
    46: (
        "max-digit-sum",
        "题面允许输出任意最大数位和的数；运行期检查答案严格小于 x 且数位和达到理论最优，"
        "因此会接受并列最优的任一答案，也无须把超长十进制数转成机器整数。",
    ),
}


EXCLUSIONS: dict[int, dict[str, object]] = {
    46: {
        "exclude_statement_inputs": ["3\n10\n1234"],
        "exclusion_reason": (
            "题面声明 T=3 却仅提供 2 个 x，输入被截断；且源页面已注明 "
            "x=10 的期望 6 是 OCR 错误，按题意应为 9。"
        ),
    },
}


def checker_for(index: int) -> dict[str, object]:
    if index in SEMANTIC_REASONS:
        mode, reason = SEMANTIC_REASONS[index]
        return checker(mode, reason)
    if index in MANUAL_REASONS:
        return checker("manual", MANUAL_REASONS[index])
    if index in FLOAT_SETTINGS:
        absolute, relative, reason = FLOAT_SETTINGS[index]
        return checker("float", reason, abs_tol=absolute, rel_tol=relative)
    return checker("tokens", TOKEN_REASON)


def numeric_tokens(text: str) -> list[float]:
    pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    return [float(value) for value in re.findall(pattern, text)]


def accepts(
    expected: str,
    actual: str,
    check: dict[str, object],
    input_text: str | None = None,
) -> bool:
    mode = check["mode"]
    if mode in {"window-distinct", "max-digit-sum"}:
        if input_text is None:
            return False
        try:
            if mode == "window-distinct":
                validate_reorder_sample(input_text, actual)
            else:
                validate_max_digit_sum_sample(input_text, actual)
        except (AssertionError, ValueError, IndexError):
            return False
        return True
    if mode == "exact":
        return expected.rstrip("\n") == actual.rstrip("\n")
    if mode == "tokens":
        return expected.split() == actual.split()
    if mode == "json":
        try:
            return json.loads(expected) == json.loads(actual)
        except (json.JSONDecodeError, TypeError):
            return False
    if mode == "float":
        left = numeric_tokens(expected)
        right = numeric_tokens(actual)
        if len(left) != len(right):
            return False
        return all(
            math.isclose(
                first,
                second,
                abs_tol=float(check["abs_tol"]),
                rel_tol=float(check["rel_tol"]),
            )
            for first, second in zip(left, right)
        )
    if mode == "manual":
        return True
    raise ValueError(f"unknown checker mode: {mode}")


def validate_reorder_sample(input_text: str, expected: str) -> None:
    lines = split_nonempty_lines(input_text)
    n, k = map(int, lines[0].split())
    values = list(map(int, lines[1].split()))
    if expected.strip() == "-1":
        frequencies = sorted(Counter(values).values(), reverse=True)
        maximum = frequencies[0]
        tied = frequencies.count(maximum)
        if (maximum - 1) * k + tied <= n:
            raise AssertionError(f"sample marked impossible but a packing bound permits a solution: {input_text!r}")
        return
    result = list(map(int, expected.split()))
    if Counter(result) != Counter(values):
        raise AssertionError(f"reorder changed multiset: {input_text!r}")
    for start in range(n):
        seen: set[int] = set()
        for end in range(start, min(n, start + k)):
            if result[end] in seen:
                raise AssertionError(f"reorder repeats inside window k={k}: {input_text!r}")
            seen.add(result[end])


def max_digit_sum_optimum(number: str) -> int:
    prefix = 0
    best = -1
    for index, character in enumerate(number):
        digit = int(character)
        if digit:
            best = max(best, prefix + digit - 1 + 9 * (len(number) - index - 1))
        prefix += digit
    return best


def validate_max_digit_sum_sample(input_text: str, expected: str) -> None:
    lines = split_nonempty_lines(input_text)
    test_count = int(lines[0])
    numbers = lines[1 : 1 + test_count]
    answers = expected.split()
    if len(lines) != test_count + 1 or len(numbers) != test_count:
        raise AssertionError(f"maximum-digit-sum input has the wrong case count: {input_text!r}")
    if len(answers) != test_count:
        raise AssertionError(f"maximum-digit-sum output has the wrong case count: {expected!r}")
    for number, answer in zip(numbers, answers):
        if not number.isdigit() or number.startswith("0"):
            raise AssertionError(f"maximum-digit-sum x is not a canonical positive integer: {number!r}")
        if not answer.isdigit():
            raise AssertionError(f"maximum-digit-sum answer is not nonnegative decimal: {answer!r}")
        canonical_answer = answer.lstrip("0") or "0"
        if len(canonical_answer) > len(number) or (
            len(canonical_answer) == len(number) and canonical_answer >= number
        ):
            raise AssertionError(f"maximum-digit-sum answer is not below x: x={number!r}, answer={answer!r}")
        actual_sum = sum(map(int, canonical_answer))
        optimum = max_digit_sum_optimum(number)
        if actual_sum != optimum:
            raise AssertionError(
                f"maximum-digit-sum answer is not optimal: x={number!r}, "
                f"sum={actual_sum}, optimum={optimum}"
            )


def validate_semantic_samples(index: int, samples: list[dict[str, str]]) -> None:
    for row in samples:
        if index == 12:
            validate_reorder_sample(row["input"], row["expected"])
        elif index == 46:
            validate_max_digit_sum_sample(row["input"], row["expected"])
            if row["name"] == "整十与两位并列":
                values = split_nonempty_lines(row["input"])[1:]
                for number in (value for value in values if value == "19"):
                    limit = int(number)
                    optimum = max_digit_sum_optimum(number)
                    tied = sum(sum(map(int, str(value))) == optimum for value in range(limit))
                    if tied < 2:
                        raise AssertionError(f"expected a digit-sum tie for x={number}, found {tied}")
            elif row["name"] == "三位并列最大数位和":
                values = split_nonempty_lines(row["input"])[1:]
                for number in values:
                    limit = int(number)
                    optimum = max_digit_sum_optimum(number)
                    tied = sum(sum(map(int, str(value))) == optimum for value in range(limit))
                    if tied < 2:
                        raise AssertionError(f"expected a digit-sum tie for x={number}, found {tied}")


def build_payloads(metas: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    specs = build_case_specs()
    specs[46] = [
        case("1\n1", "最小正输入", "boundary"),
        case("2\n10\n19", "整十与两位并列", "boundary"),
        case("1\n100", "整百边界", "boundary"),
        case("2\n199\n999", "三位并列最大数位和", "adversarial"),
        case("1\n1234", "一般四位数", "typical"),
        case("1\n1000000", "较长整十边界", "boundary"),
    ]
    manual_samples: dict[int, list[dict[str, str]]] = {
        38: [],
    }
    payloads: dict[str, dict[str, object]] = {}
    for index, meta in enumerate(metas):
        url = str(meta["url"])
        check = checker_for(index)
        if index in manual_samples:
            rows = manual_samples[index]
        elif index == 38:
            rows = []
        else:
            runner = RUNNERS[index]
            source_cases = specs.get(index, [])
            verification = "independent oracle built into acm_cases_c.py"
            if index == 12:
                verification = (
                    "independent-bruteforce: 枚举全部不同重排并直接检查所有长度不超过 k 的窗口；"
                    "expected 仅记录其中一个合法解。"
                )
            elif index == 46:
                verification = (
                    "independent-formula: 枚举“把某一位减一、后缀置九”的全部候选并比较数位和；"
                    "并列案例另行小规模穷举确认至少两个最优数。"
                )
            elif index == 15:
                verification = (
                    "independent-formula: 逐通道窗口求内积并独立套用特征图边长公式；"
                    "oracle 先断言方阵、宽度等于高度且等于卷积核边长、参数和窗口边界合法。"
                )
            elif index == 22:
                verification = (
                    "independent-bruteforce: 小范围逐项求 gcd 后求和，并用约数列举公式核对；"
                    "oracle 先断言 1<=a,b<=100000 且 0<=l<=r<=10^18。"
                )
            elif index == 48:
                verification = (
                    "independent-bruteforce: 枚举三城或四城的全部访问排列，仅把 -1 视为不可达边。"
                )
            rows = text_samples(
                source_cases,
                runner,
                verification,
            )
        payload = item(meta, check, rows)
        payload.update(EXCLUSIONS.get(index, {}))
        payloads[url] = payload
    return payloads


def validate_contract(metas: list[dict[str, object]], payloads: dict[str, dict[str, object]]) -> tuple[list[str], int]:
    messages = []
    source_sample_count = 0
    if len(metas) != 49:
        raise AssertionError(f"practice-meta slice must contain 49 items, found {len(metas)}")
    expected_urls = [str(meta["url"]) for meta in metas]
    if list(payloads) != expected_urls:
        raise AssertionError("payload order or URL set differs from practice-meta slice")
    for index, meta in enumerate(metas):
        url = str(meta["url"])
        payload = payloads[url]
        check = payload["checker"]
        rows = payload["samples"]
        assert isinstance(check, dict)
        assert isinstance(rows, list)
        if check["mode"] != "manual" and not 4 <= len(rows) <= 8:
            raise AssertionError(f"{url}: expected 4..8 supplemental samples, found {len(rows)}")
        names = [row["name"] for row in rows]
        inputs = [row["input"] for row in rows]
        if len(names) != len(set(names)) or len(inputs) != len(set(inputs)):
            raise AssertionError(f"{url}: duplicate sample name or input")
        for row in rows:
            if not row["input"] or not row["expected"]:
                raise AssertionError(f"{url}: empty supplemental input or expected output")
            if row["kind"] not in KINDS or row["source"] != "supplemental":
                raise AssertionError(f"{url}: invalid sample metadata")
            if not row["verification"].strip():
                raise AssertionError(f"{url}: missing verification note")
        if index == 12 or index == 46:
            validate_semantic_samples(index, rows)
        runner = RUNNERS.get(index)
        source_samples = meta.get("samples", [])
        if not isinstance(source_samples, list):
            raise AssertionError(f"{url}: meta samples must be a list")
        visible = [
            visible_sample
            for visible_sample in source_samples
            if isinstance(visible_sample, dict)
            and visible_sample.get("source", "statement") != "supplemental"
        ]
        source_sample_count += len(visible)
        if index == 12:
            for visible_sample in visible:
                validate_reorder_sample(
                    str(visible_sample["input"]),
                    str(visible_sample["expected"]),
                )
        excluded = payload.get("exclude_statement_inputs", [])
        exclusion_reason = payload.get("exclusion_reason")
        if bool(excluded) != bool(exclusion_reason):
            raise AssertionError(f"{url}: exclusion inputs and reason must be present together")
        if excluded:
            if not isinstance(excluded, list) or not all(isinstance(value, str) for value in excluded):
                raise AssertionError(f"{url}: exclusion inputs must be a string list")
            if len(excluded) != len(set(excluded)):
                raise AssertionError(f"{url}: duplicate exclusion input")
            if not isinstance(exclusion_reason, str) or not exclusion_reason.strip():
                raise AssertionError(f"{url}: missing exclusion reason")
            visible_inputs = {
                str(visible_sample["input"])
                for visible_sample in visible
                if "input" in visible_sample
            }
            missing = [value for value in excluded if value not in visible_inputs]
            if missing and "suite_version" not in meta:
                raise AssertionError(f"{url}: exclusion inputs are not exact visible source inputs: {missing!r}")
        if runner is not None and visible:
            visible_answers = {str(visible_sample["input"]).strip(): str(visible_sample["expected"]) for visible_sample in visible}
            conflicts = [
                row["name"]
                for row in rows
                if row["input"].strip() in visible_answers
                and row["expected"].split() != visible_answers[row["input"].strip()].split()
            ]
            if conflicts:
                raise AssertionError(f"{url}: supplemental inputs conflict with visible samples: {conflicts}")
            excluded_inputs = set(excluded) if excluded else set()
            for visible_sample in visible:
                visible_input = str(visible_sample["input"])
                if visible_input in excluded_inputs:
                    continue
                actual = runner(visible_input)
                expected = str(visible_sample["expected"])
                matches = (
                    expected.split() == actual.split()
                    if check["mode"] == "manual"
                    else accepts(expected, actual, check, visible_input)
                )
                if not matches:
                    messages.append(
                        f"{url}: visible sample mismatch; expected={expected!r}, oracle={actual!r}"
                    )
    return messages, source_sample_count


def main(argv: list[str]) -> int:
    all_metas = json.loads(META_PATH.read_text(encoding="utf-8"))
    if not isinstance(all_metas, list) or len(all_metas) < 147:
        raise AssertionError("practice-meta.json does not contain indices 98..146")
    metas = all_metas[98:147]
    payloads = build_payloads(metas)
    mismatches, source_sample_count = validate_contract(metas, payloads)
    if mismatches:
        for message in mismatches:
            print(message, file=sys.stderr)
        return 1
    manual_count = sum(item["checker"]["mode"] == "manual" for item in payloads.values())
    sample_count = sum(len(item["samples"]) for item in payloads.values())
    if "--validate-only" not in argv:
        document = {"version": 1, "items": payloads}
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        action = "wrote"
    else:
        action = "validated"
    print(
        f"{action} {len(payloads)} items, {source_sample_count} visible source samples, "
        f"{sample_count} supplemental samples, {manual_count} manual checkers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))









