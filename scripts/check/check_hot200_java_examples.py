"""Compile the published Java solutions and run each local ACM fixture on JDK 17+."""

import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

from scripts.build.build_hot200_extra import FENCE, sections
from scripts.check.check_hot200_acm_examples import catalog_with_teaching_edges

ROOT = Path(__file__).resolve().parents[2]


def literal(value, kind):
    if kind.endswith("[]"):
        items = ", ".join(literal(x, kind[:-2]) for x in value)
        return f"new {kind}{{{items}}}"
    if kind.startswith("List<"):
        items = ", ".join(literal(x, kind[5:-1]) for x in value)
        return f"List.of({items})"
    if kind == "char":
        return "'" + value + "'"
    if kind == "TreeNode":
        if isinstance(value, int):
            return f"new TreeNode({value})"
        return "tree(" + ",".join("null" if x is None else str(x) for x in value) + ")"
    if kind == "Interval":
        return f"new Interval({value[0]},{value[1]})"
    if kind == "NestedInteger":
        return (
            f"new NestedInteger({value},null)"
            if isinstance(value, int)
            else f"new NestedInteger(null,{literal(value, 'List<NestedInteger>')})"
        )
    if kind == "Node":
        if value is None:
            return "null"
        return f"new Node({value[0]},{literal(value[1], 'List<Node>')})"
    if kind == "int" and isinstance(value, bool):
        return str(int(value))
    return json.dumps(value, ensure_ascii=True)


def signature(source, name=None):
    pattern = (
        r"public\s+([\w<>\[\],]+)\s+"
        + (re.escape(name) if name else r"(\w+)")
        + r"\s*\(([^)]*)\)"
    )
    m = re.search(pattern, source)
    if not m:
        raise ValueError(name)
    return (
        m[1],
        (name or m[2]),
        [
            part.rsplit(None, 1)[0].replace("final ", "").strip()
            for part in m.groups()[-1].split(",")
            if part.strip()
        ],
    )


def invoke(source, name, args):
    result, method, types = signature(source, name)
    expr = (
        "obj."
        + method
        + "("
        + ",".join(literal(v, t) for v, t in zip(args, types, strict=True))
        + ")"
    )
    return expr + ";" if result == "void" else "out.add(" + expr + ");"


def fixture_body(pid, source, args):
    design = {
        244: ("WordDistance", ["String[]"], "shortest"),
        251: ("Vector2D", ["int[][]"], None),
        288: ("ValidWordAbbr", ["String[]"], "isUnique"),
        346: ("MovingAverage", ["int"], "next"),
        348: ("TicTacToe", ["int"], "move"),
        353: ("SnakeGame", ["int", "int", "int[][]"], "move"),
        359: ("Logger", [], "shouldPrintMessage"),
        362: ("HitCounter", [], None),
        379: ("PhoneDirectory", ["int"], None),
        716: ("MaxStack", [], None),
        308: ("NumMatrix", ["int[][]"], None),
    }
    if pid in design:
        cls, types, name = design[pid]
        params = ",".join(literal(x, t) for x, t in zip(args, types))
        statements = [
            f"var obj=new {cls}({params});",
            "List<Object> out=new ArrayList<>();",
        ]
        for op in args[len(types)]:
            if name:
                statements.append(
                    invoke(source, name, op if isinstance(op, list) else [op])
                )
            elif isinstance(op, str):
                statements.append(invoke(source, op, []))
            else:
                statements.append(invoke(source, op[0], op[1:]))
        return " ".join([*statements, "return out;"])
    if pid == 281:
        a, b = [literal(x, "List<Integer>") for x in args]
        return f"var it=new ZigzagIterator({a},{b}); List<Object> out=new ArrayList<>(); while(it.hasNext()) out.add(it.next()); return out;"
    if pid == 271:
        a = literal(args[0], "List<String>")
        return f"var c=new Codec(); var s=c.encode({a}); if(!c.decode(s).equals({a})) throw new AssertionError(); return s;"
    if pid in (428, 431):
        a = literal(args[0], "Node")
        if pid == 431:
            return f"var c=new Codec(); var root=c.encode({a}); if(!levels(c.encode(c.decode(root))).equals(levels(root))) throw new AssertionError(); return levels(root);"
        return f'var c=new Codec(); var s=c.serialize({a}); if(!s.equals(c.serialize(c.deserialize(s)))) throw new AssertionError(); var out=new ArrayList<>(); if(!s.isEmpty()) {{String[] v=s.split(",");for(int i=0;i<v.length;i+=2) out.add(List.of(Integer.valueOf(v[i]),Integer.valueOf(v[i+1])));}} return out;'
    solution = source[source.index("class Solution") :]
    result, name, types = signature(solution)
    call = "new Solution()." + name
    if pid == 1274:
        ships, high, low = [
            literal(x, t) for x, t in zip(args, ("int[][]", "int[]", "int[]"))
        ]
        return f"int[][] ships={ships}; Sea sea=(hi,lo)->Arrays.stream(ships).anyMatch(s->lo[0]<=s[0]&&s[0]<=hi[0]&&lo[1]<=s[1]&&s[1]<=hi[1]); return {call}(sea,{high},{low});"
    if pid == 1236:
        graph = "".join(
            "graph.put("
            + literal(k, "String")
            + ","
            + literal(v, "List<String>")
            + ");"
            for k, v in args[1].items()
        )
        return f"Map<String,List<String>> graph=new HashMap<>(); {graph} return {call}({literal(args[0], 'String')}, u->graph.getOrDefault(u,List.of()));"
    if pid == 277:
        return f"Relation.matrix={literal(args[0], 'int[][]')}; return {call}(Relation.matrix.length);"
    if pid == 702:
        return f"int[] a={literal(args[0], 'int[]')}; return {call}(i->i<a.length?a[i]:Integer.MAX_VALUE,{args[1]});"
    if pid == 489:
        return f"var robot=new Robot({literal(args[0], 'int[][]')},{literal(args[1], 'int[]')}); {call}(robot); return robot.cleaned;"
    if pid == 1265:
        return f"ImmutableListNode.printed.clear(); {call}(immutable({literal(args[0], 'int[]')})); return ImmutableListNode.printed;"
    if pid == 426:
        return (
            f"return ringValues({call}(treeNode({literal(args[0], 'TreeNode')})),true);"
        )
    if pid == 708:
        return f"return ringValues({call}(ring({literal(args[0], 'int[]')}),{args[1]}),false);"
    if pid == 369:
        return f"return {call}(list({literal(args[0], 'int[]')}));"
    if pid == 285:
        return f"var node={call}({literal(args[0], 'TreeNode')},new TreeNode({args[1]})); return node==null?null:node.val;"
    if pid == 776:
        return f"var roots={call}({literal(args[0], 'TreeNode')},{args[1]}); return List.of(levels(roots[0]),levels(roots[1]));"
    vals = [literal(x, t) for x, t in zip(args, types, strict=True)]
    if result == "void":
        return (
            f"var arg={vals[0]}; {call}(arg); return "
            + ("new String(arg)" if pid == 186 else "arg")
            + ";"
        )
    return f"return {call}(" + ",".join(vals) + ");"


