"""LeetCode judge structures and stdin/stdout adaptations used by the native ACM reference check."""

import itertools
from collections import deque, namedtuple
from types import SimpleNamespace

Point = namedtuple("Point", "x y")
Interval = namedtuple("Interval", "start end")


class Node:
    def __init__(self, val=0, children=None):
        self.val = val
        self.children = children or []
        self.left = self.right = self.next = self.random = None


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
        for node, nxt in itertools.pairwise(nodes):
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


def chain(values, tail=None):
    for value in reversed(values):
        tail = ListNode(value, tail)
    return tail


def linked_nodes(head):
    nodes = []
    while head is not None:
        nodes.append(head)
        head = head.next
    return nodes


def nodes_by_value(root):
    result = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node is not None:
            result[node.val] = node
            stack.extend((node.left, node.right))
    return result


def hot100_reference(pid, env, args):
    if pid in (146, 155, 208, 295):
        names, parameters = args
        obj = env[names[0]](*parameters[0])
        return [None] + [getattr(obj, name)(*values) for name, values in zip(names[1:], parameters[1:])]

    solution = env["Solution"]()
    method = next(getattr(solution, name) for name in vars(type(solution)) if not name.startswith("_"))
    if pid in (141, 142):
        values, pos = args
        head = chain(values)
        nodes = linked_nodes(head)
        if pos >= 0:
            nodes[-1].next = nodes[pos]
        result = method(head)
        if pid == 141:
            return result
        return nodes.index(result) if result is not None else -1
    if pid == 160:
        shared = chain(args[2])
        result = method(chain(args[0], shared), chain(args[1], shared))
        return result.val if result else None
    if pid == 236:
        root = tree(args[0])
        nodes = nodes_by_value(root)
        return method(root, nodes[args[1]], nodes[args[2]]).val
    if pid == 138:
        nodes = [Node(value) for value, _ in args[0]]
        for i, (_, rand) in enumerate(args[0]):
            nodes[i].next = nodes[i + 1] if i + 1 < len(nodes) else None
            nodes[i].random = nodes[rand] if rand is not None else None
        clone = linked_nodes(method(nodes[0] if nodes else None))
        positions = {node: i for i, node in enumerate(clone)}
        return [[node.val, positions[node.random] if node.random is not None else None] for node in clone]
    if pid in (2, 21):
        args = [chain(values) for values in args]
    if pid in (19, 24, 25, 148, 206, 234):
        args[0] = chain(args[0])
    if pid == 23:
        args[0] = [chain(values or []) for values in args[0]]
    if pid in (94, 98, 101, 102, 104, 114, 124, 199, 226, 230, 437, 543):
        args[0] = tree(args[0])

    result = method(*args)
    if pid in (31, 48, 73, 75, 114, 189, 283):
        result = args[0]
    if pid in (2, 19, 21, 23, 24, 25, 148, 206):
        return [node.val for node in linked_nodes(result)]
    if pid in (105, 108, 114, 226):
        return level_order(result)
    if pid in (15, 39, 49, 78):
        return sorted(sorted(row) for row in result)
    if pid in (1, 17, 22, 46, 51, 131, 347, 438):
        return sorted(result)
    return result
