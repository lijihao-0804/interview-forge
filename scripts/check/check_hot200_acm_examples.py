"""Check the supplemental ACM fixtures against this repository's published Python solutions."""

import json
import math
from collections import deque, namedtuple
from pathlib import Path
from types import SimpleNamespace

from scripts.build.build_hot200_extra import FENCE, sections

ROOT = Path(__file__).resolve().parents[2]
Point = namedtuple("Point", "x y")
Interval = namedtuple("Interval", "start end")


class Node:
    def __init__(self, val=0, children=None):
        self.val = val
        self.children = children or []
        self.left = self.right = self.next = None


def tree(values):
    nodes = [Node(v) if v is not None else None for v in values]
    rest = iter(nodes[1:])
    for node in filter(None, nodes):
        node.left = next(rest, None)
        node.right = next(rest, None)
    return nodes[0] if nodes else None


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


def level_order(root):
    queue, values = deque([root]), []
    while queue:
        node = queue.popleft()
        values.append(node.val if node else None)
        if node:
            queue.extend([node.left, node.right])
    while values and values[-1] is None:
        values.pop()
    return values


def nary(value):
    return Node(value[0], [nary(v) for v in value[1]]) if value else None


def nested(value):
    return SimpleNamespace(
        isInteger=lambda: isinstance(value, int),
        getInteger=lambda: value,
        getList=lambda: [nested(item) for item in value],
    )


class Robot:
    def __init__(self, room, pos):
        self.room, self.pos, self.direction, self.cleaned = room, tuple(pos), 0, set()

    def clean(self):
        self.cleaned.add(self.pos)

    def turnRight(self):
        self.direction = (self.direction + 1) % 4

    def move(self):
        dr, dc = [(-1, 0), (0, 1), (1, 0), (0, -1)][self.direction]
        r, c = self.pos[0] + dr, self.pos[1] + dc
        if 0 <= r < len(self.room) and 0 <= c < len(self.room[r]) and self.room[r][c]:
            self.pos = (r, c)
            return True
        return False


def operations(instance, calls):
    results = []
    for name, *args in calls:
        result = getattr(instance, name)(*args)
        if result is not None:
            results.append(result)
    return results


