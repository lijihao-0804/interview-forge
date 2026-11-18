"""Create a per-lesson reader for the local and deployed Chrome evidence."""
import argparse
import hashlib
from collections import Counter
from html import escape
import json
import os
from pathlib import Path


def pretty(value):
    return escape(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)


def read(path):
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    keyed = {(r["id"], r["viewport"][0]):r for r in records}
    assert len(records) == len(keyed), "Duplicate lesson/viewport"
    root = Path(__file__).resolve().parents[2]
    catalog = json.loads((root/"data/acm/hot200-extra.json").read_bytes())
    assert set(keyed) == {(row["id"], w) for row in catalog for w in (390,2560)}, "Incomplete lesson coverage"
    for row in catalog:
        for width in (390,2560):
            record = keyed[row["id"], width]
            if not record["issues"]:
                assert len(record["examples"]) == len(row["samples"]) + 1
                assert all(len(e["history"]) == e["steps"] for e in record["examples"])
    return keyed


def render(path, evidence, key, record):
    if not record:
        return "<p>尚无记录</p>"
    blocks = []
    if record.get("lesson_capture") and evidence:
        folder = evidence / record["id"]
        target = folder / record["lesson_capture"]["path"]
        link = os.path.relpath(target,path.parent).replace(os.sep,"/")
        blocks.append(f'<p><a href="{escape(link,quote=True)}">题解整页视口截图</a></p>')
    for item in record["examples"]:
        rows = []
        for step in item["history"]:
            state = step.get("state", "")
            if "position" in step:
                state = f"执行位置 {step['position']} · 第 {step['line']} 行"
            rows.append("<tr><td>"+str(step["step"])+"</td><td>"+pretty(state)+"</td><td><code>"+
                        pretty(step.get("code") or "")+"</code></td><td>"+pretty(step["explanation"])+"</td></tr>")
        image = ""
        if evidence and item.get("screenshot"):
            link = os.path.relpath(evidence / item["screenshot"],path.parent).replace(os.sep,"/")
            image = f' · <a href="{escape(link,quote=True)}">末帧截图</a>'
            start = os.path.relpath(evidence / item["start_screenshot"],path.parent).replace(os.sep,"/")
            image += f' · <a href="{escape(start,quote=True)}">首帧截图</a>'
        blocks.append("<details><summary>"+pretty(item["label"])+f' · {item["steps"]} 步</summary><p>末值 '+
                       pretty(item["actual"])+" · 预期 "+pretty(item["expected"])+image+"</p><table><tr><th>步</th><th>状态</th><th>代码</th><th>讲解</th></tr>"+
                       "".join(rows)+"</table></details>")
    issues = "；".join(record["issues"]) or "通过"
    return f"<h4>{pretty(key)} · {record['viewport'][0]} × {record['viewport'][1]} · {pretty(issues)}</h4>"+ "".join(blocks)


def verify_images(records, folder):
    if not folder:
        return
    for record in records.values():
        captures = []
        if "lesson_capture" in record:
            lesson = record["lesson_capture"]
            captures.append((folder/record["id"]/lesson["path"], lesson["sha256"]))
        for item in record["examples"]:
            for image_key, hash_key in (("start_screenshot","start_sha256"),("screenshot","sha256")):
                captures.append((folder/item[image_key],item[hash_key]))
        for path, digest in captures:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"Screenshot hash mismatch: {path}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local",type=Path,required=True)
    parser.add_argument("--live",type=Path,required=True)
    parser.add_argument("--local-evidence",type=Path)
    parser.add_argument("--live-evidence",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    stages = (("本地",read(args.local),args.local_evidence),("线上",read(args.live),args.live_evidence))
    counts = []
    lessons = []
    root = Path(__file__).resolve().parents[2]
    for title,records,evidence in stages:
        verify_images(records,evidence)
        total = Counter()
        for rec in records.values():
            total.update(visits=1,examples=len(rec["examples"]),steps=sum(e["steps"] for e in rec["examples"]),
                         failures=bool(rec["issues"]))
        counts.append(f"<li>{title}：{total['visits']} 次题解访问，{total['examples']} 组演示，"
                      f"{total['steps']} 个展示步骤，{total['failures']} 次访问记录问题。</li>")
    for r in json.loads((root/"data/acm/hot200-extra.json").read_bytes()):
        body = "".join(render(args.output,ev,name,data.get((r["id"],w))) for name,data,ev in stages for w in [390,2560])
        lessons.append(f"<details><summary>{pretty(r['id'])}　{pretty(r['title'])}</summary>{body}</details>")
    args.output.write_text("""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hot 200 动画逐步验收</title><style>body{max-width:1050px;margin:auto;padding:1em;font:16px/1.55 system-ui;color:#172435}
details{border-top:1px solid #ccd6de;padding:.5em}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ccd6de;padding:.3em;text-align:left;overflow-wrap:anywhere}code{white-space:pre-wrap}</style>
<h1>Hot 200 动画逐步验收</h1><ul>"""+"".join(counts)+"""</ul>
<p>两种视口均从实际题解打开内嵌演示。执行用例逐帧核对独立重跑 Python 得到的行号、变量与判题样例末值。
思路推演对照作者的图格、状态与讲解，核对显示代码的源码行号，并按独立整理的 100 个例题答案检查末步及必要的前序步骤。每个条目保留浏览器读取的末值、代码和讲解。</p>"""+"".join(lessons),encoding="utf-8")


if __name__ == "__main__":
    main()