def normalized(pid, value):
    if pid in (247, 254, 267, 272, 320, 425, 489, 1236):
        return sorted(value)
    if pid == 249:
        return sorted(sorted(x) for x in value)
    if pid == 366:
        return [sorted(x) for x in value]
    return value


def check():
    entries = catalog_with_teaching_edges()
    expected = {}
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        files = []
        calls = []
        for entry in entries:
            pid = int(entry["id"].split("-")[1])
            source = sections(
                (ROOT / f"books/hot200-extra/solutions/{pid}.md").read_text(
                    encoding="utf-8-sig"
                )
            )["Java"]
            code = FENCE.search(source)[2]
            folder = temp / f"lc{pid}"
            folder.mkdir()
            public = re.search(r"(?m)^public class (\w+)", code)
            solution = folder / ((public[1] if public else "Submission") + ".java")
            solution.write_text(
                f"package lc{pid};\nimport judge.Hot200Judge.*;\n" + code,
                encoding="utf8",
            )
            files.append(solution)
            methods = []
            for index, sample in enumerate(entry["samples"]):
                args = [json.loads(line) for line in sample["input"].splitlines()]
                methods.append(
                    f"public static Object test{index}() {{ "
                    + fixture_body(pid, code, args)
                    + " }"
                )
                key = f"{pid}.{index}"
                expected[key] = (pid, json.loads(sample["expected"]))
                calls.append(
                    f'System.out.println("{key} "+json(lc{pid}.Fixture.test{index}()));'
                )
            driver = folder / "Fixture.java"
            driver.write_text(
                f"package lc{pid};\nimport java.util.*;\nimport static judge.Hot200Judge.*;\npublic class Fixture {{\n"
                + "\n".join(methods)
                + "\n}",
                encoding="utf8",
            )
            files.append(driver)
        launcher = temp / "Main.java"
        launcher.write_text(
            "import static judge.Hot200Judge.json;\npublic class Main { public static void main(String[] args) {\n"
            + "\n".join(calls)
            + "\n}}",
            encoding="utf8",
        )
        argfile = temp / "sources.txt"
        argfile.write_text(
            "\n".join(
                '"' + p.as_posix() + '"'
                for p in [
                    Path(__file__).with_name("Hot200Judge.java").resolve(),
                    launcher,
                    *files,
                ]
            ),
            encoding="utf8",
        )
        subprocess.run(
            [
                "javac",
                "-encoding",
                "UTF-8",
                "--release",
                "17",
                "-d",
                str(temp),
                "@" + str(argfile),
            ],
            check=True,
        )
        output = subprocess.check_output(
            ["java", "-cp", str(temp), "Main"], text=True, encoding="utf8", timeout=120
        )
        for line in output.splitlines():
            key, value = line.split(" ", 1)
            pid, want = expected.pop(key)
            actual = normalized(pid, json.loads(value))
            ok = (
                math.isclose(actual, want, abs_tol=1e-6)
                if pid == 774
                else actual == want
            )
            if not ok:
                raise AssertionError((key, actual, want))
        if expected:
            raise AssertionError(sorted(expected))
    print(f"{len(entries)} Java solutions compiled; {len(calls)} ACM outputs verified")


if __name__ == "__main__":
    check()