def run_reference(pid, env, args):
    # Adapt the judge's tree, stream and interactive interfaces to stdin/stdout.
    sequence = {
        716: ("MaxStack", 0),
        308: ("NumMatrix", 1),
        362: ("HitCounter", 0),
        379: ("PhoneDirectory", 1),
    }
    if pid in sequence:
        cls, n = sequence[pid]
        return operations(env[cls](*args[:n]), args[n])
    stream = {
        244: ("WordDistance", "shortest", 1),
        288: ("ValidWordAbbr", "isUnique", 1),
        346: ("MovingAverage", "next", 1),
        348: ("TicTacToe", "move", 1),
        353: ("SnakeGame", "move", 3),
        359: ("Logger", "shouldPrintMessage", 0),
    }
    if pid in stream:
        cls, method, n = stream[pid]
        call = getattr(env[cls](*args[:n]), method)
        return [
            call(*item) if isinstance(item, list) else call(item) for item in args[n]
        ]
    if pid == 251:
        return operations(env["Vector2D"](args[0]), [[name] for name in args[1]])
    if pid == 281:
        it = env["ZigzagIterator"](*args)
        return list(iter(lambda: it.next() if it.hasNext() else None, None))
    if pid == 271:
        codec = env["Codec"]()
        encoded = codec.encode(args[0])
        assert codec.decode(encoded) == args[0]
        return encoded
    if pid == 428:
        codec = env["Codec"]()
        encoded = codec.serialize(nary(args[0]))
        assert codec.serialize(codec.deserialize(encoded)) == encoded
        tokens = list(map(int, encoded.split(","))) if encoded else []
        return [tokens[i : i + 2] for i in range(0, len(tokens), 2)]
    if pid == 431:
        return level_order(env["Codec"]().encode(nary(args[0])))
    solution = env["Solution"]()
    call = next(
        getattr(solution, name)
        for name in vars(type(solution))
        if not name.startswith("_")
    )
    if pid in (250, 270, 272, 285, 298, 314, 333, 366, 426, 742, 776):
        args[0] = tree(args[0])
    if pid == 285:
        args[1] = Node(args[1])
        result = call(*args)
        return result.val if result else None
    if pid == 426:
        head = call(*args)
        values, node = [], head
        while node:
            values.append(node.val)
            node = node.right
            if node is head:
                break
        return values
    if pid == 776:
        return [level_order(t) for t in call(*args)]
    if pid == 1274:
        ships, upper, lower = args
        sea = SimpleNamespace(
            hasShips=lambda hi, lo: any(
                lo.x <= x <= hi.x and lo.y <= y <= hi.y for x, y in ships
            )
        )
        return call(sea, Point(*upper), Point(*lower))
    if pid == 1236:
        return sorted(
            call(args[0], SimpleNamespace(getUrls=lambda u: args[1].get(u, [])))
        )
    if pid == 702:
        values, target = args
        return call(
            SimpleNamespace(get=lambda i: values[i] if i < len(values) else 2**31 - 1),
            target,
        )
    if pid == 277:
        env["knows"] = lambda x, y: args[0][x][y]
        return call(len(args[0]))
    if pid == 759:
        return [
            list(i)
            for i in call(
                [[Interval(*interval) for interval in person] for person in args[0]]
            )
        ]
    if pid == 489:
        robot = Robot(*args)
        call(robot)
        return [list(v) for v in sorted(robot.cleaned)]
    if pid in (339, 364):
        args[0] = [nested(v) for v in args[0]]
    if pid in (369, 708, 1265):
        nodes = [Node(v) for v in args[0]]
        for node, nxt in zip(nodes, nodes[1:]):
            node.next = nxt
        printed = []
        for node in nodes:
            node.getNext = lambda n=node: n.next
            node.printValue = lambda n=node: printed.append(n.val)
        if pid == 708 and nodes:
            nodes[-1].next = nodes[0]
        args[0] = nodes[0] if nodes else None
        head = call(*args)
        if pid == 1265:
            return printed
        values, cur = [], head
        while cur:
            values.append(cur.val)
            cur = cur.next
            if cur is head:
                break
        return values
    if pid == 186:
        chars = list(args[0])
        call(chars)
        return "".join(chars)
    if pid in (280, 286):
        call(*args)
        return args[0]
    result = call(*args)
    if pid in (247, 254, 267, 272, 320, 425):
        return sorted(result)
    if pid == 249:
        return sorted(sorted(group) for group in result)
    if pid == 366:
        return [sorted(group) for group in result]
    return result


def check():
    catalog = json.loads((ROOT / "data/acm/hot200-extra.json").read_bytes())
    expected_ids = {
        p["id"] for p in json.loads((ROOT / "data/hot200-extra.json").read_bytes())
    }
    assert len(catalog) == len(expected_ids) == 100
    assert {entry["id"] for entry in catalog} == {
        f"hot200-{pid}" for pid in expected_ids
    }
    failed = []
    count = 0
    for entry in catalog:
        pid = int(entry["id"].split("-")[1])
        path = ROOT / f"books/hot200-extra/solutions/{pid}.md"
        code = FENCE.search(sections(path.read_text(encoding="utf-8-sig"))["Python"])[2]
        env = dict(
            Node=Node, TreeNode=Node, ListNode=ListNode, Point=Point, Interval=Interval
        )
        exec(compile(code, str(path), "exec"), env)
        for sample in entry["samples"]:
            count += 1
            args = [json.loads(line) for line in sample["input"].splitlines()]
            want = json.loads(sample["expected"])
            try:
                actual = run_reference(pid, env, args)
                good = (
                    math.isclose(actual, want, abs_tol=1e-6)
                    if pid == 774
                    else actual == want
                )
                assert good, (actual, want)
            except Exception as error:
                failed.append((pid, sample["name"], repr(error)))
    if failed:
        raise AssertionError(failed)
    print(f"{len(catalog)} supplemental problems, {count} reference outputs verified")


if __name__ == "__main__":
    check()
